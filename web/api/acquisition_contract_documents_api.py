"""Authenticated contract document metadata only; no upload, download or approval."""
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from schemas.acquisition_contract_documents import ContractDocumentRegistration, ContractDocumentRegistrationReceipt, ContractDocumentState
from schemas.acquisition_evidence import EvidenceRevocation, EvidenceRevocationReceipt
from tools.acquisition_store import acquisition_store

router=APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/documents')
Version=Annotated[int,Path(ge=1,le=2147483647)]

async def rpc(store,name,body):
    try:
        return await store.request('POST','rpc/'+name,body=body)
    except HTTPException as error:
        error.headers={**(error.headers or {}),'Cache-Control':'no-store'}
        raise


def uncertain(message):
    return HTTPException(503,message,headers={'Cache-Control':'no-store'})


@router.post('')
async def register_document(workspace_id:UUID,contract_id:UUID,contract_version:Version,
                            body:ContractDocumentRegistration,response:Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'register_contract_document',{
        'p_id':str(body.id),'p_workspace':str(workspace_id),'p_contract':str(contract_id),'p_version':contract_version,
        'p_purpose':body.purpose,'p_sha256':body.expected_sha256,'p_byte_size':body.expected_byte_size,
        'p_media_type':body.media_type,'p_policy':str(body.retention_policy_id),'p_note':body.provenance_note})
    try:
        receipt=ContractDocumentRegistrationReceipt.model_validate(raw)
        if (receipt.artifact_id,receipt.workspace_id,receipt.contract_id,receipt.contract_version)!=(body.id,workspace_id,contract_id,contract_version):
            raise ValueError('Document receipt scope changed')
    except (ValueError,TypeError):
        raise uncertain('Document registration is unconfirmed. Keep the same request and file details for recovery.') from None
    return receipt.model_dump(mode='json')


@router.get('/{artifact_id}')
async def document_state(workspace_id:UUID,contract_id:UUID,contract_version:Version,artifact_id:UUID,
                          response:Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'contract_document_state',{'p_workspace':str(workspace_id),'p_contract':str(contract_id),
        'p_version':contract_version,'p_artifact':str(artifact_id)})
    try:
        state=ContractDocumentState.model_validate(raw)
        now=datetime.now(timezone.utc)
        if ((state.id,state.workspace_id,state.contract_id,state.contract_version)!=(artifact_id,workspace_id,contract_id,contract_version)
                or not now-timedelta(seconds=30)<=state.checked_at<=now+timedelta(seconds=5)):
            raise ValueError('Document state scope or freshness changed')
    except (ValueError,TypeError):
        raise uncertain('Current contract document state could not be confirmed.') from None
    # Raw projection has already passed strict field validation; preserve RPC field names.
    return raw


@router.post('/{artifact_id}/revocations')
async def revoke_document(workspace_id:UUID,contract_id:UUID,contract_version:Version,artifact_id:UUID,
                           body:EvidenceRevocation,response:Response,store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'revoke_contract_document',{'p_id':str(body.id),'p_workspace':str(workspace_id),
        'p_contract':str(contract_id),'p_version':contract_version,'p_artifact':str(artifact_id),'p_reason':body.reason})
    try:
        receipt=EvidenceRevocationReceipt.model_validate(raw)
        if (receipt.revocation_id,receipt.artifact_id,receipt.workspace_id)!=(body.id,artifact_id,workspace_id):
            raise ValueError('Document revocation receipt scope changed')
    except (ValueError,TypeError):
        raise uncertain('Document revocation is unconfirmed. Keep the same request and reason for recovery.') from None
    return receipt.model_dump(mode='json')
