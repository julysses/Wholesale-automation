"""Authenticated contract draft save/history; no signing or disposition actions."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from tools.acquisition_store import acquisition_store

router=APIRouter(prefix='/workspaces/{workspace_id}/contracts/drafts')


class Exact(BaseModel):
    model_config=ConfigDict(extra='forbid')


class ContractDraftRequest(Exact):
    id: UUID
    offer_id: UUID
    offer_sequence: int=Field(strict=True,ge=1,le=2147483647)
    owner_relationship_id: UUID
    name: str=Field(strict=True,min_length=1,max_length=500)

    @field_validator('name')
    @classmethod
    def draft_name(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('Use a nonblank plain-text draft name')
        return value


class ContractDraftReceipt(Exact):
    deal_id: UUID
    version: int=Field(strict=True,ge=1,le=1)
    status: Literal['draft']
    duplicate: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def no_execution(self):
        if self.execution_authorized:
            raise ValueError('A draft cannot authorize execution')
        return self


class ContractDraftRecord(Exact):
    id: UUID
    workspace_id: UUID
    lead_id: UUID
    deal_name: str=Field(strict=True,min_length=1,max_length=500)
    acquisition_status: Literal['draft','pending_signature','executed']
    acquisition_version: int=Field(strict=True,ge=1,le=2147483647)
    acquisition_property_id: UUID
    acquisition_owner_relationship_id: UUID
    acquisition_offer_id: UUID
    acquisition_offer_sequence: int=Field(strict=True,ge=1)
    created_by: UUID
    created_at: AwareDatetime


async def request(store,*args,**kwargs):
    try:
        return await store.request(*args,**kwargs)
    except HTTPException as error:
        error.headers={**(error.headers or {}),'Cache-Control':'no-store'}
        raise


@router.post('')
async def create_contract_draft(workspace_id:UUID,body:ContractDraftRequest,response:Response,
                                store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    try:
        raw=await request(store,'POST','rpc/create_acquisition_contract_draft',body={
            'p_id':str(body.id),'p_workspace':str(workspace_id),'p_offer':str(body.offer_id),
            'p_offer_sequence':body.offer_sequence,'p_relationship':str(body.owner_relationship_id),'p_name':body.name})
    except HTTPException as error:
        # The database rejected this transaction. This does not settle any earlier attempt.
        if error.status_code in {401,403,409}:
            error.headers={**(error.headers or {}),'X-Acquisition-Contract-Rejected':'true'}
        raise
    try:
        receipt=ContractDraftReceipt.model_validate(raw)
        if receipt.deal_id!=body.id:
            raise ValueError('Receipt identity mismatch')
    except (ValueError,TypeError):
        raise HTTPException(503,'Draft save is unconfirmed. Retry the same saved request and details.',
                            headers={'Cache-Control':'no-store'}) from None
    return receipt.model_dump(mode='json')


@router.get('')
async def contract_drafts(workspace_id:UUID,response:Response,lead_id:UUID|None=None,after:UUID|None=None,
                          limit:int=Query(default=20,ge=1,le=50),store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    params={'select':','.join(ContractDraftRecord.model_fields),'workspace_id':'eq.'+str(workspace_id),
            'acquisition_status':'in.(draft,pending_signature,executed)','order':'id','limit':str(limit+1)}
    if lead_id is not None:params['lead_id']='eq.'+str(lead_id)
    if after is not None:params['id']='gt.'+str(after)
    raw=await request(store,'GET','deals',params=params)
    try:
        if not isinstance(raw,list) or len(raw)>limit+1:
            raise ValueError('Unexpected draft page')
        rows=[ContractDraftRecord.model_validate(row) for row in raw]
        previous=after
        for row in rows:
            if (row.workspace_id!=workspace_id or lead_id is not None and row.lead_id!=lead_id
                    or previous is not None and row.id.int<=previous.int):
                raise ValueError('Draft page scope mismatch')
            previous=row.id
    except (ValueError,TypeError):
        raise HTTPException(503,'Draft list could not be confirmed. Refresh before continuing.',
                            headers={'Cache-Control':'no-store'}) from None
    return {'items':[row.model_dump(mode='json') for row in rows[:limit]],
            'next_after':str(rows[limit-1].id) if len(rows)>limit else None,'execution_authorized':False}


class SellerName(Exact):
    display_name: str=Field(strict=True,min_length=1,max_length=320)


class ContractSellerChoice(Exact):
    id: UUID
    workspace_id: UUID
    lead_id: UUID
    property_id: UUID
    owner_id: UUID
    relationship: Literal['reported_owner','reported_representative']
    verification_status: Literal['unverified']
    seller: SellerName


@router.get('/sellers')
async def contract_sellers(workspace_id:UUID,lead_id:UUID,property_id:UUID,response:Response,
                           after:UUID|None=None,limit:int=Query(default=20,ge=1,le=50),
                           store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    fields=[name for name in ContractSellerChoice.model_fields if name!='seller']
    params={'select':','.join(fields)+',seller:acquisition_owners(display_name)',
            'workspace_id':'eq.'+str(workspace_id),'lead_id':'eq.'+str(lead_id),
            'property_id':'eq.'+str(property_id),'order':'id','limit':str(limit+1)}
    if after is not None:params['id']='gt.'+str(after)
    raw=await request(store,'GET','acquisition_owner_properties',params=params)
    try:
        if not isinstance(raw,list) or len(raw)>limit+1:
            raise ValueError('Unexpected seller page')
        rows=[ContractSellerChoice.model_validate(row) for row in raw]
        previous=after
        for row in rows:
            if ((row.workspace_id,row.lead_id,row.property_id)!=(workspace_id,lead_id,property_id)
                    or previous is not None and row.id.int<=previous.int or not row.seller.display_name.strip()):
                raise ValueError('Seller scope or name mismatch')
            previous=row.id
    except (ValueError,TypeError):
        raise HTTPException(503,'Seller choices could not be confirmed. Refresh before continuing.',
                            headers={'Cache-Control':'no-store'}) from None
    return {'items':[row.model_dump(mode='json') for row in rows[:limit]],
            'next_after':str(rows[limit-1].id) if len(rows)>limit else None,
            'ownership_verified':False,'execution_authorized':False}
