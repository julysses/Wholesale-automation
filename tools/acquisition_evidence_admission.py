"""Shared operational reservation before consuming evidence input. No public upload route."""
import asyncio
from threading import BoundedSemaphore
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException

from schemas.acquisition_evidence import EvidenceUploadAdmission


async def admit_evidence_upload(store, artifact_id, *, workspace_id, campaign_id, purpose, clock=None):
    if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, campaign_id))
            or purpose not in ('mail_content', 'mail_destination')):
        raise HTTPException(422, 'Evidence upload identity is invalid', headers={'Cache-Control': 'no-store'})
    return await _admit_upload(store, 'admit_acquisition_evidence_upload', EvidenceUploadAdmission,
        dict(workspace_id=workspace_id, campaign_id=campaign_id, artifact_id=artifact_id, purpose=purpose),
        dict(p_workspace=str(workspace_id), p_campaign=str(campaign_id), p_artifact=str(artifact_id), p_purpose=purpose), clock)


async def admit_contract_document_upload(store, artifact_id, *, workspace_id, contract_id, contract_version, purpose, clock=None):
    from typing import get_args
    from schemas.acquisition_contract_documents import ContractDocumentUploadAdmission, DocumentPurpose
    if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, contract_id))
            or type(contract_version) is not int or not 1 <= contract_version <= 2147483647
            or purpose not in get_args(DocumentPurpose)):
        raise HTTPException(422, 'Contract document upload identity is invalid', headers={'Cache-Control': 'no-store'})
    return await _admit_upload(store, 'admit_contract_document_upload', ContractDocumentUploadAdmission,
        dict(workspace_id=workspace_id, contract_id=contract_id, contract_version=contract_version, artifact_id=artifact_id, purpose=purpose),
        dict(p_workspace=str(workspace_id), p_contract=str(contract_id), p_version=contract_version,
             p_artifact=str(artifact_id), p_purpose=purpose), clock)


async def _admit_upload(store, rpc, model, scope, body, clock):
    attempt = uuid4()  # Never accepted from a browser or replayed after an uncertain response.
    try:
        raw = await store.request('POST', 'rpc/'+rpc, body={**body, 'p_attempt': str(attempt)})
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise
    try:
        admission = model.model_validate(raw)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        if (admission.attempt_id != attempt or any(getattr(admission, key) != value for key, value in scope.items())
                or now.utcoffset() is None or not now-timedelta(seconds=15) <= admission.checked_at <= now+timedelta(seconds=5)):
            raise ValueError('Reservation scope or clock mismatch')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Upload capacity could not be confirmed; no file was read',
                            headers={'Cache-Control': 'no-store'}) from None
    if not admission.admitted:
        raise HTTPException(429, 'Upload capacity is occupied; try again shortly',
                            headers={'Cache-Control': 'no-store', 'Retry-After': str(admission.retry_after_seconds)})
    return admission


# Non-blocking across threads/event loops within this process; the database limits
# workspace activity across processes. Keep callers out of the byte buffer while full.
_PROCESS_UPLOADS = BoundedSemaphore(4)


async def upload_with_admission(store, artifact_id, source, *, workspace_id, campaign_id, purpose):
    return await _upload_with_admission(store, artifact_id, source, admit_evidence_upload,
        lambda *args, **kwargs: store.upload_evidence(*args, **kwargs), dict(workspace_id=workspace_id, campaign_id=campaign_id, purpose=purpose))


async def upload_contract_document_with_admission(store, artifact_id, source, *, workspace_id, contract_id, contract_version, purpose):
    return await _upload_with_admission(store, artifact_id, source, admit_contract_document_upload,
        lambda *args, **kwargs: store.upload_contract_document(*args, **kwargs), dict(workspace_id=workspace_id, contract_id=contract_id,
            contract_version=contract_version, purpose=purpose))


async def _upload_with_admission(store, artifact_id, source, admit, upload, scope):
    from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed
    acquired = False
    started = False
    try:
        acquired = _PROCESS_UPLOADS.acquire(blocking=False)
        if not acquired:
            raise HTTPException(429, 'Upload capacity is occupied; try again shortly',
                                headers={'Cache-Control': 'no-store', 'Retry-After': '5'})
        async with asyncio.timeout(90):
            await admit(store, artifact_id, **scope)
            started = True
            return await upload(artifact_id, source, **scope)
    except TimeoutError:
        if started:
            raise EvidenceUploadUnconfirmed('Upload was not confirmed; preserve the same artifact and file') from None
        raise HTTPException(503, 'Upload capacity could not be confirmed; no file was read',
                            headers={'Cache-Control': 'no-store'}) from None
    finally:
        try:
            if not started and hasattr(source, 'aclose'):
                try:
                    async with asyncio.timeout(1):
                        await source.aclose()
                except (TimeoutError, OSError, RuntimeError):
                    pass
        finally:
            if acquired:
                _PROCESS_UPLOADS.release()
