"""Byte-level evidence checks using synthetic streams, never real stored documents."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from schemas.acquisition_evidence import EvidenceArtifact, MAX_EVIDENCE_BYTES
from tools.acquisition_evidence import EvidenceUnavailable, verify_evidence_bytes
from tools.acquisition_store import AcquisitionStore

WORKSPACE = UUID('10000000-0000-4000-8000-000000000001')
CAMPAIGN = UUID('20000000-0000-4000-8000-000000000001')
ARTIFACT = UUID('30000000-0000-4000-8000-000000000001')
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
BODY = b'Synthetic retained mail review evidence\n'
AUTH = {'Authorization': 'Bearer synthetic-user-token', 'apikey': 'synthetic-public-key'}


def descriptor(**changes):
    return EvidenceArtifact(**{'id': ARTIFACT, 'workspace_id': WORKSPACE, 'campaign_id': CAMPAIGN,
        'purpose': 'mail_content', 'sha256': hashlib.sha256(BODY).hexdigest(), 'byte_size': len(BODY),
        'media_type': 'text/plain', 'created_at': NOW - timedelta(days=1), 'retain_until': NOW + timedelta(days=1),
        'revoked_at': None, **changes})


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks=None, error=None):
        self.chunks = [BODY[:9], BODY[9:]] if chunks is None else chunks
        self.closed = False
        self.error = error
        self.reads = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.error:
            raise self.error

    async def aclose(self):
        self.closed = True


def run(artifact=None, *, stream=None, headers=None, status=200, origin='https://storage.example.test/rest/v1/', auth=None,
        workspace=WORKSPACE, campaign=CAMPAIGN, purpose='mail_content', clock=lambda: NOW, via_store=False):
    artifact = artifact or descriptor()
    stream = stream or Stream()
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={'content-type': 'text/plain', **(headers or {})}, stream=stream)
    async def execute():
        async with httpx.AsyncClient(base_url=origin, headers=AUTH if auth is None else auth,
                                    transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            if via_store:
                return await AcquisitionStore(client).verify_evidence(artifact, workspace_id=workspace, campaign_id=campaign, purpose=purpose)
            return await verify_evidence_bytes(client, artifact, workspace_id=workspace, campaign_id=campaign, purpose=purpose, clock=clock)
    return execute, requests, stream


def test_exact_stream_hash_uses_user_authority_and_returns_no_bytes_or_url():
    execute, requests, stream = run(headers={'content-length': str(len(BODY))})
    receipt = asyncio.run(execute())
    assert stream.closed and stream.reads == 2 and len(requests) == 1
    request = requests[0]
    assert request.method == 'GET'
    assert request.url.path == f'/storage/v1/object/authenticated/acquisition-evidence/{WORKSPACE}/{ARTIFACT}/{hashlib.sha256(BODY).hexdigest()}'
    assert request.headers['authorization'] == AUTH['Authorization']
    assert request.headers['apikey'] == AUTH['apikey']
    assert request.headers['accept-encoding'] == 'identity'
    assert receipt['sha256'] == descriptor().sha256 and receipt['byte_size'] == len(BODY)
    assert receipt['status'] == 'bytes_verified' and receipt['execution_authorized'] is False and receipt['content_approved'] is False
    assert not {'url', 'signed_url', 'body', 'token', 'object_name'} & receipt.keys()


@pytest.mark.parametrize('changes', [dict(byte_size=0), dict(byte_size=True), dict(byte_size=MAX_EVIDENCE_BYTES + 1),
    dict(sha256='A' * 64), dict(media_type='text/html'), dict(retain_until=NOW - timedelta(days=2)),
    dict(revoked_at=NOW - timedelta(days=3)), dict(created_at=NOW.replace(tzinfo=None)), dict(object_name='../outside')])
def test_descriptor_rejects_unbounded_or_ambiguous_artifacts(changes):
    with pytest.raises(ValidationError):
        descriptor(**changes)


@pytest.mark.parametrize('changes', [dict(workspace=ARTIFACT), dict(campaign=ARTIFACT), dict(purpose='contract')])
def test_scope_and_purpose_mismatch_prevents_network(changes):
    execute, requests, _ = run(**changes)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


@pytest.mark.parametrize('changes', [dict(revoked_at=NOW), dict(created_at=NOW + timedelta(seconds=1)), dict(retain_until=NOW)])
def test_revoked_future_or_expired_descriptor_prevents_network(changes):
    execute, requests, _ = run(descriptor(**changes))
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


@pytest.mark.parametrize('origin', ['http://storage.example.test/rest/v1/', 'https://u:p@storage.example.test/rest/v1/',
    'https://storage.example.test/rest/v1/?redirect=evil', 'https://storage.example.test/rest/v1/#fragment',
    'https://storage.example.test/other/'])
def test_rejects_noncanonical_origin_without_sending_credentials(origin):
    execute, requests, _ = run(origin=origin)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


@pytest.mark.parametrize('auth', [{}, {'apikey': 'public'}, {'Authorization': 'Bearer x y', 'apikey': 'public'}, {'Authorization': 'Basic secret', 'apikey': 'public'}])
def test_missing_user_auth_never_falls_back_to_service_role(auth, monkeypatch):
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'never-use-this')
    execute, requests, _ = run(auth=auth)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


@pytest.mark.parametrize('status', [206, 301, 302, 307, 401, 403, 404, 429, 500])
def test_rejects_partial_redirect_and_error_responses_without_reading_body(status):
    execute, requests, stream = run(status=status, headers={'location': 'https://attacker.test/private'})
    with pytest.raises(EvidenceUnavailable) as exc: asyncio.run(execute())
    assert len(requests) == 1 and stream.closed and stream.reads == 0
    assert 'attacker' not in str(exc.value) and 'synthetic-user-token' not in str(exc.value)


@pytest.mark.parametrize('headers', [{'content-length': '0'}, {'content-length': '9' * 5000}, {'content-length': '-1'},
    {'content-length': '２'.encode('utf-8')}, {'content-type': 'text/html'}, {'content-encoding': 'gzip'}, {'content-encoding': 'br'}])
def test_bad_metadata_rejected_before_body(headers):
    execute, _, stream = run(headers=headers)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert stream.closed and stream.reads == 0


@pytest.mark.parametrize('chunks', [[BODY[:-1]], [b'x' * len(BODY)], [], [BODY, b'extra', b'never-read']])
def test_missing_tampered_truncated_or_oversized_bytes_fail_closed(chunks):
    execute, _, stream = run(stream=Stream(chunks))
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert stream.closed
    if len(chunks) == 3: assert stream.reads == 2


def test_expiry_and_clock_regression_rechecked_after_download():
    for checked in (NOW + timedelta(days=1), NOW - timedelta(seconds=1)):
        times = iter([NOW, checked])
        execute, _, stream = run(clock=lambda: next(times))
        with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
        assert stream.closed and stream.reads == 2


def test_untrusted_constructed_model_is_revalidated_before_io():
    artifact = descriptor().model_copy(update={'byte_size': MAX_EVIDENCE_BYTES + 1})
    execute, requests, _ = run(artifact)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


def test_stream_failure_is_generic_and_closes_resource():
    execute, _, stream = run(stream=Stream(error=httpx.ReadError('private payload and secret')))
    with pytest.raises(EvidenceUnavailable) as exc: asyncio.run(execute())
    assert str(exc.value) == 'Evidence storage could not be read' and stream.closed


def test_total_timeout_stops_a_trickle_stream(monkeypatch):
    original = asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence.asyncio.timeout', lambda seconds: original(0.001))
    class Slow(Stream):
        async def __aiter__(self):
            await asyncio.sleep(1)
            yield BODY
    execute, _, stream = run(stream=Slow())
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert stream.closed


def test_existing_store_reuses_authenticated_client():
    # The store uses the production default clock, so use a current descriptor.
    current = datetime.now(timezone.utc)
    execute, requests, stream = run(descriptor(created_at=current - timedelta(days=1), retain_until=current + timedelta(days=1)), via_store=True)
    assert asyncio.run(execute())['status'] == 'bytes_verified'
    assert len(requests) == 1 and stream.closed
