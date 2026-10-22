"""Retained single-buyer edits/deletes. No consent grants or provider activity."""
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool, model_validator
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client
from web.api.buyer_manual import ManualBuyer, ReceiptResponse, operator

router=APIRouter(prefix='/api/buyers/mutations',tags=['Buyer changes'],default_response_class=ReceiptResponse)

class BuyerEdit(ManualBuyer):
    active: StrictBool | None = None
    buys_land: StrictBool | None = None
    buys_infill: StrictBool | None = None

class Mutation(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    request_id: UUID
    buyer_id: UUID
    kind: Literal['update','delete']
    expected: dict
    updates: BuyerEdit | None = None

    @model_validator(mode='after')
    def scope(self):
        if self.expected.get('id')!=str(self.buyer_id) or len(json.dumps(self.expected))>70000:
            raise ValueError('Original buyer record is required')
        if (self.kind=='update') != (self.updates is not None):raise ValueError('Updates are required only for edits')
        if self.updates is not None and self.updates.model_fields_set != set(BuyerEdit.model_fields):
            raise ValueError('Submit all editable profile fields explicitly; omitted fields cannot reset saved values')
        return self

def execute(name,params):
    db=get_supabase_client()
    if db is None:raise HTTPException(503,'Buyer storage unavailable; retain the original request')
    try:
        value=db.rpc(name,params).execute().data
        if not isinstance(value,dict) or value.get('id')!=params['p_id'] or value.get('state') not in {'pending','canceled','updated','deleted','stale','missing'}:
            raise ValueError('Unconfirmed buyer mutation')
        if value['state'] not in {'pending','canceled'}:
            if (value.get('kind') not in {'update','delete'} or type(value.get('transaction_count')) is not int
                or type(value.get('current_exists')) is not bool or not value.get('buyer_id')):
                raise ValueError('Unconfirmed buyer result')
            if ('p_buyer' in params and (value['buyer_id'] != params['p_buyer'] or value['kind'] != params['p_kind'])):
                raise ValueError('Buyer request scope changed')
            if value['state'] in {'updated','deleted'} and (not isinstance(value.get('buyer'),dict) or value['buyer'].get('id')!=value['buyer_id']):
                raise ValueError('Unconfirmed buyer snapshot')
        return value
    except Exception as exc:
        code=getattr(exc,'pgcode',None) or getattr(exc,'code',None)
        if code=='42501':raise HTTPException(403,'An approved operator must recover their own request') from None
        if code in {'22023','23505','23514','22P02','22003'}:raise HTTPException(409,'Original details or buyer identity require review. Recover or stop this request.') from None
        raise HTTPException(503,'Buyer change is unconfirmed. Recover the original reference before another change.') from None

@router.post('')
async def mutate(body:Mutation,request:Request):
    return await run_in_threadpool(execute,'mutate_buyer',{'p_id':str(body.request_id),'p_operator':operator(request),
      'p_kind':body.kind,'p_buyer':str(body.buyer_id),'p_expected':body.expected,'p_patch':body.updates.model_dump(mode='json') if body.updates else {}})

@router.get('/{request_id}')
async def receipt(request_id:UUID,request:Request):
    return await run_in_threadpool(execute,'buyer_mutation_receipt',{'p_id':str(request_id),'p_operator':operator(request)})

@router.post('/{request_id}/cancel')
async def cancel(request_id:UUID,request:Request):
    return await run_in_threadpool(execute,'cancel_buyer_mutation',{'p_id':str(request_id),'p_operator':operator(request)})
