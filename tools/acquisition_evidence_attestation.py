"""Internal signing contract for trusted scanner output, never a browser API.

Provisioning, bounded persistence/recovery transport and approval binding remain
separate. No environment secret lookup or default key is provided here.
"""
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from schemas.acquisition_evidence import MAX_EVIDENCE_BYTES
from tools.acquisition_evidence import EvidenceUnavailable, utcnow


class ScanObservation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    byte_size: int = Field(strict=True, ge=1, le=MAX_EVIDENCE_BYTES)
    media_type: Literal['application/pdf','image/png','image/jpeg','text/plain']
    retain_until: AwareDatetime
    retention_policy_id: UUID
    checked_at: AwareDatetime
    scan_checked_at: AwareDatetime
    registry_checked_at: AwareDatetime
    scanner: Literal['clamav-instream-v1']
    scanner_version: str = Field(pattern=r'^ClamAV [0-9]+\.[0-9]+\.[0-9]+/[0-9]+/[\x20-\x7e]{1,100}$', max_length=160)
    scan_policy_version: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
    scan_status: Literal['no_detection','detected']

    @field_validator('checked_at','scan_checked_at','registry_checked_at','retain_until',mode='before')
    @classmethod
    def string_timestamp(cls, value):
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})',value):
            raise ValueError('Explicit timestamp string required')
        return value

    @model_validator(mode='after')
    def ordered_observation(self):
        if (self.checked_at>self.scan_checked_at or self.registry_checked_at<self.scan_checked_at-timedelta(seconds=5)
                or self.retain_until<=max(self.checked_at,self.scan_checked_at,self.registry_checked_at)):
            raise ValueError('Current ordered observation required')
        return self


class ScanReceipt(ScanObservation):
    status: Literal['scan_observed']
    workspace_id: UUID
    campaign_id: UUID
    evidence_ref: UUID
    purpose: Literal['mail_content','mail_destination']
    verifier_version: Literal['acquisition-evidence-bytes-v1']
    registry_verifier_version: Literal['acquisition-evidence-registry-v1']
    verification_persisted: StrictBool
    scan_persisted: StrictBool
    preview_authorized: StrictBool
    content_approved: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def no_authority(self):
        if any(getattr(self,k) for k in ('verification_persisted','scan_persisted','preview_authorized','content_approved','execution_authorized')):
            raise ValueError('Unpersisted non-approving scanner observation required')
        return self


@dataclass(frozen=True)
class VerificationSigningKey:
    id: UUID
    workspace_id: UUID
    secret: bytes = field(repr=False)
    scanner_version: str
    scan_policy_version: str
    valid_from: datetime
    valid_until: datetime


def build_scan_attestation(receipt, *, request_id: UUID, actor_id: UUID, session_id: UUID,
                           key: VerificationSigningKey, clock=utcnow):
    """Sign only validated internal scan output; preserve this exact request on retry.

    The database independently checks the signature, current authority, registry,
    key validity and freshness. This function alone grants no persistence/approval.
    Never wrap it in an endpoint accepting a caller's scan result or key material.
    """
    try:
        now=clock()
        scan=ScanReceipt.model_validate(receipt)
        if (type(key) is not VerificationSigningKey or not all(isinstance(v,UUID) for v in
                (request_id,actor_id,session_id,key.id,key.workspace_id)) or type(key.secret) is not bytes or len(key.secret)!=32
                or key.workspace_id!=scan.workspace_id or key.scanner_version!=scan.scanner_version
                or key.scan_policy_version!=scan.scan_policy_version
                or any(t.utcoffset() is None for t in (now,key.valid_from,key.valid_until))
                or not key.valid_from<=now<key.valid_until or not key.valid_from<=scan.checked_at
                or key.valid_until-key.valid_from>timedelta(hours=24)
                or not now-timedelta(seconds=120)<=scan.checked_at
                or max(scan.scan_checked_at,scan.registry_checked_at)>now+timedelta(seconds=5)
                or scan.retain_until<=now):
            raise ValueError('Invalid signing scope or deadline')
        observation=scan.model_dump(mode='json',include=set(ScanObservation.model_fields))
        payload=json.dumps(observation,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
        context=[request_id,scan.workspace_id,scan.campaign_id,scan.evidence_ref,actor_id,session_id,key.id]
        message='acquisition-evidence-attestation-v1\n'+'\n'.join(map(str,context))+'\n'+payload
        signature=hmac.new(key.secret,message.encode('utf-8'),hashlib.sha256).hexdigest()
        return dict(zip(('p_id','p_workspace','p_campaign','p_artifact','p_actor','p_session','p_key'),map(str,context)),
                    p_observation=payload,p_signature=signature)
    except (ValueError,TypeError,AttributeError):
        raise EvidenceUnavailable('Trusted scan attestation is unavailable') from None
