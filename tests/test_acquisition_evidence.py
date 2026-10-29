"""Byte-level evidence checks using synthetic streams, never real stored documents."""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from schemas.acquisition_evidence import EvidenceArtifact, MAX_EVIDENCE_BYTES
from tools.acquisition_evidence import EvidenceUnavailable, verify_evidence_bytes, verify_registered_evidence
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
        workspace=WORKSPACE, campaign=CAMPAIGN, purpose='mail_content', clock=lambda: NOW):
    artifact = artifact or descriptor()
    stream = stream or Stream()
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={'content-type': 'text/plain', **(headers or {})}, stream=stream)
    async def execute():
        async with httpx.AsyncClient(base_url=origin, headers=AUTH if auth is None else auth,
                                    transport=httpx.MockTransport(handler), follow_redirects=True) as client:
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


def test_small_chunks_cannot_starve_byte_read_deadline(monkeypatch):
    original = asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence.asyncio.timeout', lambda seconds: original(0.001))
    body = b'x' * 100000
    class ChunkFlood(Stream):
        async def __aiter__(self):
            for value in body:
                self.reads += 1
                yield bytes([value])
    stream = ChunkFlood()
    artifact = descriptor(byte_size=len(body), sha256=hashlib.sha256(body).hexdigest())
    execute, _, _ = run(artifact, stream=stream)
    with pytest.raises(EvidenceUnavailable, match='storage could not be read'):
        asyncio.run(execute())
    assert stream.closed and stream.reads < len(body)


def test_small_chunks_cannot_starve_registry_read_deadline(monkeypatch):
    from tools.acquisition_evidence import load_registry_state
    original = asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence.asyncio.timeout', lambda seconds: original(0.001))
    body = b' ' * 4096 + json.dumps(registry_payload()).encode()
    class ChunkFlood(Stream):
        async def __aiter__(self):
            for value in body:
                self.reads += 1
                yield bytes([value])
    stream = ChunkFlood()
    async def execute():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/', headers=AUTH,
                transport=httpx.MockTransport(lambda request: httpx.Response(200,
                    headers={'content-type':'application/json'}, stream=stream))) as client:
            return await load_registry_state(client, artifact_id=ARTIFACT, workspace_id=WORKSPACE,
                                             campaign_id=CAMPAIGN, purpose='mail_content', clock=lambda:NOW)
    with pytest.raises(EvidenceUnavailable, match='registry is unavailable'):
        asyncio.run(execute())
    assert stream.closed and stream.reads < len(body)


def registry_payload(artifact=None, checked=NOW, **changes):
    artifact = artifact or descriptor()
    data = artifact.model_dump(mode='json')
    data['artifact_id'] = data.pop('id')
    data['expected_sha256'] = data.pop('sha256')
    data['expected_byte_size'] = data.pop('byte_size')
    return {**data, 'retention_policy_id': str(CAMPAIGN), 'status': 'pending_verification',
            'bytes_verified': False, 'content_approved': False, 'execution_authorized': False,
            'checked_at': checked.isoformat(), **changes}


def registered_run(*, states=None, clock=lambda: NOW, origin='https://storage.example.test/rest/v1/',
                   registry_status=200, registry_headers=None, raw=None, via_store=False,
                   artifact_id=ARTIFACT, body=BODY):
    states = [registry_payload(), registry_payload()] if states is None else states
    requests, streams = [], []
    index = 0
    def handler(request):
        nonlocal index
        requests.append(request)
        if request.method == 'POST':
            assert request.url.path == '/rest/v1/rpc/acquisition_evidence_state'
            assert json.loads(request.content) == {'p_workspace': str(WORKSPACE), 'p_campaign': str(CAMPAIGN), 'p_artifact': str(artifact_id)}
            stream = Stream(chunks=[raw if raw is not None else json.dumps(states[index]).encode()])
            index += 1
            streams.append(stream)
            return httpx.Response(registry_status, stream=stream, headers={'content-type': 'application/json', **(registry_headers or {})})
        stream = Stream(chunks=[body]); streams.append(stream)
        return httpx.Response(200, stream=stream, headers={'content-type': 'text/plain'})
    async def execute():
        async with httpx.AsyncClient(base_url=origin, headers=AUTH, transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            if via_store:
                return await AcquisitionStore(client).verify_evidence(artifact_id, workspace_id=WORKSPACE, campaign_id=CAMPAIGN, purpose='mail_content')
            return await verify_registered_evidence(client, artifact_id, workspace_id=WORKSPACE, campaign_id=CAMPAIGN, purpose='mail_content', clock=clock)
    return execute, requests, streams


def test_registered_verifier_resolves_then_rechecks_exact_identity_without_persistence():
    execute, requests, streams = registered_run()
    receipt = asyncio.run(execute())
    assert [r.method for r in requests] == ['POST', 'GET', 'POST']
    assert all(s.closed for s in streams)
    assert all(r.headers['authorization'] == AUTH['Authorization'] and r.headers['apikey'] == AUTH['apikey'] for r in requests)
    assert all(r.headers['cache-control'] == 'no-store' and r.headers['accept-encoding'] == 'identity' for r in requests)
    assert receipt['status'] == 'bytes_verified' and receipt['verification_persisted'] is False
    assert receipt['scan_status'] == 'not_scanned' and receipt['content_approved'] is False and receipt['execution_authorized'] is False
    assert receipt['retention_policy_id'] == str(CAMPAIGN) and receipt['registry_checked_at'] == NOW.isoformat()
    assert not {'url','signed_url','body','token','object_name'} & receipt.keys()


@pytest.mark.parametrize('changes', [
    {'workspace_id': str(ARTIFACT)}, {'campaign_id': str(ARTIFACT)}, {'artifact_id': str(CAMPAIGN)},
    {'purpose': 'mail_destination'}, {'status': 'revoked'}, {'status': 'expired'}, {'status': 'policy_review_required'},
    {'revoked_at': NOW.isoformat()}, {'retain_until': NOW.isoformat()}, {'created_at': (NOW+timedelta(seconds=1)).isoformat()},
    {'bytes_verified': True}, {'content_approved': True}, {'execution_authorized': True}, {'bytes_verified': 0},
    {'expected_byte_size': True}, {'expected_byte_size': MAX_EVIDENCE_BYTES+1}, {'expected_sha256': 'invalid'},
    {'media_type': 'text/html'}, {'checked_at': (NOW-timedelta(seconds=31)).isoformat()},
    {'checked_at': (NOW+timedelta(seconds=6)).isoformat()}, {'checked_at': NOW.replace(tzinfo=None).isoformat()},
    {'retention_policy_id': None}, {'object_url': 'https://attacker.example/private'},
])
def test_invalid_registry_state_stops_before_download(changes):
    execute, requests, streams = registered_run(states=[registry_payload(**changes)])
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert len(requests) == 1 and streams[0].closed


@pytest.mark.parametrize('changes', [
    {'status': 'revoked'}, {'status': 'policy_review_required'}, {'status': 'expired'},
    {'expected_sha256': 'b'*64}, {'expected_byte_size': len(BODY)+1}, {'retention_policy_id': str(ARTIFACT)},
    {'retain_until': (NOW+timedelta(days=2)).isoformat()}, {'created_at': (NOW-timedelta(days=2)).isoformat()},
    {'checked_at': (NOW-timedelta(seconds=1)).isoformat()},
])
def test_changed_or_revoked_registry_after_bytes_produces_no_receipt(changes):
    execute, requests, streams = registered_run(states=[registry_payload(), registry_payload(**changes)])
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert [r.method for r in requests] == ['POST','GET','POST'] and all(s.closed for s in streams)


@pytest.mark.parametrize('status', [206,301,302,307,401,403,404,429,500])
def test_registry_failures_and_redirects_never_read_body_or_follow_location(status):
    execute, requests, streams = registered_run(registry_status=status, registry_headers={'location':'https://attacker.example/private'})
    with pytest.raises(EvidenceUnavailable) as error: asyncio.run(execute())
    assert len(requests) == 1 and streams[0].closed and streams[0].reads == 0
    assert str(error.value) == 'Evidence registry is unavailable'


@pytest.mark.parametrize('raw', [b'[]', b'null', b'{}', b'invalid', b'x'*8193,
    b'{"status":"expired","status":"pending_verification"}', b'['*2000+b']'*2000])
def test_registry_payload_is_bounded_unambiguous_and_strict(raw):
    execute, requests, streams = registered_run(raw=raw)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert len(requests) == 1 and streams[0].closed


@pytest.mark.parametrize('headers', [{'content-length':'8193'}, {'content-length':'1'}, {'content-length':'-1'},
    {'content-length':'0'}, {'content-encoding':'gzip'}, {'content-type':'text/html'}])
def test_registry_rejects_unbounded_or_incompatible_response_metadata(headers):
    execute, requests, streams = registered_run(registry_headers=headers)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert len(requests) == 1 and streams[0].closed


@pytest.mark.parametrize('identity', [str(ARTIFACT), descriptor(), None, {'artifact_id': str(ARTIFACT)}])
def test_store_seam_cannot_accept_untrusted_expectations(identity):
    execute, requests, _ = registered_run(artifact_id=identity, via_store=True)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


def test_registry_origin_is_checked_before_sending_user_credentials():
    execute, requests, _ = registered_run(origin='https://user:secret@storage.example.test/rest/v1/')
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert requests == []


def test_byte_mismatch_never_reaches_final_registry_state():
    execute, requests, streams = registered_run(body=b'wrong bytes')
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert [r.method for r in requests] == ['POST','GET'] and all(s.closed for s in streams)


def test_existing_store_resolves_registry_using_same_user_client():
    current = datetime.now(timezone.utc)
    state = registry_payload(descriptor(created_at=current-timedelta(days=1), retain_until=current+timedelta(days=1)), checked=current)
    execute, requests, streams = registered_run(states=[state,state], via_store=True)
    assert asyncio.run(execute())['status'] == 'bytes_verified'
    assert len(requests) == 3 and all(s.closed for s in streams)


@pytest.mark.parametrize('completed', [NOW-timedelta(seconds=1), NOW+timedelta(days=1)])
def test_registry_verification_rechecks_completion_clock_and_retention(completed):
    times=iter([NOW,NOW,NOW,NOW,NOW,completed])
    execute, requests, streams=registered_run(clock=lambda:next(times))
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert len(requests)==3 and all(s.closed for s in streams)


def test_registry_orchestration_has_a_total_deadline(monkeypatch):
    original=asyncio.timeout
    monkeypatch.setattr('tools.acquisition_evidence.asyncio.timeout',lambda seconds:original(0.01 if seconds==25 else seconds))
    async def stalled(*args,**kwargs):
        await asyncio.sleep(1)
    monkeypatch.setattr('tools.acquisition_evidence.verify_evidence_bytes',stalled)
    execute, requests, streams=registered_run()
    with pytest.raises(EvidenceUnavailable,match='timed out'):asyncio.run(execute())
    assert len(requests)==1 and streams[0].closed


def test_final_registry_check_cannot_predate_bytes_beyond_clock_skew():
    later=NOW+timedelta(seconds=6)
    times=iter([NOW,NOW,NOW,later,later,later])
    execute, requests, streams=registered_run(clock=lambda:next(times))
    with pytest.raises(EvidenceUnavailable):asyncio.run(execute())
    assert len(requests)==3 and all(s.closed for s in streams)
