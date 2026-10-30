"""Postal provenance handoff; no address verification or mail execution."""
import os
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool

from tools.acquisition_store import acquisition_store

router=APIRouter(prefix='/workspaces/{workspace_id}/owner-relationships/{relationship_id}/postal-observations')


class PostalImport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: UUID


class PostalReceipt(BaseModel):
    # Internal source evidence stays in the ledger, not in the primary app response.
    model_config=ConfigDict(extra='ignore')
    id: UUID
    workspace_id: UUID
    relationship_id: UUID
    raw_address: str=Field(min_length=1,max_length=4096,strict=True)
    verification_status: Literal['unverified']
    recorded_at: AwareDatetime
    duplicate: StrictBool
    execution_authorized: StrictBool


@router.post('')
async def import_postal(workspace_id: UUID,relationship_id: UUID,body: PostalImport,
                        response: Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    if os.getenv('ACQUISITION_POSTAL_IMPORT_ENABLED','').lower()!='true':
        raise HTTPException(503,'Postal address import is not available yet',headers={'Cache-Control':'no-store'})
    try:
        result=await store.request('POST','rpc/import_acquisition_postal_observation',body={
            'p_id':str(body.id),'p_workspace':str(workspace_id),'p_relationship':str(relationship_id)})
    except HTTPException as error:
        error.headers={**(error.headers or {}),'Cache-Control':'no-store'}
        raise
    try:
        receipt=PostalReceipt.model_validate(result)
        if ((receipt.id,receipt.workspace_id,receipt.relationship_id)!=(body.id,workspace_id,relationship_id)
            or receipt.execution_authorized or not receipt.raw_address.strip()
            or len(receipt.raw_address.encode('utf-8'))>4096):
            raise ValueError('Postal receipt mismatch')
    except (ValueError,TypeError):
        raise HTTPException(503,'Address import could not be confirmed. Retry the same saved request.',headers={'Cache-Control':'no-store'}) from None
    return receipt.model_dump(mode='json')
