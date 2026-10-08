"""Admin-only Retell initiation with durable claims and explicit AI consent."""
import logging
import re
from datetime import datetime, timezone, timedelta
from uuid import UUID, NAMESPACE_URL, uuid5

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
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


class ReviewCall(BaseModel):
    acknowledged: bool


def _receipt(sb, lead_id):
    notice_id=str(uuid5(NAMESPACE_URL,f'wholesaleos:intake-alert:{lead_id}'))
    notices=sb.table('app_notifications').select('metadata').eq('id',notice_id).limit(1).execute().data
    return notices[0].get('metadata',{}).get('consent_receipt') if notices else None


LIMIT_REASONS = {
    'unresolved_attempt': 'An earlier text or call remains active or unresolved',
    'attempt_limit': 'Recipient has reached two automated seller contacts in 30 days',
    'contact_cooldown': 'Recipient was contacted in the last 24 hours',
}


def _recipient_blocker(sb, phone):
    limits=sb.rpc('outreach_recipient_limits',{'p_phone':phone}).execute().data
    if not isinstance(limits,dict) or 'blocker' not in limits:
        raise HTTPException(503,'Recipient contact limits could not be verified')
    reason=limits['blocker']
    return LIMIT_REASONS.get(reason,'Recipient contact limits block calling') if reason else None


def _status_blocker(lead):
    return lead.get('status') in {'dead','dnc','closed','under_contract','responding','hot','qualified_hot','appointment_set','appt_set','offer_made'}


def lead_readiness(lead_id):
    sb=_storage()
    try:
        rows=sb.table('leads').select('*').eq('id',str(lead_id)).limit(1).execute().data
        if not rows:
            raise HTTPException(404,'Lead not found')
        lead=rows[0]
        receipt=_receipt(sb,str(lead_id))
        blockers=[]
        phone=None
        try:phone=_phone(lead.get('owner_phone_1'))
        except HTTPException:blockers.append('A valid US lead phone is required')
        if not settings.ai_calling_live_enabled:blockers.append('AI calling is disabled pending launch acceptance')
        if not all((settings.retell_api_key,settings.retell_agent_id,settings.retell_from_number,settings.retell_webhook_secret)):
            blockers.append('Retell agent, number and signature configuration is incomplete')
        try:
            allowed={_phone(value) for value in settings.ai_calling_allowed_recipients.split(',') if value.strip()}
        except HTTPException:allowed=set()
        if not phone or phone not in allowed:blockers.append('Phone is outside the authorized call recipient list')
        if lead.get('dnc') is not False:blockers.append('Lead is suppressed or its suppression state is unknown')
        if _status_blocker(lead):blockers.append('Lead needs personal follow-up or is no longer eligible for automated calling')
        consent=_consented(receipt,phone,lead) if phone else False
        if not consent:blockers.append('Matching explicit AI-call consent is missing')
        now=_texas_now()
        if now.weekday()>=5 or not settings.tcpa_allowed_start_hour<=now.hour<settings.tcpa_allowed_end_hour:
            blockers.append('Outside weekday calling hours in Central time')
        if phone:
            safety=sb.rpc('intake_phone_status',{'p_phone':phone,'p_lead':str(lead_id),
                'p_property':lead.get('property_address','')}).execute().data
            if not isinstance(safety,dict) or safety.get('suppressed') is not False:
                blockers.append('Phone suppression verification blocks calling')
        if phone:
            contact_blocker=_recipient_blocker(sb,phone)
            if contact_blocker:blockers.append(contact_blocker)
        attempts=[]
        if phone:
            # A second CRM lead can share this phone. Match the database's recipient lock.
            attempts=sb.table('retell_call_requests').select('*').eq('phone_number',phone).neq('status','completed').order('created_at',desc=True).limit(1).execute().data
            if not attempts:
                attempts=sb.table('retell_call_requests').select('*').eq('phone_number',phone).order('created_at',desc=True).limit(1).execute().data
        attempt=_record(attempts[0]) if attempts else None
        if attempt and attempt['status']!='completed':blockers.append('An earlier call remains active or unresolved')
        paused=lead.get('ai_calling_paused') is not False
        return {'lead_id':str(lead_id),'property_address':lead.get('property_address',''),'phone_number':phone,'ai_calling_paused':paused,
            'can_review':not blockers and paused,'can_call':not blockers and not paused,
            'blockers':blockers,'attempt':attempt,
            'consent':{'accepted':consent,'disclosure':receipt.get('ai_calls',{}).get('disclosure') if consent else None,
                       'submitted_at':receipt.get('submitted_at') if consent else None}}
    except HTTPException:raise
    except Exception:
        raise HTTPException(503,'Call readiness could not be verified')


def review_lead(lead_id, acknowledged, operator_id):
    if acknowledged is not True:raise HTTPException(409,'Review the saved AI-call consent before approving')
    readiness=lead_readiness(lead_id)
    if not readiness['can_review']:raise HTTPException(409,'Lead cannot be approved: '+('; '.join(readiness['blockers']) or 'already approved'))
    sb=_storage()
    # Preserve evidence of the operator review before unpausing. This never places a call.
    reference=f"{lead_id}:{operator_id}:{readiness['consent']['submitted_at']}"
    notice={'id':str(uuid5(NAMESPACE_URL,f'wholesaleos:call-review:{reference}')),
        'recipient_role':'admin','type':'pipeline_step','title':'AI-call consent reviewed',
        'body':'An operator reviewed the saved consent. Check current lead readiness before calling.',
        'lead_id':str(lead_id),'action_url':'/leads',
        'metadata':{'source':'ai_call_review','operator_id':operator_id,'consent_submitted_at':readiness['consent']['submitted_at']}}
    try:
        saved=sb.table('app_notifications').upsert(notice,on_conflict='id',ignore_duplicates=True).execute().data
        if not saved and not sb.table('app_notifications').select('id').eq('id',notice['id']).limit(1).execute().data:
            raise RuntimeError('Review receipt unavailable')
        changed=sb.table('leads').update({'ai_calling_paused':False}).eq('id',str(lead_id)).eq('dnc',False).execute().data
        if not changed:raise RuntimeError('Lead approval was not confirmed')
    except Exception:raise HTTPException(503,'Lead approval could not be confirmed')
    return lead_readiness(lead_id)


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
    if lead.get('dnc') is not False or lead.get('ai_calling_paused') is not False or _status_blocker(lead):
        raise HTTPException(409,'Lead is suppressed or AI calling remains paused')
    if _phone(lead.get('owner_phone_1'))!=phone:
        raise HTTPException(409,'Requested phone does not match the lead')
    receipt=_receipt(sb,str(body.lead_id))
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
        result=sb.rpc('claim_retell_call',{'p_id':reference,'p_lead':str(body.lead_id),
            'p_phone':phone,'p_operator':operator_id}).execute().data
        saved=isinstance(result,dict) and result.get('claimed') is True
    except Exception:
        raise HTTPException(409,'Call claim unavailable or an earlier call remains unresolved')
    if not saved:
        reason=result.get('reason') if isinstance(result,dict) else None
        raise HTTPException(409,LIMIT_REASONS.get(reason,'Another request already claimed this call or current limits block it'))
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


@router.get('/lead/{lead_id}')
async def readiness(lead_id: UUID):
    return await run_in_threadpool(lead_readiness,lead_id)


@router.post('/lead/{lead_id}/review')
async def review(lead_id: UUID,body: ReviewCall,request: Request):
    return await run_in_threadpool(review_lead,lead_id,body.acknowledged,request.state.user_id)


class BatchSelection(BaseModel):
    lead_ids: list[UUID] = Field(min_length=1,max_length=5)

class StartBatch(BatchSelection):
    request_id: UUID
    acknowledged: bool = False


def preview_batch(body: BatchSelection):
    rows=[]
    for lead_id in dict.fromkeys(body.lead_ids):
        rows.append(lead_readiness(lead_id))
    phones=[row['phone_number'] for row in rows if row['phone_number']]
    if len(phones)!=len(set(phones)):
        for row in rows:
            row['blockers'].append('Selection includes duplicate recipients; select one lead per phone')
            row['can_call']=row['can_review']=False
    return {'leads':rows,'can_start':all(row['can_call'] for row in rows)}


def batch_status(batch_id, operator_id):
    rows=_storage().table('retell_call_batches').select('*').eq('id',str(batch_id)).eq('requested_by',operator_id).limit(1).execute().data
    if not rows:raise HTTPException(404,'Call batch not found for this operator')
    return rows[0]


def create_batch(body: StartBatch, operator_id):
    sb=_storage()
    lead_ids=[str(value) for value in dict.fromkeys(body.lead_ids)]
    previous=sb.table('retell_call_batches').select('*').eq('id',str(body.request_id)).limit(1).execute().data
    if previous:
        row=previous[0]
        if row['requested_by']!=operator_id or row['lead_ids']!=lead_ids:
            raise HTTPException(409,'Batch reference already belongs to another selection')
        return row  # Repeated creation never dispatches or expands a batch.
    if not body.acknowledged:raise HTTPException(409,'Review every selected lead and saved AI-call consent first')
    state=preview_batch(body)
    if not state['can_start']:raise HTTPException(409,'Selected leads are not all approved and eligible. Refresh the review.')
    outcomes=[{'lead_id':row['lead_id'],'phone_number':row['phone_number'],
               'request_id':str(uuid5(body.request_id,'retell:'+row['lead_id'])),'status':'pending'} for row in state['leads']]
    row={'id':str(body.request_id),'requested_by':operator_id,'lead_ids':lead_ids,'outcomes':outcomes,'status':'ready'}
    try:
        saved=sb.table('retell_call_batches').upsert(row,on_conflict='id',ignore_duplicates=True).execute().data
    except Exception:raise HTTPException(503,'Batch persistence unconfirmed; refresh without a new reference')
    if not saved:
        observed=batch_status(body.request_id,operator_id)
        if observed['lead_ids']!=lead_ids:raise HTTPException(409,'Batch reference belongs to another selection')
        return observed
    return saved[0]


def _finish_batch(sb, batch_id, item, status, reason):
    result=sb.rpc('finish_retell_batch_item',{'p_batch':str(batch_id),'p_reference':item['request_id'],
        'p_status':status,'p_reason':reason}).execute().data
    if not isinstance(result,dict) or result.get('saved') is not True:
        raise HTTPException(503,'Batch outcome unconfirmed; refresh and reconcile before continuing')


def batch_next(batch_id, operator_id):
    batch_status(batch_id,operator_id)
    sb=_storage()
    result=sb.rpc('claim_retell_batch_next',{'p_batch':str(batch_id),'p_operator':operator_id}).execute().data
    if not isinstance(result,dict) or not isinstance(result.get('claimed'),bool):
        raise HTTPException(503,'Batch claim unconfirmed; refresh without resubmitting')
    if not result['claimed']:return batch_status(batch_id,operator_id)
    item=result['item']
    status,reason='unknown','Provider outcome unconfirmed; reconcile before further calls'
    try:
        record=start_call(StartCall(request_id=item['request_id'],lead_id=item['lead_id'],phone_number=item['phone_number']),operator_id)
        if record.get('call_id') and record['status'] not in ('submitting','unknown'):
            status,reason='accepted','Provider accepted. Answered call and completion are verified separately.'
    except HTTPException as exc:
        rows=sb.table('retell_call_requests').select('*').eq('id',item['request_id']).limit(1).execute().data or []
        if not rows and exc.status_code<500:
            status,reason='blocked',str(exc.detail)
        elif rows and rows[0].get('provider_call_id') and rows[0].get('status') in ('accepted','completed'):
            status,reason='accepted','Durable receipt confirms provider acceptance; no resubmission'
    except Exception:
        pass  # The batch claim remains durable; no automatic provider retry.
    _finish_batch(sb,batch_id,item,status,reason)
    if status=='unknown':record_provider_alert(sb,'retell',item['request_id'],'unknown',item['lead_id'])
    return batch_status(batch_id,operator_id)


def reconcile_batch(batch_id,operator_id):
    batch=batch_status(batch_id,operator_id)
    if batch['status'] not in ('processing','review'):return batch
    sb=_storage()
    for item in batch['outcomes']:
        if item['status'] not in ('submitting','unknown'):continue
        rows=sb.table('retell_call_requests').select('*').eq('id',item['request_id']).limit(1).execute().data or []
        if rows and rows[0].get('provider_call_id') and rows[0].get('status') in ('accepted','completed'):
            _finish_batch(sb,batch_id,item,'accepted','Correlated durable provider receipt confirmed; no redial')
        elif batch.get('claimed_at') and datetime.fromisoformat(batch['claimed_at'].replace('Z','+00:00'))<datetime.now(timezone.utc)-timedelta(minutes=5):
            _finish_batch(sb,batch_id,item,'unknown','No confirmed provider outcome; operator reconciliation required')
            record_provider_alert(sb,'retell',item['request_id'],'unknown',item['lead_id'])
    return batch_status(batch_id,operator_id)

@router.post('/batch/preview')
async def batch_preview(body: BatchSelection):
    return await run_in_threadpool(preview_batch,body)

@router.post('/batch')
async def batch_create(body: StartBatch,request: Request):
    return await run_in_threadpool(create_batch,body,request.state.user_id)

@router.get('/batch/recent')
async def recent_batch(request: Request):
    rows=_storage().table('retell_call_batches').select('*').eq('requested_by',request.state.user_id).in_('status',['ready','processing','review']).order('created_at',desc=True).limit(1).execute().data
    return rows[0] if rows else None

@router.get('/batch/{batch_id}')
async def batch_read(batch_id: UUID,request: Request):
    return await run_in_threadpool(batch_status,batch_id,request.state.user_id)

@router.post('/batch/{batch_id}/next')
async def batch_dispatch(batch_id: UUID,request: Request):
    return await run_in_threadpool(batch_next,batch_id,request.state.user_id)

@router.post('/batch/{batch_id}/reconcile')
async def batch_reconcile(batch_id: UUID,request: Request):
    return await run_in_threadpool(reconcile_batch,batch_id,request.state.user_id)

@router.post('/batch/{batch_id}/cancel')
async def batch_cancel(batch_id: UUID,request: Request):
    batch_status(batch_id,request.state.user_id)
    rows=_storage().table('retell_call_batches').update({'status':'canceled'}).eq('id',str(batch_id)).eq('requested_by',request.state.user_id).eq('status','ready').execute().data
    if not rows:raise HTTPException(409,'Batch is already claimed or requires reconciliation; cancellation not confirmed')
    return rows[0]


@router.get('/{call_id}')
async def status(call_id: str):
    return await run_in_threadpool(call_status,call_id)
