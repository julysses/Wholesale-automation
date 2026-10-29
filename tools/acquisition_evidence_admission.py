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
    attempt = uuid4()  # Never accepted from a browser or replayed after an uncertain response.
    try:
        raw = await store.request('POST', 'rpc/admit_acquisition_evidence_upload', body={
            'p_attempt': str(attempt), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
            'p_artifact': str(artifact_id), 'p_purpose': purpose})
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise
    try:
        admission = EvidenceUploadAdmission.model_validate(raw)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        if ((admission.attempt_id, admission.workspace_id, admission.campaign_id, admission.artifact_id, admission.purpose)
                != (attempt, workspace_id, campaign_id, artifact_id, purpose)
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
    from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed
    acquired = False
    started = False
    try:
        acquired = _PROCESS_UPLOADS.acquire(blocking=False)
        if not acquired:
            raise HTTPException(429, 'Upload capacity is occupied; try again shortly',
                                headers={'Cache-Control': 'no-store', 'Retry-After': '5'})
        async with asyncio.timeout(90):
            await admit_evidence_upload(store, artifact_id, workspace_id=workspace_id,
                                       campaign_id=campaign_id, purpose=purpose)
            started = True
            return await store.upload_evidence(artifact_id, source, workspace_id=workspace_id,
                                               campaign_id=campaign_id, purpose=purpose)
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
