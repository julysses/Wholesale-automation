"""Internal byte observation only; no endpoint, registry, signing or legal approval."""
from datetime import datetime
from typing import Callable
from uuid import UUID
import httpx
from schemas.acquisition_contract_documents import ContractDocumentArtifact
from tools.acquisition_evidence import EvidenceUnavailable, _verify_retained_object, utcnow


async def verify_contract_document_bytes(client: httpx.AsyncClient, artifact: ContractDocumentArtifact, *,
                                         workspace_id: UUID, contract_id: UUID, contract_version: int,
                                         purpose: str, clock: Callable[[], datetime] = utcnow) -> dict:
    try:
        artifact = ContractDocumentArtifact.model_validate(artifact.model_dump())
    except (ValueError, AttributeError, TypeError):
        raise EvidenceUnavailable('Contract document descriptor is invalid') from None
    if (not isinstance(workspace_id, UUID) or not isinstance(contract_id, UUID)
            or type(contract_version) is not int or contract_version < 1
            or (artifact.workspace_id, artifact.contract_id, artifact.contract_version, artifact.purpose)
                != (workspace_id, contract_id, contract_version, purpose)):
        raise EvidenceUnavailable('Contract document scope is invalid')
    checked, size = await _verify_retained_object(client, artifact, clock=clock)
    return {'status': 'bytes_verified', 'verifier_version': 'acquisition-contract-document-bytes-v1',
            'workspace_id': str(workspace_id), 'contract_id': str(contract_id), 'contract_version': contract_version,
            'artifact_id': str(artifact.id), 'purpose': purpose, 'sha256': artifact.sha256,
            'byte_size': size, 'media_type': artifact.media_type, 'checked_at': checked.isoformat(),
            'retain_until': artifact.retain_until.isoformat(), 'verification_persisted': False,
            'scan_status': 'not_scanned', 'legal_review_approved': False, 'execution_authorized': False}
