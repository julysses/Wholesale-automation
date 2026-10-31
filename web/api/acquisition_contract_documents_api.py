"""Authenticated document metadata and separately gated binary uploads; no approval."""
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Path, Response, Request
from schemas.acquisition_contract_documents import ContractDocumentRegistration, ContractDocumentRegistrationReceipt, ContractDocumentState, ContractDocumentUploadReceipt, DocumentPurpose
from schemas.acquisition_evidence import EvidenceRevocation, EvidenceRevocationReceipt
from tools.acquisition_store import acquisition_store, open_acquisition_store
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed
from web.api.acquisition_upload_stream import binary_upload_source
from starlette.requests import ClientDisconnect

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


async def contract_document_upload_store(request: Request):
    if os.getenv('ACQUISITION_CONTRACT_UPLOAD_ENABLED', '').lower() != 'true':
        raise HTTPException(404, 'Contract document upload is not enabled', headers={'Cache-Control':'no-store'})
    try:
        async with open_acquisition_store(request) as store:
            yield store
    except HTTPException as error:
        error.headers={**(error.headers or {}),'Cache-Control':'no-store'}
        raise


def upload_unconfirmed():
    return HTTPException(503, {'code':'CONTRACT_DOCUMENT_UPLOAD_UNCONFIRMED',
        'message':'Upload could not be confirmed. Preserve the same document record and exact file for recovery.'},
        headers={'Cache-Control':'no-store'})


@router.post('/{artifact_id}/bytes')
async def upload_document(workspace_id:UUID, contract_id:UUID, contract_version:Version, artifact_id:UUID,
                          purpose:DocumentPurpose, request:Request, response:Response,
                          store=Depends(contract_document_upload_store)):
    response.headers['Cache-Control']='no-store'
    source=binary_upload_source(request)
    try:
        result=await store.upload_contract_document_with_admission(artifact_id,source,workspace_id=workspace_id,
            contract_id=contract_id,contract_version=contract_version,purpose=purpose)
    except EvidenceUploadUnconfirmed:
        raise upload_unconfirmed() from None
    except (EvidenceUnavailable,ClientDisconnect):
        raise HTTPException(409, {'code':'CONTRACT_DOCUMENT_UPLOAD_NOT_ACCEPTED',
            'message':'The file or current document state could not be accepted. Check the document record and original file.'},
            headers={'Cache-Control':'no-store'}) from None
    except HTTPException as error:
        error.headers={**(error.headers or {}),'Cache-Control':'no-store'}
        raise
    try:
        receipt=ContractDocumentUploadReceipt.model_validate(result)
        now=datetime.now(timezone.utc)
        if ((receipt.workspace_id,receipt.contract_id,receipt.contract_version,receipt.artifact_id,receipt.purpose)
                != (workspace_id,contract_id,contract_version,artifact_id,purpose)
                or receipt.retain_until<=now
                or any(not now-timedelta(seconds=30)<=checked<=now+timedelta(seconds=5)
                       for checked in (receipt.checked_at,receipt.registry_checked_at))):
            raise ValueError('Upload receipt scope or freshness mismatch')
    except (ValueError,TypeError):
        raise upload_unconfirmed() from None
    return receipt.model_dump(mode='json')
