"""Bounded authenticated storage reads; no uploads, signed URLs or approvals.

The store resolves descriptors from the protected registry and rechecks after
reading. Persistence and approval transactions still need wiring; this transport
does not make a client-supplied reference trustworthy. No endpoint exposes it yet.
Returned receipts prove exact bytes at a time, not legal sufficiency,
malware safety, current membership after that instant, or execution authority.
"""
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

import httpx

from schemas.acquisition_evidence import EvidenceArtifact, EvidenceRegistryState, EVIDENCE_BUCKET


class EvidenceUnavailable(ValueError):
    """Generic, payload-free failure: never expose object data or upstream errors."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def authenticated_origin(client: httpx.AsyncClient) -> httpx.URL:
    origin = client.base_url
    authorization = client.headers.get('authorization', '')
    if (origin.scheme != 'https' or not origin.host or origin.userinfo or origin.query or origin.fragment
            or origin.path != '/rest/v1/' or not authorization.lower().startswith('bearer ')
            or not authorization[7:] or any(c.isspace() for c in authorization[7:]) or not client.headers.get('apikey')):
        raise EvidenceUnavailable('Authenticated evidence storage is unavailable')
    return origin


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Ambiguous JSON object')
        result[key] = value
    return result


async def load_registry_state(client: httpx.AsyncClient, *, artifact_id: UUID, workspace_id: UUID,
                              campaign_id: UUID, purpose: str, clock: Callable[[], datetime]) -> EvidenceRegistryState:
    """Bounded POST with user authority, no redirect/cached state/service fallback."""
    url = authenticated_origin(client).copy_with(path='/rest/v1/rpc/acquisition_evidence_state')
    body = {'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_artifact': str(artifact_id)}
    data = bytearray()
    try:
        async with asyncio.timeout(5):
            async with client.stream('POST', url, json=body, follow_redirects=False, timeout=5,
                                     headers={'Accept-Encoding': 'identity', 'Cache-Control': 'no-store'}) as response:
                length = response.headers.get('content-length')
                if (response.status_code != 200 or response.url != url
                        or response.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json'
                        or response.headers.get('content-encoding', 'identity').lower() != 'identity'
                        or (length is not None and (len(length) > 5 or not length.isascii() or not length.isdigit() or not 0 < int(length) <= 8192))):
                    raise EvidenceUnavailable('Evidence registry is unavailable')
                async for chunk in response.aiter_raw():
                    if len(data) + len(chunk) > 8192:
                        raise EvidenceUnavailable('Evidence registry is unavailable')
                    data.extend(chunk)
                    await asyncio.sleep(0)  # Small buffered chunks must not starve the deadline.
                if length is not None and len(data) != int(length):
                    raise EvidenceUnavailable('Evidence registry is unavailable')
        state = EvidenceRegistryState.model_validate(json.loads(data, object_pairs_hook=unique_json_object))
        now = clock()
        if (now.utcoffset() is None or (state.id, state.workspace_id, state.campaign_id, state.purpose)
                != (artifact_id, workspace_id, campaign_id, purpose)
                or not state.available_at(now) or not state.available_at(state.checked_at)
                or not now - timedelta(seconds=30) <= state.checked_at <= now + timedelta(seconds=5)):
            raise EvidenceUnavailable('Evidence registry is unavailable')
        return state
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, RecursionError):
        raise EvidenceUnavailable('Evidence registry is unavailable') from None


async def verify_registered_evidence(client: httpx.AsyncClient, artifact_id: UUID, *, workspace_id: UUID,
                                     campaign_id: UUID, purpose: str, clock: Callable[[], datetime] = utcnow) -> dict:
    """Registry → exact bytes → fresh registry; observational only, not persisted approval."""
    if (not all(isinstance(value, UUID) for value in (artifact_id, workspace_id, campaign_id))
            or purpose not in ('mail_content', 'mail_destination')):
        raise EvidenceUnavailable('Evidence identity is invalid')
    started = clock()
    if started.utcoffset() is None:
        raise EvidenceUnavailable('Evidence verification clock is invalid')
    try:
        async with asyncio.timeout(25):
            before = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                               campaign_id=campaign_id, purpose=purpose, clock=clock)
            receipt = await verify_evidence_bytes(client, before.descriptor(), workspace_id=workspace_id,
                                                  campaign_id=campaign_id, purpose=purpose, clock=clock)
            after = await load_registry_state(client, artifact_id=artifact_id, workspace_id=workspace_id,
                                              campaign_id=campaign_id, purpose=purpose, clock=clock)
            completed = clock()
            bytes_checked = datetime.fromisoformat(receipt['checked_at'])
            if (before.model_dump(exclude={'checked_at'}) != after.model_dump(exclude={'checked_at'})
                    or after.checked_at < before.checked_at or completed.utcoffset() is None or completed < started
                    or after.checked_at < bytes_checked - timedelta(seconds=5)
                    or completed < bytes_checked or not after.available_at(completed)):
                raise EvidenceUnavailable('Evidence changed during verification')
            return {**receipt, 'registry_verifier_version': 'acquisition-evidence-registry-v1',
                    'retention_policy_id': str(after.retention_policy_id), 'registry_checked_at': after.checked_at.isoformat(),
                    'verification_persisted': False, 'scan_status': 'not_scanned'}
    except TimeoutError:
        raise EvidenceUnavailable('Evidence verification timed out') from None


async def verify_evidence_bytes(client: httpx.AsyncClient, artifact: EvidenceArtifact, *,
                                workspace_id: UUID, campaign_id: UUID, purpose: str,
                                clock: Callable[[], datetime] = utcnow,
                                _observe_chunk: Callable[[bytes], None] | None = None) -> dict:
    # Internal observer receives bounded chunks, never an independently fetched object.
    # Its collected bytes are not trustworthy until the complete receipt validates.
    # Revalidate even model_construct/model_copy inputs from internal callers.
    try:
        artifact = EvidenceArtifact.model_validate(artifact.model_dump())
    except (ValueError, AttributeError, TypeError):
        raise EvidenceUnavailable('Evidence descriptor is invalid') from None
    started = clock()
    if ((artifact.workspace_id, artifact.campaign_id, artifact.purpose) != (workspace_id, campaign_id, purpose)
            or not artifact.available_at(started)):
        raise EvidenceUnavailable('Evidence is unavailable for this review')
    origin = authenticated_origin(client)
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
                    if _observe_chunk is not None:
                        _observe_chunk(chunk)
                    await asyncio.sleep(0)  # Keep wall-clock cancellation effective.
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
