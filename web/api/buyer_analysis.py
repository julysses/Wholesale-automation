"""Explicit, retained buyer analysis. No background work or automatic paid retries."""
import hashlib
import os
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, StrictBool
from starlette.concurrency import run_in_threadpool
from agents.buyer_intelligence_agent import BuyerIntelligenceAgent, InvalidBuyerClassification
from tools.buyer_intelligence_engine import batch_score_buyers, compute_tags
from tools.crm import get_supabase_client
from web.api.buyer_manual import ReceiptResponse, operator

router = APIRouter(prefix='/api/buyers/analysis', tags=['Buyer analysis'], default_response_class=ReceiptResponse)

class Start(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    kind: Literal['score', 'classify']
    buyer_id: UUID | None = None
    paid_confirmed: StrictBool = False

def rpc(db, name, params):
    try:
        value = db.rpc(name, params).execute().data
        if not isinstance(value, dict): raise ValueError('Unconfirmed analysis receipt')
        return value
    except Exception as exc:
        code = getattr(exc, 'pgcode', None) or getattr(exc, 'code', None)
        if code == '42501': raise HTTPException(403, 'An approved operator must recover their own request') from None
        if code in {'22023','23514','22P02'}: raise HTTPException(409, 'Analysis scope or retained evidence requires review') from None
        raise HTTPException(503, 'Analysis outcome is unconfirmed. Check the original reference; do not create another paid request.') from None

def storage():
    db = get_supabase_client()
    if db is None: raise HTTPException(503, 'Buyer analysis storage is unavailable')
    return db

def status(db, params, offset=0):
    value = rpc(db, 'buyer_analysis_status', {**params, 'p_offset':offset})
    if value.get('id') != params['p_id'] or value.get('state') not in {'unconfirmed','stopped','running','review','complete'}:
        raise HTTPException(503, 'Analysis receipt could not be confirmed')
    if 'kind' in value:
        for field in ('total','processed','applied','failed','stale','missing','unknown','blocked','held','ready','pending','offset'):
            if type(value.get(field)) is not int or value[field] < 0: raise HTTPException(503, 'Analysis totals unconfirmed')
        if (type(value.get('can_run')) is not bool or not isinstance(value.get('next_ids'), list)
            or len(value['next_ids'])>20 or not isinstance(value.get('items'), list) or len(value['items'])>20
            or value['processed']+value['pending'] != value['total']):
            raise HTTPException(503, 'Analysis scope unconfirmed')
        try:
            if len(set(value['next_ids'])) != len(value['next_ids']): raise ValueError()
            for identity in value['next_ids']: UUID(identity)
        except (ValueError, TypeError): raise HTTPException(503, 'Analysis identities unconfirmed') from None
    return value

def retain(db, member, state, patch, metadata):
    params = {**member, 'p_state':state, 'p_patch':patch, 'p_metadata':metadata}
    # Only retry identical database evidence. This never repeats the provider call.
    for attempt in range(2):
        try:
            if rpc(db, 'store_buyer_analysis_result', params).get('saved') is not True:
                raise HTTPException(503, 'Analysis result is unconfirmed')
            return
        except HTTPException as exc:
            if exc.status_code != 503 or attempt: raise

def run_step(db, params):
    current = status(db, params)
    if not current.get('can_run'): return current
    if current['kind'] == 'classify' and not current['ready'] and not os.environ.get('ANTHROPIC_API_KEY','').strip():
        raise HTTPException(503, 'AI classification is unavailable until its provider is configured')
    for buyer in current['next_ids']:
        member = {**params, 'p_buyer':buyer, 'p_claim':str(uuid4())}
        claim = rpc(db, 'claim_buyer_analysis', member)
        if claim.get('stopped') or claim.get('blocked'): continue
        if claim.get('kind') != current['kind'] or type(claim.get('owned')) is not bool:
            raise HTTPException(503, 'Analysis claim is unconfirmed')
        member['p_claim'] = claim['claim_id']
        if claim.get('result') is not None:
            rpc(db, 'apply_buyer_analysis', {**params,'p_buyer':buyer})
            continue
        if current['kind'] == 'classify' and not claim['owned']: continue
        snapshot = claim.get('snapshot')
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('transactions'),list):
            raise HTTPException(503, 'Complete analysis input is unconfirmed')
        row = snapshot.get('buyer'); state = 'valid'; patch = {}; metadata = {}
        when = datetime.fromisoformat(claim['as_of'].replace('Z','+00:00'))
        if row is None:
            state = 'missing'
        elif row.get('id') != buyer:
            raise HTTPException(503, 'Analysis buyer does not match the request')
        elif current['kind'] == 'score':
            patch = batch_score_buyers([row], {buyer:snapshot['transactions']}, as_of=when)[0]
            patch.pop('id')
            metadata = {'as_of':when.isoformat(),'transactions':len(snapshot['transactions'])}
        else:
            authorization = rpc(db, 'authorize_buyer_classification', member)
            if authorization.get('authorized') is not True:
                if authorization.get('state') != 'stale': continue
                state = 'stale'
            else:
                try:
                    agent = BuyerIntelligenceAgent()
                    result = agent.classify_buyer(row, snapshot['transactions'])
                    patch = {'buyer_type_ibie':result.buyer_type_ibie, 'ai_classified_at':when.isoformat(),
                             'tags':compute_tags({**row,'buyer_type_ibie':result.buyer_type_ibie},when.date())}
                    metadata = {'model':agent.MODEL, 'confidence':result.confidence,'reasoning':result.reasoning,
                                'suggested_tags':result.suggested_tags,'provider_reference':getattr(agent,'_last_message_id',''),
                                'response_sha256':hashlib.sha256(result.raw_response.encode()).hexdigest(),
                                'transactions':len(snapshot['transactions']),'as_of':when.isoformat()}
                except InvalidBuyerClassification:
                    state = 'invalid'; metadata = {'reason':'Invalid provider output; existing classification retained'}
                except Exception as exc:
                    code = getattr(exc,'status_code',None)
                    state = 'failed' if isinstance(code,int) and 400<=code<500 and code not in {408,409,429} else 'unknown'
                    metadata = {'reason':'Provider rejected the request' if state=='failed' else 'Provider outcome unknown; paid retry held for review'}
        retain(db, member, state, patch, metadata)
        rpc(db, 'apply_buyer_analysis', {**params,'p_buyer':buyer})
    return status(db, params)

@router.get('/config')
async def config(request:Request):
    operator(request)
    return {'configured':bool(os.environ.get('ANTHROPIC_API_KEY','').strip()),'model':BuyerIntelligenceAgent.MODEL,
            'max_output_tokens':512,'attempts':1,'provider_verified':False}

@router.post('/start')
async def start(body:Start, request:Request):
    params = {'p_id':str(body.request_id),'p_operator':operator(request)}
    db = storage()
    await run_in_threadpool(rpc, db, 'start_buyer_analysis', {**params,'p_kind':body.kind,
        'p_buyer':str(body.buyer_id) if body.buyer_id else None,'p_confirmed':body.paid_confirmed})
    return await run_in_threadpool(status,db,params)

@router.get('/{request_id}')
async def read(request_id:UUID, request:Request, offset:int=Query(0,ge=0,le=20000)):
    return await run_in_threadpool(status,storage(),{'p_id':str(request_id),'p_operator':operator(request)},offset)

@router.post('/{request_id}/run')
async def run(request_id:UUID, request:Request):
    return await run_in_threadpool(run_step,storage(),{'p_id':str(request_id),'p_operator':operator(request)})

@router.post('/{request_id}/cancel')
async def cancel(request_id:UUID, request:Request):
    db=storage(); params={'p_id':str(request_id),'p_operator':operator(request)}
    await run_in_threadpool(rpc,db,'cancel_buyer_analysis',params)
    return await run_in_threadpool(status,db,params)
