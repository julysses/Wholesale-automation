"""Bounded signed inbound receiver; stores only an approved metadata projection."""
import json

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.requests import ClientDisconnect

from tools.acquisition_inbound_events import project_inbound_event
from tools.acquisition_inbound_webhook import (
    InboundUnavailable, accept_inbound_event, load_config, verify_signature,
)

router = APIRouter(prefix='/webhooks/retell/acquisition', tags=['acquisition-webhooks'])
MAX_BODY = 1048576


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON constant')


@router.post('')
async def receive(request: Request):
    try:
        config = load_config()
    except InboundUnavailable:
        raise HTTPException(503, 'Inbound acquisition unavailable') from None
    signatures = request.headers.getlist('x-retell-signature')
    if len(signatures) != 1:
        raise HTTPException(403, 'Invalid inbound signature')
    body = bytearray()
    try:
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY:
                raise HTTPException(413, 'Webhook payload too large')
            body.extend(chunk)
    except ClientDisconnect:
        raise HTTPException(400, 'Incomplete inbound payload') from None
    raw = bytes(body)
    if not verify_signature(raw, signatures[0], config.secret):
        raise HTTPException(403, 'Invalid inbound signature')
    try:
        payload = json.loads(raw.decode('utf-8'), object_pairs_hook=_object, parse_constant=_constant)
        projection = project_inbound_event(payload, **config.routing)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(400, 'Invalid inbound event') from None
    try:
        await accept_inbound_event(config, projection)
    except InboundUnavailable:
        raise HTTPException(503, 'Inbound receipt unconfirmed; retry delivery') from None
    return Response(status_code=204)
