"""Persist exact contract scan signatures without granting review or execution.

Internal transport only. The caller must journal the original request before
sending it; no endpoint, keys, scanner configuration or automatic retry is added.
"""
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from schemas.acquisition_contract_documents import DocumentPurpose
from tools.acquisition_evidence import EvidenceUnavailable, authenticated_origin, unique_json_object
from tools.acquisition_evidence_attestation import ScanObservation
from tools.acquisition_evidence_persistence import (
    SignedObservationEnvelope, EvidencePersistenceUnconfirmed, _post_signed_observation,
)


class SignedContractObservationRequest(SignedObservationEnvelope):
    p_contract: UUID
    p_version: int = Field(strict=True, ge=1, le=2147483647)
    p_purpose: DocumentPurpose

    @field_validator('p_contract', mode='before')
    @classmethod
    def canonical_contract(cls, value):
        return cls.canonical_identity(value)


class PersistedContractObservationReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    verification_id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=1, le=2147483647)
    purpose: DocumentPurpose
    artifact_id: UUID
    scan_status: Literal['no_detection', 'detected']
    duplicate: StrictBool
    observation_persisted: StrictBool
    preview_authorized: StrictBool
    legal_review_approved: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def no_approval(self):
        if (not self.observation_persisted or self.preview_authorized
                or self.legal_review_approved or self.execution_authorized):
            raise ValueError('Persisted non-approving observation required')
        return self


async def persist_contract_attestation(client, signed_request, *, workspace_id: UUID, contract_id: UUID,
                                       contract_version: int, purpose: str, artifact_id: UUID,
                                       actor_id: UUID, session_id: UUID):
    """Send once to the fixed RPC; any uncertain result retains the exact request.

    Old requests may reconcile immutable historical receipts. Only the database
    decides whether current authority permits a new write or historical replay.
    """
    try:
        if (type(signed_request) is not dict or type(contract_version) is not int
                or not all(isinstance(v, UUID) for v in
                           (workspace_id, contract_id, artifact_id, actor_id, session_id))):
            raise ValueError('Scoped signed request required')
        request = SignedContractObservationRequest.model_validate(signed_request)
        if (request.p_workspace, request.p_contract, request.p_version, request.p_purpose,
                request.p_artifact, request.p_actor, request.p_session) != (
                workspace_id, contract_id, contract_version, purpose, artifact_id, actor_id, session_id):
            raise ValueError('Contract observation scope mismatch')
        observation = ScanObservation.model_validate(json.loads(request.p_observation, object_pairs_hook=unique_json_object))
        body = json.dumps(request.model_dump(mode='json'), separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
        if len(body) > 12288:
            raise ValueError('Bounded signed request required')
        url = authenticated_origin(client).copy_with(path='/rest/v1/rpc/record_contract_document_verification')
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise EvidenceUnavailable('Signed contract observation request is invalid') from None
    try:
        receipt = PersistedContractObservationReceipt.model_validate(await _post_signed_observation(client, url, body))
        if (receipt.verification_id, receipt.workspace_id, receipt.contract_id, receipt.contract_version,
                receipt.purpose, receipt.artifact_id, receipt.scan_status) != (
                request.p_id, request.p_workspace, request.p_contract, request.p_version,
                request.p_purpose, request.p_artifact, observation.scan_status):
            raise ValueError('Contract observation receipt mismatch')
        return receipt.model_dump(mode='json')
    except (ValueError, TypeError, RecursionError):
        raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed') from None
