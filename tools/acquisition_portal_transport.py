"""Bounded seller request parsing; not a mounted route or activation control."""
import asyncio
import json
from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import StringConstraints, ValidationError
from starlette.requests import ClientDisconnect

from schemas.acquisition_online_offer import Exact, OnlineOfferRequest

MAX_BODY_BYTES = 32768
BODY_TIMEOUT_SECONDS = 5.0


class PortalEnvelope(Exact):
    inquiry: OnlineOfferRequest
    bot_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2048,
                                               pattern=r'^[!-~]+$')]


def _error(status, message):
    return HTTPException(status, message, headers={'Cache-Control': 'no-store'})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError('Non-JSON number')


async def read_portal_envelope(request: Request) -> PortalEnvelope:
    """Consume once, under byte and wall-clock limits, without echoing private input.

    Call only after deployment/route gates. Does not trust forwarded headers,
    derive caller identity, reserve capacity, contact providers or save an inquiry.
    A receiver must subsequently use durable admission and verified completion.
    """
    headers = request.headers
    content_types = headers.getlist('content-type')
    if len(content_types) != 1 or content_types[0].lower().strip() not in (
            'application/json', 'application/json; charset=utf-8'):
        raise _error(415, 'Send the offer request as UTF-8 JSON')
    if headers.getlist('content-encoding'):
        raise _error(415, 'Compressed requests are not supported')
    lengths = headers.getlist('content-length')
    expected = None
    if lengths:
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 10:
            raise _error(400, 'Request length is invalid')
        expected = int(lengths[0])
        if expected > MAX_BODY_BYTES:
            raise _error(413, 'Offer request is too large')
    # ASGI servers own transfer framing; ambiguous length plus transfer encoding
    # is rejected here as well, never interpreted by application code.
    if lengths and headers.getlist('transfer-encoding'):
        raise _error(400, 'Request framing is invalid')

    async def consume():
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                raise _error(413, 'Offer request is too large')
            body.extend(chunk)
        return body

    try:
        raw = await asyncio.wait_for(consume(), timeout=BODY_TIMEOUT_SECONDS)
    except (TimeoutError, asyncio.TimeoutError):
        raise _error(408, 'Request timed out; retry the same inquiry') from None
    except ClientDisconnect:
        raise _error(400, 'Request upload was interrupted') from None
    if expected is not None and len(raw) != expected:
        raise _error(400, 'Request length does not match its content')
    try:
        parsed = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant)
        return PortalEnvelope.model_validate(parsed)
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError, ValidationError):
        # Pydantic/JSON errors may contain names, contact details or bot tokens.
        raise _error(422, 'Review the offer request fields before submitting') from None
