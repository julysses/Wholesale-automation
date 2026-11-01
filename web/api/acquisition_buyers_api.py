"""Workspace-scoped buyer profiles and exact save recovery; no contact authority."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from schemas.acquisition_buyers import AcquisitionBuyerIndex, AcquisitionBuyerProfile, AcquisitionBuyerRequest, AcquisitionBuyerReceipt
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import rpc, uncertain

router=APIRouter(prefix='/workspaces/{workspace_id}/buyers')


def current_scope(value, workspace):
    now=datetime.now(timezone.utc)
    if value.workspace_id!=workspace or not now-timedelta(seconds=30)<=value.checked_at<=now+timedelta(seconds=5):
        raise ValueError('Current buyer workspace projection required')


@router.get('')
async def buyer_index(workspace_id:UUID,response:Response,after:UUID|None=None,
                      limit:int=Query(25,ge=1,le=50),store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'acquisition_buyer_index',{'p_workspace':str(workspace_id),'p_after':str(after) if after else None,'p_limit':limit})
    try:
        page=AcquisitionBuyerIndex.model_validate(raw)
        current_scope(page,workspace_id)
        if len(page.items)>limit or page.next_cursor is not None and len(page.items)!=limit or after is not None and any(item.buyer_id.int<=after.int for item in page.items):
            raise ValueError('Buyer pagination changed')
    except (ValueError,TypeError):
        raise uncertain('Current buyers could not be confirmed. Refresh before proceeding.') from None
    return page.model_dump(mode='json')


@router.get('/{buyer_id}')
async def buyer_profile(workspace_id:UUID,buyer_id:UUID,response:Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'acquisition_buyer_profile',{'p_workspace':str(workspace_id),'p_buyer':str(buyer_id)})
    if raw is None:raise HTTPException(404,'Buyer not found in this workspace.',headers={'Cache-Control':'no-store'})
    try:
        profile=AcquisitionBuyerProfile.model_validate(raw)
        current_scope(profile,workspace_id)
        if profile.buyer_id!=buyer_id:raise ValueError('Buyer identity changed')
    except (ValueError,TypeError):
        raise uncertain('Current buyer details could not be confirmed. Refresh before proceeding.') from None
    return profile.model_dump(mode='json')


@router.post('')
async def save_buyer(workspace_id:UUID,body:AcquisitionBuyerRequest,response:Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    try:
        raw=await rpc(store,'record_acquisition_buyer',{'p_id':str(body.id),'p_workspace':str(workspace_id),
            'p_buyer':str(body.buyer_id),'p_expected_revision':body.expected_revision,'p_details':body.details.model_dump(mode='json')})
    except HTTPException as error:
        if error.status_code in {401,403,409}:
            error.headers={**(error.headers or {}),'X-Acquisition-Buyer-Rejected':'true'}
        raise
    try:
        receipt=AcquisitionBuyerReceipt.model_validate(raw)
        if not receipt.confirms(body,workspace_id):raise ValueError('Buyer receipt does not match the saved request')
    except (ValueError,TypeError):
        raise uncertain('Buyer save is unconfirmed. Keep the same request for recovery.') from None
    return receipt.model_dump(mode='json')
