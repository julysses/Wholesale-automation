"""Operator email acceptance test and durable delivery evidence."""
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from config.settings import settings
from tools.crm import get_supabase_client
from tools.email_client import EmailClient

router=APIRouter(prefix='/api/email',tags=['Email'])


class TestEmail(BaseModel):
    message_id: UUID
    recipient: str | None = None


def _test_recipients():
    return list(dict.fromkeys(r.strip().lower() for r in settings.email_allowed_recipients.split(',') if r.strip()))


def _default_recipient(recipients):
    owner=settings.notification_email.strip().lower()
    return owner if owner in recipients else recipients[0] if len(recipients)==1 else None


def evidence():
    sb=get_supabase_client()
    if sb is None:
        raise HTTPException(503,'Email storage unavailable')
    try:
        messages=sb.table('email_messages').select('id,created_at,recipient,subject,status,provider_message_id').order('created_at',desc=True).limit(20).execute().data
        events=sb.table('email_delivery_events').select('event_id,message_id,event,occurred_at,recipient').order('received_at',desc=True).limit(50).execute().data
        return {'live_enabled':settings.email_live_enabled,'test_recipients':settings.email_allowed_recipients,
                'default_recipient':_default_recipient(_test_recipients()),'messages':messages,'events':events}
    except Exception:
        raise HTTPException(503,'Email storage unavailable')


@router.get('/messages')
async def messages():
    return await run_in_threadpool(evidence)


def send_test(message_id, recipient=None):
    recipients=_test_recipients()
    if not recipients or not settings.email_live_enabled:
        raise HTTPException(409,'Enable email with an explicit authorized test recipient list first')
    chosen=recipient.strip().lower() if recipient is not None else None
    if chosen is None:
        chosen=_default_recipient(recipients)
    if chosen is None:
        raise HTTPException(409,'Select an authorized test recipient')
    if chosen not in recipients:
        raise HTTPException(403,'Recipient is not authorized for production testing')
    client=EmailClient('sendgrid')
    accepted=client.send(chosen,'Hilltop Home Co — Production email verification',
        'This is your authorized production email verification from Wholesale Automation. '
        'Please confirm receipt. Reference: '+str(message_id),message_id=str(message_id))
    return {'message_id':str(message_id),'recipient':chosen,'provider_accepted':accepted,
            'detail':'Check delivery events for final delivery. A repeated reference will not resend.'}


@router.post('/test')
async def test_email(body: TestEmail):
    return await run_in_threadpool(send_test,body.message_id,body.recipient)
