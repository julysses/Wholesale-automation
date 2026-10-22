"""Invitation-bound public buyer choices. No messages or enrollment activation."""
import hashlib,json,re
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,StrictBool
from starlette.concurrency import run_in_threadpool
from config.settings import settings
from tools.crm import get_supabase_client

class EnrollmentResponse(JSONResponse):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.headers['Cache-Control']='no-store'
        self.headers['Referrer-Policy']='no-referrer'


router=APIRouter(tags=['Buyer enrollment'],default_response_class=EnrollmentResponse)


def program():
    origin=settings.buyer_enrollment_public_origin.rstrip('/')
    parts=urlsplit(origin)
    brand=settings.buyer_sms_brand.strip();support=settings.buyer_enrollment_support.strip()
    if (parts.scheme!='https' or not parts.hostname or parts.path or parts.query or parts.fragment or parts.username or parts.password
        or not brand or len(brand)>100 or not support or len(support)>200):return None
    disclosure=(f'I agree to receive recurring automated marketing text messages from {brand} about wholesale property opportunities and Buyer Deal Alerts at the mobile number I provide. '
        'Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. '
        'The Buyer SMS Terms and Privacy Statement are available beside this optional choice.')
    privacy=(f'{brand} uses your submitted mobile number, invitation and consent record to manage buyer deal-alert enrollment, review your choice, send requested messages and maintain suppression. '
        'Necessary information may be processed by service providers that operate or secure the program. Mobile information and SMS consent are not sold or shared with third parties or affiliates for their own marketing or promotional purposes. '
        f'Consent and suppression records are retained as needed to operate the program and meet applicable requirements. For privacy questions or requests, contact {support}.')
    terms=(f'{brand} Buyer Deal Alerts provides recurring automated marketing texts about wholesale property opportunities, availability and related buyer follow-up. '
        'Message frequency varies. Message and data rates may apply. Consent is optional and is not a condition of purchase. '
        f'Reply STOP to stop messages or HELP for help. You may also contact {support}. Carriers are not liable for delayed or undelivered messages. '
        'Submitting an enrollment choice does not guarantee activation, property availability, investment returns, financing or a transaction. '
        'No AI-call consent or homeowner property-inquiry consent is granted by this program. A new enrollment request does not clear an existing do-not-contact record.')
    value={'brand':brand,'support':support,'origin':origin,'disclosure':disclosure,'privacy':privacy,'terms':terms,'purpose':'buyer_deal_alerts','revision':'2026-10-22-v1'}
    value['version']=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value


def approved(value):
    return bool(value and settings.buyer_enrollment_policies_reviewed and value['version']==settings.buyer_enrollment_approved_version)


def enabled(value):return approved(value) and settings.buyer_enrollment_enabled


def database():
    db=get_supabase_client()
    if db is None:raise HTTPException(503,'Buyer enrollment is temporarily unavailable')
    return db


def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()


class Capability(BaseModel):
    request_id:UUID
    token:str=Field(pattern=r'^[A-Za-z0-9_-]{43}$')

class Invite(Capability):pass

class Choice(Capability):
    phone:str=Field(min_length=10,max_length=32)
    accepted:StrictBool
    program_version:str=Field(pattern=r'^[0-9a-f]{64}$')
    website:str=Field(default='',max_length=0)


def operator(request):
    identity=getattr(request.state,'user_id',None)
    if not identity:raise HTTPException(401,'Sign in to review enrollment')
    return identity


def call(db,name,params):
    try:return db.rpc(name,params).execute().data
    except Exception as exc:
        code=getattr(exc,'pgcode',None) or getattr(exc,'code',None)
        if code=='42501':raise HTTPException(403,'An approved administrator is required') from None
        if code in {'22023','P0002'}:raise HTTPException(409,'This enrollment link or record is unavailable. Request a new link or contact support.') from None
        raise HTTPException(503,'The saved result is unconfirmed. Keep the same link and reference when retrying.') from None


@router.get('/api/buyer-enrollment/config')
async def public_config():
    value=program()
    return {'available':enabled(value),'program':value if approved(value) else None}


@router.get('/api/buyers/enrollment-program')
async def preview(request:Request):
    operator(request);value=program()
    return {'available':enabled(value),'policies_approved':approved(value),'program':value}


@router.post('/api/buyers/{buyer_id}/enrollment-invite')
async def invite(buyer_id:UUID,req:Invite,request:Request):
    actor=operator(request);value=program()
    if not enabled(value):raise HTTPException(503,'Review the program and approve its exact version before creating enrollment links')
    result=await run_in_threadpool(call,database(),'create_buyer_enrollment_invite',{'p_id':str(req.request_id),'p_buyer':str(buyer_id),'p_operator':actor,'p_hash':token_hash(req.token),'p_program':value})
    if not isinstance(result,dict) or result.get('id')!=str(req.request_id) or result.get('buyer_id')!=str(buyer_id) or result.get('saved') is not True:
        raise HTTPException(503,'Invitation receipt is unconfirmed. Retry the same reference.')
    return result


@router.post('/api/buyer-enrollment/receipt')
async def receipt(req:Capability):
    result=await run_in_threadpool(call,database(),'buyer_enrollment_receipt',{'p_id':str(req.request_id),'p_hash':token_hash(req.token)})
    if not isinstance(result,dict) or result.get('id')!=str(req.request_id) or type(result.get('saved')) is not bool:
        raise HTTPException(503,'Saved choice could not be confirmed')
    return result


@router.post('/api/buyer-enrollment/submit')
async def submit(req:Choice):
    value=program()
    result=await run_in_threadpool(call,database(),'submit_buyer_enrollment',{'p_id':str(req.request_id),'p_hash':token_hash(req.token),
        'p_phone':req.phone,'p_accepted':req.accepted,'p_version':req.program_version,'p_program':value or {},'p_hold':not enabled(value)})
    if not isinstance(result,dict) or result.get('id')!=str(req.request_id) or result.get('saved') is not True or result.get('accepted') is not req.accepted:
        raise HTTPException(503,'Your choice is unconfirmed. Keep this link and retry the same choice.')
    return result


@router.get('/api/buyers/{buyer_id}/enrollment-submissions')
async def submissions(buyer_id:UUID,request:Request,offset:int=0):
    result=await run_in_threadpool(call,database(),'buyer_enrollment_submissions',{'p_buyer':str(buyer_id),'p_operator':operator(request),'p_offset':offset})
    if not isinstance(result,dict) or result.get('buyer_id')!=str(buyer_id) or not isinstance(result.get('submissions'),list) or type(result.get('total')) is not int or result.get('offset')!=offset:
        raise HTTPException(503,'Enrollment history is unconfirmed')
    return result


@router.post('/api/buyers/{buyer_id}/enrollment-submissions/{submission_id}/review')
async def review(buyer_id:UUID,submission_id:UUID,request:Request):
    value=program()
    if not value:raise HTTPException(503,'Program identity is unavailable')
    result=await run_in_threadpool(call,database(),'review_buyer_enrollment',{'p_id':str(submission_id),'p_buyer':str(buyer_id),'p_operator':operator(request),'p_origin':value['origin']})
    if not isinstance(result,dict) or result.get('id')!=str(submission_id) or result.get('buyer_id')!=str(buyer_id) or result.get('saved') is not True:
        raise HTTPException(503,'Consent review receipt is unconfirmed. Inspect saved history before retrying.')
    return result
