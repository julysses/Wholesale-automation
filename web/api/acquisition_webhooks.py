"""Separate signed native-form receiver; disabled until reviewed activation."""
import json
import hmac
import os
import re

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from tools.acquisition_inbox import InboxUnavailable, accept_facebook_events, ingestion_enabled
from tools.facebook_ads_adapter import FacebookAdsAdapter

router = APIRouter(prefix='/webhooks/facebook/acquisition', tags=['acquisition-webhooks'])
MAX_BODY = 1048576


def _adapter():
    if not ingestion_enabled():
        raise HTTPException(503, 'Acquisition ingestion disabled')
    secret = os.getenv('ACQUISITION_FACEBOOK_APP_SECRET', '')
    token = os.getenv('ACQUISITION_FACEBOOK_VERIFY_TOKEN', '')
    if not secret.strip() or not token.strip():
        raise HTTPException(503, 'Acquisition webhook configuration unavailable')
    return FacebookAdsAdapter(secret, '', token)


def _events(payload):
    if not isinstance(payload, dict) or payload.get('object') != 'page':
        raise ValueError('Invalid Page envelope')
    parsed = FacebookAdsAdapter('', '', '').parse_lead_webhook(payload)
    if len(parsed) > 100:
        raise ValueError('Too many native events')
    events = []
    for entry in parsed:
        event = {}
        for name in ('page_id', 'leadgen_id', 'form_id', 'ad_id', 'adgroup_id', 'campaign_id'):
            value = getattr(entry, name)
            if value is None and name not in ('page_id', 'leadgen_id', 'form_id'):
                continue
            if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'[0-9]{1,200}', str(value)):
                raise ValueError('Invalid native event identity')
            event[name] = str(value)
        if entry.created_time is not None:
            if type(entry.created_time) is not int or entry.created_time < 0:
                raise ValueError('Invalid native event time')
            event['created_time'] = entry.created_time
        events.append(event)
    return events


@router.get('')
async def verify(hub_mode: str = Query('', alias='hub.mode'),
                 hub_verify_token: str = Query('', alias='hub.verify_token'),
                 hub_challenge: str = Query('', alias='hub.challenge')):
    challenge = _adapter().verify_webhook_challenge(hub_mode, hub_verify_token, hub_challenge)
    if challenge is None:
        raise HTTPException(403, 'Invalid acquisition verification challenge')
    return PlainTextResponse(challenge)


@router.post('')
async def receive(request: Request, signature: str = Header('', alias='X-Hub-Signature-256')):
    adapter = _adapter()
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            raise HTTPException(413, 'Webhook payload too large')
        body.extend(chunk)
    raw = bytes(body)
    if not adapter.verify_webhook_signature(raw, signature):
        raise HTTPException(403, 'Invalid Facebook signature')
    try:
        events = _events(json.loads(raw))
    except (ValueError, TypeError, UnicodeDecodeError):
        raise HTTPException(400, 'Invalid Facebook event envelope') from None
    if not events:
        return {'received': True, 'events': 0}
    try:
        count = await accept_facebook_events(events, raw)
    except InboxUnavailable:
        # Retryable; do not expose database/provider errors or private identities.
        raise HTTPException(503, 'Receipt persistence unconfirmed; retry delivery') from None
    return {'received': True, 'events': count}


@router.post('/worker')
async def run_worker(authorization: str = Header('')):
    secret = os.getenv('ACQUISITION_FACEBOOK_WORKER_TRIGGER_SECRET', '')
    if not secret.strip():
        raise HTTPException(503, 'Acquisition worker trigger unavailable')
    if not hmac.compare_digest(authorization.encode(), ('Bearer ' + secret).encode()):
        raise HTTPException(403, 'Invalid worker authorization')
    from tools.acquisition_facebook_worker import WorkerUnavailable, process_facebook_inquiry
    try:
        return await process_facebook_inquiry()
    except WorkerUnavailable:
        raise HTTPException(503, 'Acquisition worker operation unconfirmed') from None
