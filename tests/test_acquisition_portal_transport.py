import asyncio
import json

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from tools import acquisition_portal_transport as transport
from tests.test_acquisition_portal_submission import BODY


def request(chunks, *, headers=None, delay=0, disconnect=False):
    events = list(chunks)
    async def receive():
        if delay:
            await asyncio.sleep(delay)
        if disconnect:
            return {'type': 'http.disconnect'}
        chunk = events.pop(0)
        return {'type': 'http.request', 'body': chunk, 'more_body': bool(events)}
    return Request({'type': 'http', 'headers': headers if headers is not None else
                    [(b'content-type', b'application/json')], 'method': 'POST', 'path': '/'}, receive)


def raw():
    return json.dumps({'inquiry': BODY, 'bot_token': 'synthetic-token'}).encode()


def read(req):
    return asyncio.run(transport.read_portal_envelope(req))


def test_valid_stream_keeps_exact_inquiry_identity_and_optional_values():
    body = raw()
    result = read(request([body[:100], body[100:]], headers=[
        (b'content-type', b'application/json; charset=utf-8'), (b'content-length', str(len(body)).encode())]))
    assert str(result.inquiry.submission_id) == BODY['submission_id']
    assert result.inquiry.property.asking_price is None
    assert result.inquiry.selections['human_callback_requested'] is False
    assert result.bot_token == 'synthetic-token'


@pytest.mark.parametrize('headers,status', [
    ([], 415), ([(b'content-type', b'text/plain')], 415),
    ([(b'content-type', b'application/json'), (b'content-type', b'application/json')], 415),
    ([(b'content-encoding', b'gzip')], 415),
    ([(b'content-length', b'32769')], 413),
    ([(b'content-length', b'-1')], 400),
    ([(b'content-length', b'1'), (b'content-length', b'1')], 400),
    ([(b'content-length', b'1'), (b'transfer-encoding', b'chunked')], 400),
    ([(b'content-length', b'1')], 400),
])
def test_header_rejections(headers, status):
    if headers and not any(k == b'content-type' for k, _ in headers):
        headers = [(b'content-type', b'application/json')] + headers
    with pytest.raises(HTTPException) as error:
        read(request([raw()], headers=headers))
    assert error.value.status_code == status
    assert error.value.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('body', [b'', b'\xff', b'null', b'[]', b'{"x":NaN}',
    b'{"bot_token":"secret","bot_token":"other"}',
    b'['*1500+b']'*1500,
    json.dumps({'inquiry': BODY | {'workspace_id': 'private'}, 'bot_token': 'secret'}).encode(),
    json.dumps({'inquiry': BODY, 'bot_token': 'secret', 'p_bot': {}}).encode(),
    json.dumps({'inquiry': BODY, 'bot_token': 'bad token'}).encode(),
    raw().replace(b'"owner"', b'"owner", "authority":"authorized_representative"')])
def test_invalid_or_ambiguous_input_never_echoes_private_values(body):
    with pytest.raises(HTTPException) as error:
        read(request([body]))
    assert error.value.status_code == 422
    assert error.value.detail == 'Review the offer request fields before submitting'
    assert error.value.headers['Cache-Control'] == 'no-store'


def test_stream_limit_without_content_length():
    with pytest.raises(HTTPException) as error:
        read(request([b' '*16000, b' '*17000]))
    assert error.value.status_code == 413


def test_slow_stream_has_total_deadline(monkeypatch):
    monkeypatch.setattr(transport, 'BODY_TIMEOUT_SECONDS', .02)
    with pytest.raises(HTTPException) as error:
        read(request([b' ', raw()], delay=.015))
    assert error.value.status_code == 408


def test_disconnect_rejected():
    with pytest.raises(HTTPException) as error:
        read(request([], disconnect=True))
    assert error.value.status_code == 400
