"""Bounded user-authorized persistence of an already prepared signed observation.

No signing, scanning, new request IDs, automatic retries or clearance. A caller
must durably retain the exact signed request before dispatch and reconcile it
unchanged after uncertainty. This transport does not provide that worker journal.
"""
import asyncio
import json
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from tools.acquisition_evidence import EvidenceUnavailable, authenticated_origin, unique_json_object
from tools.acquisition_evidence_attestation import ScanObservation

PERSIST_SECONDS = 10
MAX_RESPONSE_BYTES = 2048


class EvidencePersistenceUnconfirmed(EvidenceUnavailable):
    """A write may have committed. Keep the exact signed request, even on denial."""


class SignedObservationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    p_id: UUID
    p_workspace: UUID
    p_campaign: UUID
    p_artifact: UUID
    p_actor: UUID
    p_session: UUID
    p_key: UUID
    p_observation: str = Field(strict=True, min_length=2, max_length=4096)
    p_signature: str = Field(strict=True, pattern=r'^[0-9a-f]{64}$')

    @field_validator('p_id','p_workspace','p_campaign','p_artifact','p_actor','p_session','p_key',mode='before')
    @classmethod
    def canonical_identity(cls,value):
        if not isinstance(value,str) or str(UUID(value)) != value:
            raise ValueError('Canonical signed identity required')
        return value

    @field_validator('p_observation')
    @classmethod
    def bounded_exact_observation(cls,value):
        if len(value.encode('utf-8')) > 4096:
            raise ValueError('Bounded observation required')
        ScanObservation.model_validate(json.loads(value,object_pairs_hook=unique_json_object))
        return value  # The original signed text, never normalized or reserialized.


class PersistedObservationReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    verification_id: UUID
    artifact_id: UUID
    workspace_id: UUID
    scan_status: Literal['no_detection','detected']
    duplicate: StrictBool
    observation_persisted: StrictBool
    preview_authorized: StrictBool
    content_approved: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def persisted_is_not_approval(self):
        if (not self.observation_persisted or self.preview_authorized or self.content_approved or self.execution_authorized):
            raise ValueError('Stored non-approving observation required')
        return self


async def persist_evidence_attestation(client: httpx.AsyncClient, signed_request, *, workspace_id: UUID,
                                       campaign_id: UUID, artifact_id: UUID, actor_id: UUID, session_id: UUID):
    """One fixed RPC POST. Every post-dispatch failure remains unconfirmed.

    No recency check is imposed on a previously signed request: the database can
    return an exact historical duplicate after expiry/revocation. New writes must
    satisfy its current signature, session, policy and observation checks.
    """
    try:
        if type(signed_request) is not dict or not all(isinstance(v,UUID) for v in
                (workspace_id,campaign_id,artifact_id,actor_id,session_id)):
            raise ValueError('Scoped signed request required')
        request=SignedObservationRequest.model_validate(signed_request)
        if (request.p_workspace,request.p_campaign,request.p_artifact,request.p_actor,request.p_session) != (
                workspace_id,campaign_id,artifact_id,actor_id,session_id):
            raise ValueError('Signed request scope mismatch')
        observation=ScanObservation.model_validate(json.loads(request.p_observation,object_pairs_hook=unique_json_object))
        body=json.dumps(request.model_dump(mode='json'),separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')
        if len(body)>12288: raise ValueError('Bounded signed request required')
        url=authenticated_origin(client).copy_with(path='/rest/v1/rpc/record_acquisition_evidence_verification')
    except (ValueError,TypeError,AttributeError,RecursionError):
        raise EvidenceUnavailable('Signed evidence request is invalid') from None
    data=bytearray()
    try:
        async with asyncio.timeout(PERSIST_SECONDS):
            async with client.stream('POST',url,content=body,follow_redirects=False,timeout=5,
                    headers={'Content-Type':'application/json','Accept-Encoding':'identity','Cache-Control':'no-store'}) as response:
                length=response.headers.get('content-length')
                if (response.status_code!=200 or response.url!=url
                        or response.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json'
                        or response.headers.get('content-encoding','identity').lower()!='identity'
                        or (length is not None and (len(length)>5 or not length.isascii() or not length.isdigit()
                                                  or not 0<int(length)<=MAX_RESPONSE_BYTES))):
                    raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed')
                async for chunk in response.aiter_raw():
                    if len(data)+len(chunk)>MAX_RESPONSE_BYTES:
                        raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed')
                    data.extend(chunk)
                    await asyncio.sleep(0)
                if length is not None and len(data)!=int(length):
                    raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed')
        receipt=PersistedObservationReceipt.model_validate(json.loads(data,object_pairs_hook=unique_json_object))
        if (receipt.verification_id,receipt.workspace_id,receipt.artifact_id,receipt.scan_status) != (
                request.p_id,request.p_workspace,request.p_artifact,observation.scan_status):
            raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed')
        return receipt.model_dump(mode='json')
    except (httpx.HTTPError,TimeoutError,ValueError,TypeError,RecursionError):
        # Even 401/403/409 on a later attempt does not prove the earlier attempt
        # failed to commit. No source text or signed capability is put in errors.
        raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed') from None
    finally:
        data.clear()
