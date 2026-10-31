"""Internal contract scan signing format; no endpoint, key provisioning or persistence.

Contract keys are a distinct type with explicit document purposes. Existing mail
keys cannot acquire contract signing authority by being passed to this function.
Database acceptance and durable exact-request recovery remain separate gates.
"""
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, get_args
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from schemas.acquisition_contract_documents import DocumentPurpose
from tools.acquisition_evidence import EvidenceUnavailable, utcnow
from tools.acquisition_evidence_attestation import ScanObservation


class ContractScanReceipt(ScanObservation):
    status: Literal['scan_observed']
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    artifact_id: UUID
    purpose: DocumentPurpose
    verifier_version: Literal['acquisition-contract-document-bytes-v1']
    registry_verifier_version: Literal['acquisition-contract-document-registry-v1']
    verification_persisted: StrictBool
    scan_persisted: StrictBool
    preview_authorized: StrictBool
    legal_review_approved: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def no_authority(self):
        if any(getattr(self, name) for name in ('verification_persisted', 'scan_persisted', 'preview_authorized', 'legal_review_approved', 'execution_authorized')):
            raise ValueError('Unpersisted non-approving contract observation required')
        return self


@dataclass(frozen=True)
class ContractVerificationSigningKey:
    id: UUID
    workspace_id: UUID
    secret: bytes = field(repr=False)
    purposes: frozenset[str]
    scanner_version: str
    scan_policy_version: str
    valid_from: datetime
    valid_until: datetime


def build_contract_scan_attestation(receipt, *, request_id: UUID, actor_id: UUID, session_id: UUID,
                                    key: ContractVerificationSigningKey, clock=utcnow):
    """Sign trusted internal output only; never sign caller-supplied scan assertions.

    Preserve the exact returned request for retries. This signature is not legal
    approval, scanner deployment authorization or evidence of database acceptance.
    """
    try:
        now = clock()
        scan = ContractScanReceipt.model_validate(receipt)
        if (type(key) is not ContractVerificationSigningKey
                or not all(isinstance(value, UUID) for value in (request_id, actor_id, session_id, key.id, key.workspace_id))
                or type(key.secret) is not bytes or len(key.secret) != 32
                or type(key.purposes) is not frozenset or not key.purposes
                or not key.purposes <= set(get_args(DocumentPurpose)) or scan.purpose not in key.purposes
                or key.workspace_id != scan.workspace_id or key.scanner_version != scan.scanner_version
                or key.scan_policy_version != scan.scan_policy_version
                or any(t.utcoffset() is None for t in (now, key.valid_from, key.valid_until))
                or not key.valid_from <= now < key.valid_until or not key.valid_from <= scan.checked_at
                or key.valid_until-key.valid_from > timedelta(hours=24)
                or not now-timedelta(seconds=120) <= scan.checked_at
                or max(scan.scan_checked_at, scan.registry_checked_at) > now+timedelta(seconds=5)
                or scan.retain_until <= now):
            raise ValueError('Invalid contract signing scope or deadline')
        observation = scan.model_dump(mode='json', include=set(ScanObservation.model_fields))
        payload = json.dumps(observation, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
        fields = ('p_id', 'p_workspace', 'p_contract', 'p_version', 'p_purpose', 'p_artifact', 'p_actor', 'p_session', 'p_key')
        values = (request_id, scan.workspace_id, scan.contract_id, scan.contract_version, scan.purpose, scan.artifact_id, actor_id, session_id, key.id)
        context = list(map(str, values))
        message = 'acquisition-contract-document-attestation-v1\n'+'\n'.join(context)+'\n'+payload
        result = dict(zip(fields, context), p_observation=payload,
                      p_signature=hmac.new(key.secret, message.encode('utf-8'), hashlib.sha256).hexdigest())
        result['p_version'] = scan.contract_version
        return result
    except (ValueError, TypeError, AttributeError):
        raise EvidenceUnavailable('Trusted contract scan attestation is unavailable') from None
