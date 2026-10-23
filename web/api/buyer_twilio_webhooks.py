"""Signature-bound buyer callbacks; delivery/replies remain active while paused."""
from uuid import UUID,NAMESPACE_URL,uuid5
from fastapi import APIRouter,HTTPException,Request,Response
from starlette.concurrency import run_in_threadpool
from config.settings import settings
from tools.crm import get_supabase_client
from tools.retell_sms import recipient_opted_out
from web.api.twilio_webhooks import _verified

router=APIRouter(prefix='/webhooks/buyer-twilio',tags=['Buyer SMS'])

async def receive(request,kind):
    payload=await _verified(request,kind,sender=settings.buyer_sms_from_number,path_prefix='/webhooks/buyer-twilio')
    reference=None
    if kind=='status':
        if len(request.query_params.getlist('message_id'))!=1:raise HTTPException(400,'One message reference is required')
        try:reference=str(UUID(request.query_params['message_id']))
        except ValueError:raise HTTPException(400,'Invalid message reference') from None
    else:payload['crm_opt_out']=recipient_opted_out([{'role':'user','content':payload.get('Body')}])
    key=f"buyer-twilio:{payload['AccountSid']}:{kind}:{payload['MessageSid']}"
    if kind=='status':key+=':'+payload['MessageStatus']
    event=str(uuid5(NAMESPACE_URL,key))
    db=get_supabase_client()
    if db is None:raise HTTPException(503,'Buyer receipt storage unavailable')
    try:
        result=await run_in_threadpool(lambda:db.rpc('record_buyer_sms_event',{'p_event':event,'p_kind':kind,'p_id':reference,'p_payload':payload}).execute().data)
        if not isinstance(result,dict) or (kind=='inbound' and result.get('saved') is not True) or (kind=='status' and result.get('id')!=reference):
            raise ValueError('Buyer receipt unconfirmed')
        if result.get('owner_missing') is True:raise ValueError('Buyer reply owner unconfirmed')
    except Exception:
        raise HTTPException(503,'Buyer receipt or follow-up is unconfirmed; retry this event') from None
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response/>',media_type='application/xml')

@router.post('/status')
async def status(request:Request):return await receive(request,'status')

@router.post('/inbound')
async def inbound(request:Request):return await receive(request,'inbound')
