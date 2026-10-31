import asyncio
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import httpx
import pytest

from tools.acquisition_portal_bot import (ACTION, SITEVERIFY, BotConfig, BotRejected, BotUnavailable,
                                          configured_bot, verify_portal_bot)

ID = UUID('fd000000-0000-4000-8000-000000000001')
HASH = 'a' * 64
SECRET = 'synthetic-secret-not-live'
TOKEN = 'synthetic-token-not-live'
CONFIG = BotConfig(SECRET, 'seller.example.test')


def success(**patch):
    return {'success': True, 'hostname': CONFIG.hostname, 'action': ACTION, 'cdata': str(ID),
            'challenge_ts': datetime.now(timezone.utc).isoformat(), 'error-codes': [], **patch}


def run(handler, **kwargs):
    return asyncio.run(verify_portal_bot(CONFIG, token=kwargs.pop('token', TOKEN), submission_id=kwargs.pop('submission_id', ID),
        request_hash=kwargs.pop('request_hash', HASH), transport=httpx.MockTransport(handler), **kwargs))


def test_exact_provider_retry_preserves_identity_without_sharing_seller_or_ip_data():
    requests = []
    def handler(request):
        assert str(request.url) == SITEVERIFY and request.method == 'POST'
        assert 'authorization' not in request.headers and 'apikey' not in request.headers
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=success())
    first = run(handler); second = run(handler)
    assert requests[0] == requests[1]
    assert set(requests[0]) == {'secret', 'response', 'idempotency_key'}
    assert first.verification_id == second.verification_id
    assert first.submission_id == ID and first.request_hash == HASH
    assert first.verified_at < first.expires_at
    assert TOKEN not in repr(first) and SECRET not in repr(CONFIG)
    run(handler, request_hash='b' * 64)
    assert requests[-1]['idempotency_key'] != requests[0]['idempotency_key']
    run(handler, token='new-synthetic-token')
    assert requests[-1]['idempotency_key'] not in {requests[0]['idempotency_key'], requests[-2]['idempotency_key']}


@pytest.mark.parametrize('patch', [
    {'success': False, 'error-codes': ['timeout-or-duplicate']}, {'success': False, 'error-codes': ['invalid-input-response']},
    {'hostname': 'different.example.test'}, {'hostname': 'seller.example.test.evil.test'}, {'action': 'login'},
    {'cdata': str(UUID(int=1))},
])
def test_rejects_unverified_wrong_context_or_stale_challenge(patch):
    with pytest.raises(BotRejected):run(lambda _:httpx.Response(200,json=success(**patch)))


@pytest.mark.parametrize('offset,accepted', [(-301, False), (-300, False), (-299, True), (5, True), (6, False), (60, False)])
def test_challenge_age_boundaries_use_verification_time(monkeypatch, offset, accepted):
    import tools.acquisition_portal_bot as adapter
    now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(adapter, 'datetime', Clock)
    challenge = (now + timedelta(seconds=offset)).isoformat()
    handler = lambda _: httpx.Response(200, json=success(challenge_ts=challenge))
    if accepted:
        assert run(handler).verified_at == now
    else:
        with pytest.raises(BotRejected):
            run(handler)


@pytest.mark.parametrize('value', [None, [], {}, {'success': 1}, {'success': 'true'},
    success(challenge_ts='invalid'), success(challenge_ts='2026-10-31T12:00:00'), success(**{'error-codes': ['unexpected']}),
    success(**{'error-codes': 'invalid'}), {'success':False,'error-codes':['internal-error']},
    {'success':False,'error-codes':['invalid-input-secret']}])
def test_uncertain_provider_results_never_verify(value):
    with pytest.raises(BotUnavailable):run(lambda _:httpx.Response(200,json=value))


@pytest.mark.parametrize('response', [httpx.Response(302,headers={'Location':'https://elsewhere.example.test'}),
    httpx.Response(429),httpx.Response(503),httpx.Response(200,text='secret provider detail'),
    httpx.Response(200,content=b'{}',headers={'content-type':'application/json','content-length':'999999'}),
    httpx.Response(200,content=b'{}',headers={'content-type':'application/json','content-length':'invalid'}),
    httpx.Response(200,content=b'{"success":true,"success":false}',headers={'content-type':'application/json'}),
    httpx.Response(200,content=b' '*16385,headers={'content-type':'application/json'}),
])
def test_transport_status_bounds_and_ambiguous_json_fail_closed(response):
    calls=[]
    with pytest.raises(BotUnavailable) as caught:
        run(lambda request:(calls.append(str(request.url)) or response))
    assert calls == [SITEVERIFY]
    assert SECRET not in str(caught.value) and TOKEN not in str(caught.value)
    assert 'secret provider detail' not in str(caught.value)


@pytest.mark.parametrize('token', ['', 'x'*2049, 'white space', '\nsecret', 'é'])
def test_invalid_token_does_not_reach_provider(token):
    def forbidden(_):raise AssertionError('Provider was reached')
    with pytest.raises(BotRejected):run(forbidden,token=token)


def test_provider_timeout_is_uncertain_and_not_automatically_retried():
    count=[]
    def timeout(request):
        count.append(request)
        raise httpx.ReadTimeout('private provider diagnostic '+SECRET)
    with pytest.raises(BotUnavailable) as caught:run(timeout)
    assert len(count)==1 and SECRET not in str(caught.value)


def test_disabled_or_incomplete_configuration_is_unavailable():
    for env in ({},{'ACQUISITION_PORTAL_BOT_ENABLED':'false'},{'ACQUISITION_PORTAL_BOT_ENABLED':'true'}):
        with pytest.raises(BotUnavailable):configured_bot(env)
    env={'ACQUISITION_PORTAL_BOT_ENABLED':'true','ACQUISITION_PORTAL_TURNSTILE_SECRET':SECRET,
         'ACQUISITION_PORTAL_HOSTNAME':CONFIG.hostname}
    assert configured_bot(env)==CONFIG
    for host in ('https://seller.example.test','*.example.test','seller.example.test:443','seller.example.test/path',''):
        with pytest.raises(BotUnavailable):BotConfig(SECRET,host)

class Chunked(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks=chunks
        self.consumed=0
    async def __aiter__(self):
        for chunk in self.chunks:
            self.consumed+=1
            yield chunk


def test_chunked_response_is_bounded_without_trusting_content_length():
    stream=Chunked([b' '*10000,b' '*10000,b'not-read'])
    with pytest.raises(BotUnavailable):
        run(lambda _:httpx.Response(200,stream=stream,headers={'Content-Type':'application/json'}))
    assert stream.consumed==2


def test_huge_content_length_is_rejected_before_reading_or_integer_conversion():
    stream=Chunked([b'not-read'])
    with pytest.raises(BotUnavailable):
        run(lambda _:httpx.Response(200,stream=stream,headers={'Content-Type':'application/json','Content-Length':'9'*5000}))
    assert stream.consumed==0


def test_encoded_response_is_rejected_before_reading():
    stream=Chunked([b'not-read'])
    with pytest.raises(BotUnavailable):
        run(lambda _:httpx.Response(200,stream=stream,headers={'Content-Type':'application/json','Content-Encoding':'gzip'}))
    assert stream.consumed==0


def test_total_deadline_stops_a_slow_stream_without_retry(monkeypatch):
    import tools.acquisition_portal_bot as adapter
    timeout=asyncio.timeout
    monkeypatch.setattr(adapter.asyncio,'timeout',lambda _:timeout(.01))
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(.1)
            yield b'{}'
    calls=[]
    with pytest.raises(BotUnavailable):
        run(lambda request:(calls.append(request) or httpx.Response(200,stream=Slow(),headers={'Content-Type':'application/json'})))
    assert len(calls)==1


@pytest.mark.parametrize('identity,request_hash', [('not-a-uuid',HASH),(ID,'bad-hash'),(ID,None)])
def test_unprepared_request_identity_never_reaches_provider(identity,request_hash):
    def forbidden(_):raise AssertionError('Provider was reached')
    with pytest.raises(BotUnavailable):run(forbidden,submission_id=identity,request_hash=request_hash)
