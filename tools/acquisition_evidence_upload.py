"""Bounded non-overwriting upload seam. No public route, scanner or approval authority."""
import asyncio
import hashlib
import hmac
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from uuid import UUID

import httpx

from schemas.acquisition_evidence import EVIDENCE_BUCKET
from tools.acquisition_evidence import (
    EvidenceUnavailable, authenticated_origin, load_registry_state, utcnow, verify_registered_evidence,
)


class EvidenceUploadUnconfirmed(EvidenceUnavailable):
    """A write may have occurred. Preserve the artifact identity and exact file for recovery."""


def plausible_media(body: bytearray, media_type: str) -> bool:
    """Conservative format precheck only; never a parser, malware scan or safety verdict."""
    if media_type == 'application/pdf':
        return body.startswith(b'%PDF-') and b'%%EOF' in body[-1024:]
    if media_type == 'image/png':
        return body.startswith(b'\x89PNG\r\n\x1a\n') and body.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82')
    if media_type == 'image/jpeg':
        return body.startswith(b'\xff\xd8\xff') and body.endswith(b'\xff\xd9')
    if media_type == 'text/plain':
        try:
            text = body.decode('utf-8')
        except UnicodeDecodeError:
            return False
        return all(character in '\t\n\r' or (ord(character) >= 32 and not 127 <= ord(character) <= 159) for character in text)
    return False


async def upload_registered_evidence(client: httpx.AsyncClient, artifact_id: UUID, source: AsyncIterator[bytes], *,
                                     workspace_id: UUID, campaign_id: UUID, purpose: str,
                                     clock: Callable[[], datetime] = utcnow) -> dict:
    """Validate whole bounded input before one POST, then independently reconcile exact bytes.

    No retry, upsert, signed URL, DELETE or filename from the caller. The source is
    consumed once and closed when it supports aclose. Bytes stay in bounded process
    memory only, never a temporary file. HTTP failures after attempting the write
    retain an uncertain outcome unless a fresh authorized read proves the object.
    """
    body = bytearray()
    attempted = False
    try:
        if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, campaign_id))
                or purpose not in ('mail_content','mail_destination') or not hasattr(source, '__anext__')):
            raise EvidenceUnavailable('Evidence upload identity or stream is invalid')
        origin = authenticated_origin(client)
        started = clock()
        if started.utcoffset() is None:
            raise EvidenceUnavailable('Evidence upload clock is invalid')
        async with asyncio.timeout(60):
            before = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                               campaign_id=campaign_id, purpose=purpose, clock=clock)
            digest = hashlib.sha256()
            async with asyncio.timeout(10):
                async for chunk in source:
                    if not isinstance(chunk, bytes) or len(body) + len(chunk) > before.byte_size:
                        raise EvidenceUnavailable('File does not match registered evidence')
                    body.extend(chunk)
                    digest.update(chunk)
                    # Even a source yielding endless empty chunks must honor the deadline.
                    await asyncio.sleep(0)
            if (len(body) != before.byte_size or not hmac.compare_digest(digest.hexdigest(), before.sha256)
                    or not plausible_media(body, before.media_type)):
                raise EvidenceUnavailable('File does not match registered evidence')
            current = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                                campaign_id=campaign_id, purpose=purpose, clock=clock)
            now = clock()
            if (before.model_dump(exclude={'checked_at'}) != current.model_dump(exclude={'checked_at'})
                    or current.checked_at < before.checked_at or now.utcoffset() is None or now < started
                    or not current.available_at(now)):
                raise EvidenceUnavailable('Evidence changed before upload')
            url = origin.copy_with(path=f'/storage/v1/object/{EVIDENCE_BUCKET}/{current.object_name}')

            async def chunks():
                for offset in range(0, len(body), 65536):
                    yield bytes(body[offset:offset+65536])

            attempted = True
            try:
                async with asyncio.timeout(15):
                    async with client.stream('POST', url, content=chunks(), follow_redirects=False, timeout=10,
                         headers={'Content-Type': current.media_type, 'Content-Length': str(len(body)),
                                  'x-upsert': 'false', 'Cache-Control': 'no-store', 'Accept-Encoding': 'identity'}) as response:
                        # Ignore provider response bodies/IDs: they cannot establish stored bytes.
                        # 400/409 may be an identical retry; 5xx may follow a committed write.
                        if response.url != url or not (response.status_code in (200,201,400,409) or 500 <= response.status_code < 600):
                            raise EvidenceUploadUnconfirmed('Evidence upload was not confirmed')
            except (httpx.HTTPError, TimeoutError):
                pass  # Reconcile once via a fresh registry + authenticated byte read; never repeat POST.
            receipt = await verify_registered_evidence(client, artifact_id, workspace_id=workspace_id,
                                                       campaign_id=campaign_id, purpose=purpose, clock=clock)
            completed = clock()
            if (receipt['sha256'] != current.sha256 or receipt['byte_size'] != current.byte_size
                    or receipt['media_type'] != current.media_type or receipt['retention_policy_id'] != str(current.retention_policy_id)
                    or datetime.fromisoformat(receipt['retain_until']) != current.retain_until
                    or completed.utcoffset() is None or completed < now or not current.available_at(completed)):
                raise EvidenceUploadUnconfirmed('Evidence upload was not confirmed')
            return {**receipt, 'status': 'stored_unverified', 'upload_version': 'acquisition-evidence-upload-v1',
                    'write_outcome': 'stored_or_existing', 'byte_match_observed': True}
    except (EvidenceUnavailable, httpx.HTTPError, TimeoutError, OSError, TypeError, ValueError, RuntimeError):
        if attempted:
            raise EvidenceUploadUnconfirmed('Evidence upload was not confirmed; preserve the same artifact and file') from None
        raise EvidenceUnavailable('Evidence upload could not be prepared') from None
    finally:
        body.clear()
        close = getattr(source, 'aclose', None)
        if callable(close):
            try:
                async with asyncio.timeout(1):
                    await close()
            except (TimeoutError, OSError):
                pass
