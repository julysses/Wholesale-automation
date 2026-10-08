"""Operator-entered deal evidence and atomic handoff tasks. No contracts signed or outreach sent."""
from datetime import date
from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client
router=APIRouter(prefix='/api/deals',tags=['Deals'])
class DealFields(BaseModel):
 model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
 deal_name: str | None=Field(default=None,max_length=500)
 stage: Literal['offer_made','under_contract','marketing_to_buyers','buyer_found','assigned','closed','cancelled'] | None=None
 contract_price: float | None=Field(default=None,ge=0,le=100000000)
 arv: float | None=Field(default=None,ge=0,le=100000000)
 repair_estimate: float | None=Field(default=None,ge=0,le=100000000)
 assignment_fee: float | None=Field(default=None,ge=0,le=100000000)
 buyer_price: float | None=Field(default=None,ge=0,le=100000000)
 earnest_money: float | None=Field(default=None,ge=0,le=100000000)
 contract_date: date | None=None
 inspection_deadline: date | None=None
 closing_date: date | None=None
 actual_close_date: date | None=None
 seller_name: str | None=Field(default=None,max_length=500)
 buyer_id: UUID | None=None
 assigned_to: UUID | None=None
 title_company: str | None=Field(default=None,max_length=500)
 title_contact: str | None=Field(default=None,max_length=500)
 title_phone: str | None=Field(default=None,max_length=80)
 psa_doc_url: str | None=Field(default=None,max_length=2000)
 assignment_doc_url: str | None=Field(default=None,max_length=2000)
 notes: str | None=Field(default=None,max_length=10000)
 @field_validator('psa_doc_url','assignment_doc_url')
 @classmethod
 def safe_document_url(cls,value):
  if value is None:return None
  parts=urlsplit(value)
  if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or any(c.isspace() for c in value):raise ValueError('Use a valid HTTPS document link without embedded credentials')
  return value
class NewDeal(DealFields):
 lead_id: UUID
 deal_name: str=Field(min_length=1,max_length=500)
 stage: Literal['offer_made','under_contract','marketing_to_buyers','buyer_found','assigned','closed','cancelled']='offer_made'
class CreateDeal(BaseModel):
 request_id: UUID
 deal: NewDeal
class UpdateDeal(BaseModel):
 expected_updated_at: AwareDatetime
 updates: DealFields

def result(value,reference,creating=False):
 rejected={'X-Deal-Create-Rejected':'true'} if creating else None
 if not isinstance(value,dict):raise HTTPException(503,'Deal outcome is unconfirmed. Retry the same reference and details.')
 if value.get('existing_id'):raise HTTPException(409,f"An active deal already exists for this lead ({value['existing_id']}). Open it in Pipeline.",headers=rejected)
 if value.get('conflict'):raise HTTPException(409,'Deal details or version changed. Recover the pending create or refresh before editing.')
 if value.get('missing'):raise HTTPException(404,'Lead or deal not found',headers=rejected)
 if value.get('invalid'):raise HTTPException(422,'Review owner, buyer, dates and stage evidence. Contract stages need price, contract/closing dates, title company and a signed PSA link; assigned/closed need buyer and assignment link; closed needs actual closing date.')
 row=value.get('deal')
 if not isinstance(row,dict) or row.get('id')!=str(reference) or not row.get('updated_at'):raise HTTPException(503,'Deal outcome is unconfirmed. Retry the same reference and details.')
 return row
async def write(name,params,request):
 operator=getattr(request.state,'user_id',None)
 if not operator:raise HTTPException(401,'Sign in to continue')
 try:
  return await run_in_threadpool(lambda:get_supabase_client().rpc(name,{**params,'p_operator':str(operator)}).execute().data)
 except Exception:raise HTTPException(503,'Deal outcome is unconfirmed. Retry the same reference and details; no outreach was attempted.')
@router.post('')
async def create(body:CreateDeal,request:Request):
 value=await write('create_pipeline_deal',{'p_id':str(body.request_id),'p_payload':body.deal.model_dump(mode='json')},request)
 return result(value,body.request_id,creating=True)
@router.patch('/{deal_id}')
async def update(deal_id:UUID,body:UpdateDeal,request:Request):
 value=await write('update_pipeline_deal',{'p_id':str(deal_id),'p_expected':body.expected_updated_at.isoformat(),'p_patch':body.updates.model_dump(mode='json',exclude_unset=True)},request)
 return result(value,deal_id)
