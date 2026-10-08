"""Authenticate SendGrid's raw-byte ECDSA signature before committing receipts."""
import base64
import hashlib
import json
import logging
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from config.settings import settings
from tools.crm import get_supabase_client
from tools.operational_alerts import record_provider_alert

router = APIRouter(prefix='/webhooks/sendgrid', tags=['SendGrid'])
logger = logging.getLogger(__name__)
EVENTS = {'processed','deferred','delivered','bounce','dropped','spamreport','unsubscribe',
          'group_unsubscribe','group_resubscribe','open','click'}


def verify_signature(body: bytes, signature: str, timestamp: str) -> None:
    if not settings.sendgrid_webhook_public_key:
        raise HTTPException(503, 'SendGrid verification key not configured')
    try:
        key = serialization.load_der_public_key(base64.b64decode(settings.sendgrid_webhook_public_key, validate=True))
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise ValueError('Not an EC public key')
    except Exception:
        raise HTTPException(503, 'SendGrid verification key invalid')
    try:
        if not timestamp.isascii() or not timestamp.isdigit() or len(timestamp)>16:
            raise ValueError('Invalid timestamp')
        key.verify(base64.b64decode(signature, validate=True), timestamp.encode()+body, ec.ECDSA(hashes.SHA256()))
    except (ValueError, InvalidSignature):
        raise HTTPException(401, 'Invalid SendGrid signature')
    # Retries may arrive much later; durable event IDs make replays harmless.


def normalize_events(raw):
    if not isinstance(raw, list) or len(raw)>1000:
        raise ValueError('Invalid batch')
    result=[]
    for event in raw:
        if not isinstance(event, dict) or event.get('event') not in EVENTS:
            raise ValueError('Invalid event')
        email = event.get('email')
        timestamp = event.get('timestamp')
        if not isinstance(email,str) or not email.strip() or len(email)>320 or '@' not in email:
            raise ValueError('Invalid recipient')
        if isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not 0<=timestamp<=32503680000:
            raise ValueError('Invalid event timestamp')
        event_id = event.get('sg_event_id') or hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
        if not isinstance(event_id,str) or len(event_id)>512:
            raise ValueError('Invalid event ID')
        # Only opaque correlation IDs go into SendGrid custom_args, never seller PII.
        message_id = event.get('app_message_id')
        message_id = str(UUID(message_id)) if message_id else None
        result.append({'event_id':event_id,'email':email.strip().lower(),'timestamp':timestamp,
                       'event':event['event'],'message_id':message_id,
                       'reason':str(event.get('reason',''))[:1000],
                       'provider_message_id':str(event.get('sg_message_id',''))[:512]})
    return result


def persist(events):
    sb=get_supabase_client()
    if sb is None:
        raise HTTPException(503,'Email receipt storage unavailable')
    try:
        data=sb.rpc('record_sendgrid_events',{'p_events':events}).execute().data
        if not isinstance(data,dict) or data.get('saved') is not True:
            raise RuntimeError('Unconfirmed receipt')
        for event in events:
            if event['event'] in ('bounce','dropped','spamreport') and event.get('message_id'):
                tracked=sb.table('email_messages').select('id').eq('id',event['message_id']).limit(1).execute().data
                if tracked:
                    record_provider_alert(sb,'sendgrid',event['message_id'],event['event'])
    except Exception:
        logger.exception('SendGrid receipt transaction failed')
        raise HTTPException(503,'Email receipt storage unavailable')


@router.post('/events')
async def receive(request: Request):
    body=await request.body()
    if len(body)>2_000_000:
        raise HTTPException(413,'Payload too large')
    verify_signature(body,request.headers.get('x-twilio-email-event-webhook-signature',''),
                     request.headers.get('x-twilio-email-event-webhook-timestamp',''))
    try:
        events=normalize_events(json.loads(body))
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(400,'Invalid SendGrid events')
    await run_in_threadpool(persist,events)
    return {'saved':True,'count':len(events)}
