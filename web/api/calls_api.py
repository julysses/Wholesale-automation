"""Admin-only Retell initiation with durable claims and explicit AI consent."""
import logging
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from config.settings import settings
from tools.crm import get_supabase_client
from tools.facebook_consent import matching_native_consent, normalize_us_phone
from tools.retell_adapter import CallRequest, RetellAdapter
from tools.operational_alerts import record_provider_alert
from tools.sms_client import _texas_now

router=APIRouter(prefix='/api/calls/retell',tags=['Calls'])
logger=logging.getLogger(__name__)


class StartCall(BaseModel):
    request_id: UUID
    lead_id: UUID
    phone_number: str


def _phone(value):
    try:
        return normalize_us_phone(value)
    except ValueError:
        raise HTTPException(409,'A valid US phone number is required')


def _storage():
    sb=get_supabase_client()
    if sb is None:
        raise HTTPException(503,'Call storage unavailable')
    return sb


def _consented(receipt, phone, lead):
    return matching_native_consent(receipt, phone, lead, 'ai_calls')


def _record(row):
    return {'request_id':row['id'],'call_id':row.get('provider_call_id'),
            'lead_id':row['lead_id'],'phone_number':row['phone_number'],
            'status':row['status'],'provider':'retell'}


def start_call(body: StartCall, operator_id: str):
    # A finite controlled recipient list remains mandatory during acceptance.
    if not settings.ai_calling_live_enabled:
        raise HTTPException(409,'AI calling is disabled pending launch acceptance')
    if not all((settings.retell_api_key,settings.retell_agent_id,settings.retell_from_number,settings.retell_webhook_secret)):
        raise HTTPException(503,'Retell agent, number, API key and signed webhook must be configured')
    phone=_phone(body.phone_number)
    allowed={_phone(item) for item in settings.ai_calling_allowed_recipients.split(',') if item.strip()}
    if phone not in allowed:
        raise HTTPException(403,'Recipient is not authorized for live call testing')
    sb=_storage()
    reference=str(body.request_id)
    existing=sb.table('retell_call_requests').select('*').eq('id',reference).limit(1).execute().data
    if existing:
        row=existing[0]
        if row['lead_id']!=str(body.lead_id) or row['phone_number']!=phone:
            raise HTTPException(409,'Request reference already belongs to a different call')
        if not row.get('provider_call_id'):
            raise HTTPException(409,'Prior call outcome is unresolved; reconcile before another attempt')
        return _record(row) # Never resubmit even after provider deduplication expires.
    rows=sb.table('leads').select('*').eq('id',str(body.lead_id)).limit(1).execute().data
    if not rows:
        raise HTTPException(404,'Lead not found')
    lead=rows[0]
    if lead.get('dnc') is not False or lead.get('ai_calling_paused') is not False:
        raise HTTPException(409,'Lead is suppressed or AI calling remains paused')
    if _phone(lead.get('owner_phone_1'))!=phone:
        raise HTTPException(409,'Requested phone does not match the lead')
    notices=sb.table('app_notifications').select('metadata').eq('lead_id',str(body.lead_id)).order('created_at',desc=True).limit(1).execute().data
    receipt=notices[0].get('metadata',{}).get('consent_receipt') if notices else None
    if not _consented(receipt,phone,lead):
        raise HTTPException(409,'A matching durable AI-call consent receipt is required')
    now=_texas_now()
    if not(settings.tcpa_allowed_start_hour<=now.hour<settings.tcpa_allowed_end_hour) or now.weekday()>=5:
        raise HTTPException(409,'AI calls are allowed on weekdays during configured Central hours')
    safety=sb.rpc('intake_phone_status',{'p_phone':phone,'p_lead':str(body.lead_id),
        'p_property':lead.get('property_address','')}).execute().data
    if not isinstance(safety,dict) or safety.get('suppressed') is not False:
        raise HTTPException(409,'Suppression verification blocked the call')
    claim={'id':reference,'lead_id':str(body.lead_id),'phone_number':phone,
           'requested_by':operator_id,'status':'submitting'}
    try:
        saved=sb.table('retell_call_requests').upsert(claim,on_conflict='id',ignore_duplicates=True).execute().data
    except Exception:
        raise HTTPException(409,'Call claim unavailable or an earlier call remains unresolved')
    if not saved:
        raise HTTPException(409,'Another request already claimed this call reference')
    req=CallRequest(lead_id=str(body.lead_id),phone_number=phone,
        property_address=lead.get('property_address',''),
        owner_name=' '.join(str(lead.get(key) or '') for key in ('owner_first_name','owner_last_name')).strip(),
        request_id=reference)
    try:
        record=RetellAdapter().create_call(req)
        updated=sb.table('retell_call_requests').update({'status':'accepted',
            'provider_call_id':record.call_id}).eq('id',reference).eq('status','submitting').execute().data
        if not updated:
            # A signed callback may have arrived before the creation response.
            observed=sb.table('retell_call_requests').select('*').eq('id',reference).limit(1).execute().data
            if not observed or observed[0].get('provider_call_id')!=record.call_id:
                raise RuntimeError('Provider accepted but receipt could not be persisted')
            return _record(observed[0])
    except Exception as error:
        logger.warning('Retell initiation requires reconciliation (%s)',type(error).__name__)
        try:
            sb.table('retell_call_requests').update({'status':'unknown'}).eq('id',reference).eq('status','submitting').execute()
        except Exception:
            pass # The durable submitting claim still blocks automatic redial.
        try:
            record_provider_alert(sb,'retell',reference,'unknown',str(body.lead_id))
        except Exception:
            logger.exception('Retell reconciliation alert persistence failed')
        raise HTTPException(502,'Call outcome is unconfirmed; reconcile in Retell before retrying')
    return _record({**claim,'status':record.status,'provider_call_id':record.call_id})


def call_status(call_id: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,255}',call_id):
        raise HTTPException(404,'Call not found')
    sb=_storage()
    rows=sb.table('retell_call_requests').select('*').eq('provider_call_id',call_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404,'Call not found in the CRM ledger')
    if not settings.retell_api_key:
        raise HTTPException(503,'Retell status access is not configured')
    try:
        result=RetellAdapter().get_call_status(call_id)
        if result.get('call_id')!=call_id or result.get('call_status') not in ('registered','not_connected','ongoing','ended','error'):
            raise ValueError('Invalid provider status')
        if result['call_status'] in ('ended','error','not_connected'):
            saved=sb.table('retell_call_requests').update({'status':'completed'}).eq('id',rows[0]['id']).execute().data
            if not saved:
                raise RuntimeError('Call completion persistence was not confirmed')
        return {'call_id':call_id,'call_status':result['call_status']}
    except Exception:
        raise HTTPException(502,'Retell status could not be confirmed')


def reconcile_call(payload):
    """Only signed Retell processors may reconcile an ambiguous creation."""
    event=payload.get('event') or payload.get('event_type')
    completed=event in ('call_ended','call_analyzed','retell.call.completed','retell.call.analyzed')
    if not completed and event not in ('call_started','call_answered','retell.call.started','retell.call.answered'):
        return
    call=payload.get('call') or {}
    metadata=call.get('metadata') or {}
    reference=metadata.get('request_id')
    if not reference:
        return # Existing provider calls predate the initiation ledger.
    reference=str(UUID(str(reference)))
    call_id=call.get('call_id') or ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,255}',call_id):
        raise ValueError('Invalid provider call ID')
    sb=_storage()
    for _ in range(2):
        rows=sb.table('retell_call_requests').select('*').eq('id',reference).limit(1).execute().data
        if not rows:
            raise ValueError('Call has no durable initiation claim')
        row=rows[0]
        if row['lead_id']!=metadata.get('lead_id') or row['phone_number']!=_phone(call.get('to_number')):
            raise ValueError('Call does not match the durable claim')
        if row.get('provider_call_id') not in (None,call_id):
            raise ValueError('Conflicting provider call ID')
        if row['status']=='completed':
            return # Out-of-order started events cannot reactivate a closed claim.
        query=sb.table('retell_call_requests').update({'provider_call_id':call_id,
            'status':'completed' if completed else 'accepted'}).eq('id',reference).eq('status',row['status'])
        query=query.eq('provider_call_id',call_id) if row.get('provider_call_id') else query.is_('provider_call_id','null')
        saved=query.execute().data
        if saved:
            return
    raise RuntimeError('Concurrent call reconciliation requires retry')


@router.post('')
async def create(body: StartCall,request: Request):
    return await run_in_threadpool(start_call,body,request.state.user_id)


@router.get('/{call_id}')
async def status(call_id: str):
    return await run_in_threadpool(call_status,call_id)
