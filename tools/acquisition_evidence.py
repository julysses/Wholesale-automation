"""Bounded authenticated storage reads; no uploads, signed URLs or approvals.

Call only with a descriptor loaded from the workspace evidence registry. The
registry/immutable storage policies and approval transaction still need wiring;
this transport does not make a client-supplied reference trustworthy. No endpoint
exposes it yet. Returned receipts prove exact bytes at a time, not legal sufficiency,
malware safety, current membership after that instant, or execution authority.
"""
import asyncio
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

import httpx

from schemas.acquisition_evidence import EvidenceArtifact, EVIDENCE_BUCKET


class EvidenceUnavailable(ValueError):
    """Generic, payload-free failure: never expose object data or upstream errors."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def verify_evidence_bytes(client: httpx.AsyncClient, artifact: EvidenceArtifact, *,
                                workspace_id: UUID, campaign_id: UUID, purpose: str,
                                clock: Callable[[], datetime] = utcnow) -> dict:
    # Revalidate even model_construct/model_copy inputs from internal callers.
    try:
        artifact = EvidenceArtifact.model_validate(artifact.model_dump())
    except (ValueError, AttributeError, TypeError):
        raise EvidenceUnavailable('Evidence descriptor is invalid') from None
    started = clock()
    if ((artifact.workspace_id, artifact.campaign_id, artifact.purpose) != (workspace_id, campaign_id, purpose)
            or not artifact.available_at(started)):
        raise EvidenceUnavailable('Evidence is unavailable for this review')
    origin = client.base_url
    authorization = client.headers.get('authorization', '')
    if (origin.scheme != 'https' or not origin.host or origin.userinfo or origin.query or origin.fragment
            or origin.path != '/rest/v1/' or not authorization.lower().startswith('bearer ')
            or not authorization[7:] or any(c.isspace() for c in authorization[7:]) or not client.headers.get('apikey')):
        raise EvidenceUnavailable('Authenticated evidence storage is unavailable')
    url = origin.copy_with(path=f'/storage/v1/object/authenticated/{EVIDENCE_BUCKET}/{artifact.object_name}')
    digest = hashlib.sha256()
    size = 0
    try:
        # Wall-clock bound in addition to per-read timeout: trickle streams cannot
        # keep verification open indefinitely. No decompression or redirects.
        async with asyncio.timeout(15):
            async with client.stream('GET', url, follow_redirects=False, timeout=10,
                                     headers={'Accept-Encoding': 'identity', 'Cache-Control': 'no-store'}) as response:
                if response.status_code != 200 or response.url != url:
                    raise EvidenceUnavailable('Evidence bytes could not be verified')
                encoding = response.headers.get('content-encoding', 'identity').lower()
                content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
                length = response.headers.get('content-length')
                if (encoding != 'identity' or content_type != artifact.media_type
                        or (length is not None and (len(length) > 10 or not length.isascii() or not length.isdigit() or int(length) != artifact.byte_size))):
                    raise EvidenceUnavailable('Evidence bytes could not be verified')
                async for chunk in response.aiter_raw():
                    size += len(chunk)
                    if size > artifact.byte_size:
                        raise EvidenceUnavailable('Evidence bytes could not be verified')
                    digest.update(chunk)
    except (httpx.HTTPError, TimeoutError):
        raise EvidenceUnavailable('Evidence storage could not be read') from None
    checked = clock()
    if (checked.utcoffset() is None or checked < started or not artifact.available_at(checked) or size != artifact.byte_size
            or not hmac.compare_digest(digest.hexdigest(), artifact.sha256)):
        raise EvidenceUnavailable('Evidence bytes could not be verified')
    return {'status': 'bytes_verified', 'verifier_version': 'acquisition-evidence-bytes-v1',
            'workspace_id': str(workspace_id), 'campaign_id': str(campaign_id), 'evidence_ref': str(artifact.id),
            'purpose': purpose, 'sha256': artifact.sha256, 'byte_size': size, 'media_type': artifact.media_type,
            'checked_at': checked.isoformat(), 'retain_until': artifact.retain_until.isoformat(),
            'execution_authorized': False, 'content_approved': False}
