"""Registry-backed byte observation only; no endpoint, signing or legal approval."""
import asyncio
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID
import httpx
from schemas.acquisition_contract_documents import ContractDocumentArtifact, ContractDocumentRegistryState
from tools.acquisition_evidence import EvidenceUnavailable, _verify_retained_object, _read_registry_json, utcnow


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


async def load_contract_document_state(client, *, artifact_id, workspace_id, contract_id, contract_version, purpose, clock):
    try:
        raw = await _read_registry_json(client, 'contract_document_state', {
            'p_workspace': str(workspace_id), 'p_contract': str(contract_id), 'p_version': contract_version, 'p_artifact': str(artifact_id)})
        state = ContractDocumentRegistryState.model_validate(raw)
        now = clock()
        if ((state.id, state.workspace_id, state.contract_id, state.contract_version, state.purpose)
                != (artifact_id, workspace_id, contract_id, contract_version, purpose)
                or not state.available_at(now) or not now - timedelta(seconds=30) <= state.checked_at <= now + timedelta(seconds=5)):
            raise EvidenceUnavailable('Contract document registry is unavailable')
        return state
    except (ValueError, TypeError):
        raise EvidenceUnavailable('Contract document registry is unavailable') from None


async def verify_registered_contract_document(client: httpx.AsyncClient, artifact_id: UUID, *, workspace_id: UUID,
                                               contract_id: UUID, contract_version: int, purpose: str,
                                               clock: Callable[[], datetime] = utcnow) -> dict:
    """Current registry → bounded exact bytes → current registry; no persisted approval."""
    if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, contract_id))
            or type(contract_version) is not int or contract_version < 1
            or purpose not in ('purchase_contract', 'title_report', 'assignment_agreement', 'seller_disclosure',
                               'assignee_disclosure', 'closing_statement', 'supporting_document')):
        raise EvidenceUnavailable('Contract document identity is invalid')
    scope = dict(artifact_id=artifact_id, workspace_id=workspace_id, contract_id=contract_id,
                 contract_version=contract_version, purpose=purpose, clock=clock)
    started = clock()
    if started.utcoffset() is None:
        raise EvidenceUnavailable('Contract document clock is invalid')
    try:
        async with asyncio.timeout(25):
            before = await load_contract_document_state(client, **scope)
            receipt = await verify_contract_document_bytes(client, before.descriptor(), workspace_id=workspace_id,
                contract_id=contract_id, contract_version=contract_version, purpose=purpose, clock=clock)
            after = await load_contract_document_state(client, **scope)
            completed = clock()
            checked = datetime.fromisoformat(receipt['checked_at'])
            if (before.model_dump(exclude={'checked_at'}) != after.model_dump(exclude={'checked_at'})
                    or after.checked_at < before.checked_at or completed.utcoffset() is None or completed < started
                    or after.checked_at < checked - timedelta(seconds=5) or completed < checked or not after.available_at(completed)):
                raise EvidenceUnavailable('Contract document changed during verification')
            return {**receipt, 'registry_verifier_version': 'acquisition-contract-document-registry-v1',
                    'retention_policy_id': str(after.retention_policy_id), 'registry_checked_at': after.checked_at.isoformat()}
    except TimeoutError:
        raise EvidenceUnavailable('Contract document verification timed out') from None


async def upload_registered_contract_document(client, artifact_id, source, *, workspace_id, contract_id,
                                               contract_version, purpose, clock=utcnow):
    """Internal bounded transport; writes still require current exact-document Storage authorization."""
    from typing import get_args
    from schemas.acquisition_contract_documents import DocumentPurpose
    from tools.acquisition_evidence_upload import _upload_registered_object
    scope = dict(artifact_id=artifact_id, workspace_id=workspace_id, contract_id=contract_id,
                 contract_version=contract_version, purpose=purpose, clock=clock)
    def validate():
        if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, contract_id))
                or type(contract_version) is not int or not 1 <= contract_version <= 2147483647
                or purpose not in get_args(DocumentPurpose)):
            raise EvidenceUnavailable('Contract document upload identity is invalid')
    async def load():
        return await load_contract_document_state(client, **scope)
    async def verify():
        return await verify_registered_contract_document(client, **scope)
    return await _upload_registered_object(client, source, validate=validate, load=load, verify=verify,
        upload_version='acquisition-contract-document-upload-v1', clock=clock)
