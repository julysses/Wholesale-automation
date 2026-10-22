"""Atomic manual CSV imports, preserving existing land work and immutable receipts."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client

router=APIRouter(prefix='/api/land/imports',tags=['Land imports'])

class LandImportRow(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,allow_inf_nan=False)
    owner_name: str=Field(min_length=1,max_length=500)
    property_address: str=Field(min_length=1,max_length=500)
    city: str=Field(min_length=1,max_length=200)
    state: str=Field(default='TX',pattern='^[A-Z]{2}$')
    zip_code: str | None=Field(default=None,max_length=20)
    county: str | None=Field(default=None,max_length=200)
    apn: str | None=Field(default=None,max_length=200)
    external_id: str | None=Field(default=None,max_length=200)
    owner_phone_1: str | None=Field(default=None,max_length=100)
    owner_phone_2: str | None=Field(default=None,max_length=100)
    owner_mailing_address: str | None=Field(default=None,max_length=1000)
    owner_email: str | None=Field(default=None,max_length=500)
    zoning_raw: str | None=Field(default=None,max_length=500)
    lot_size_acres: float | None=Field(default=None,gt=0,le=999999.9999,strict=True)
    lot_size_sqft: int | None=Field(default=None,ge=0,le=2147483647,strict=True)
    tav: float | None=Field(default=None,ge=0,le=9999999999.99,multiple_of=0.01,strict=True)

class LandImportRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    rows: list[LandImportRow]=Field(min_length=1,max_length=10000)

@router.post('')
async def import_rows(body: LandImportRequest,request: Request):
    operator=getattr(request.state,'user_id',None)
    if not operator: raise HTTPException(401,'Sign in to continue')
    rows=[row.model_dump(mode='json',exclude_none=True) for row in body.rows]
    try:
        value=await run_in_threadpool(lambda:get_supabase_client().rpc('import_manual_land_leads',{
            'p_id':str(body.request_id),'p_operator':str(operator),'p_rows':rows}).execute().data)
    except Exception as exc:
        if getattr(exc,'code',None)=='22023':
            raise HTTPException(409,'The import conflicts with saved evidence or ambiguous properties. Review saved land records before retrying.')
        raise HTTPException(503,'Land import outcome is unconfirmed. Check or retry the original import reference.')
    receipt=value.get('receipt') if isinstance(value,dict) else None
    result=receipt.get('result') if isinstance(receipt,dict) else None
    if (not isinstance(receipt,dict) or receipt.get('id')!=str(body.request_id)
        or receipt.get('operator_id')!=str(operator) or receipt.get('payload')!=rows
        or not isinstance(result,dict) or any(type(result.get(k)) is not int or result[k]<0 for k in ['imported','existing'])
        or result['imported']+result['existing']!=len(rows) or not isinstance(result.get('rows'),list)
        or len(result['rows'])!=len(rows) or value.get('outreach_authorized') is not False):
        raise HTTPException(503,'Land import receipt is unconfirmed. Check or retry the original import reference.')
    mappings=result['rows']
    try:
        for mapping in mappings:
            UUID(mapping['land_lead_id'])
            if type(mapping['created']) is not bool: raise ValueError()
            if mapping['created']: UUID(mapping['task_id'])
        if sum(mapping['created'] for mapping in mappings)!=result['imported']: raise ValueError()
    except (KeyError,TypeError,ValueError,AttributeError):
        raise HTTPException(503,'Land import linkage is unconfirmed. Check or retry the original import reference.')
    return value
