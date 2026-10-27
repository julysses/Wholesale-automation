"""Bounded signed inbound receiver; stores only an approved metadata projection."""
import json
import os

from fastapi import APIRouter, HTTPException, Request, Response
from starlette.requests import ClientDisconnect

from tools.acquisition_inbound_events import project_inbound_event
from tools.acquisition_inbound_tools import prepare_inbound_tool
from tools.acquisition_inbound_webhook import (
    InboundUnavailable, accept_inbound_event, record_inbound_request, lookup_inbound_property,
    record_inbound_restriction, load_config, verify_signature,
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


async def _authenticated_payload(request: Request):
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
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(400, 'Invalid inbound event') from None
    return config, payload


@router.post('')
async def receive(request: Request):
    config, payload = await _authenticated_payload(request)
    try:
        projection = project_inbound_event(payload, **config.routing)
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid inbound event') from None
    try:
        await accept_inbound_event(config, projection)
    except InboundUnavailable:
        raise HTTPException(503, 'Inbound receipt unconfirmed; retry delivery') from None
    return Response(status_code=204)


@router.post('/tools')
async def receive_tool(request: Request):
    if os.getenv('ACQUISITION_INBOUND_TOOLS_ENABLED', '').lower() != 'true':
        raise HTTPException(503, 'Inbound tools unavailable')
    config, payload = await _authenticated_payload(request)
    try:
        intent = prepare_inbound_tool(payload, **config.routing)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(400, 'Invalid inbound tool request') from None
    if intent['name'] == 'record_contact_restriction':
        if os.getenv('ACQUISITION_INBOUND_RESTRICTIONS_ENABLED', '').lower() != 'true':
            raise HTTPException(503, 'Inbound restrictions unavailable')
        try:
            result = await record_inbound_restriction(config, intent)
        except InboundUnavailable:
            raise HTTPException(503, 'Restriction save unconfirmed; retry the same request') from None
        return {'status': 'restriction_recorded', 'request_id': intent['request_id'],
                'kind': result['kind'], 'channels': result['channels'], 'duplicate': result['duplicate'], 'execution_authorized': False,
                'message': ('Your do-not-contact request has been recorded for this inquiry.'
                            if result['kind'] == 'do_not_contact' else
                            'The callback request for this inquiry has been withdrawn.')}
    if intent['name'] == 'lookup_property':
        if os.getenv('ACQUISITION_INBOUND_LOOKUP_ENABLED', '').lower() != 'true':
            raise HTTPException(503, 'Inbound lookup unavailable')
        try:
            status = await lookup_inbound_property(config, intent)
        except InboundUnavailable:
            raise HTTPException(503, 'Property lookup unavailable; continue collecting seller information') from None
        messages = {
            'incomplete_address': 'Please provide the full property street address, city and state.',
            'no_address_candidate': 'The address could not be matched in this lookup. Hilltop can still review the submitted information.',
            'address_candidate': 'There is a possible address match. Hilltop must review it; property identity and ownership are not verified.',
            'multiple_address_candidates': 'The address needs further review. Please confirm the complete address, including any unit.',
        }
        return {'status': status, 'intake_revision': intent['intake_revision'], 'review_required': True,
                'property_verified': False, 'ownership_verified': False, 'execution_authorized': False,
                'message': messages[status]}
    if intent['name'] == 'submit_seller_intake' and os.getenv('ACQUISITION_INBOUND_INTAKE_ENABLED', '').lower() != 'true':
        raise HTTPException(503, 'Inbound intake unavailable')
    try:
        result = await record_inbound_request(config, intent)
    except InboundUnavailable:
        raise HTTPException(503, 'Request save unconfirmed; retry the same request') from None
    # Everything returned can be spoken by the provider agent. No owner data,
    # internal record IDs, valuation, consent, scheduling or transfer claims.
    return {'status': 'recorded_for_review', 'request_id': intent['request_id'],
            'revision': result['revision'], 'duplicate': result['duplicate'],
            'execution_authorized': False,
            'message': ('Property information is saved for review. An offer has not been approved.'
                        if intent['name'] == 'submit_seller_intake' else
                        'The request is saved for review. Saving it does not schedule a callback or initiate a transfer.')}
