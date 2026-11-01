"""Original-document references and withdrawals; no copying, review or execution."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, StrictBool, field_validator
from schemas.acquisition_contract_terms import Exact
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/document-links')


class DocumentLinkRequest(Exact):
    id: UUID
    source_version: int = Field(strict=True, ge=1, le=2147483646)
    artifact_id: UUID
    verification_id: UUID
    sha256: str = Field(strict=True, pattern=r'^[a-f0-9]{64}$')
    note: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('note')
    @classmethod
    def meaningful_note(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Describe why the original document supports this version')
        return value


class LinkWithdrawalRequest(Exact):
    id: UUID
    reason: str = Field(strict=True, min_length=20, max_length=4000)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 20 or '\x00' in value:
            raise ValueError('Describe why this reference is withdrawn')
        return value


class LinkReceipt(Exact):
    link_id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=2, le=2147483647)
    source_version: int = Field(strict=True, ge=1, le=2147483646)
    artifact_id: UUID
    duplicate: StrictBool
    review_approved: StrictBool
    execution_authorized: StrictBool


class LinkWithdrawalReceipt(Exact):
    revocation_id: UUID
    workspace_id: UUID
    contract_id: UUID
    contract_version: int = Field(strict=True, ge=2, le=2147483647)
    link_id: UUID
    duplicate: StrictBool
    execution_authorized: StrictBool


async def write(store, function, body):
    try:
        return await rpc(store, function, body)
    except HTTPException as error:
        # This settles only the current attempt, not an earlier lost response.
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), 'X-Acquisition-Link-Rejected': 'true'}
        raise


@router.post('')
async def link_document(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                        body: DocumentLinkRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    if body.source_version >= contract_version:
        raise HTTPException(422, 'Choose an original document from an earlier contract version.', headers={'Cache-Control': 'no-store'})
    raw = await write(store, 'link_contract_document', {
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_contract': str(contract_id), 'p_version': contract_version,
        'p_source_version': body.source_version, 'p_artifact': str(body.artifact_id),
        'p_verification': str(body.verification_id), 'p_sha256': body.sha256, 'p_note': body.note})
    try:
        receipt = LinkReceipt.model_validate(raw)
        if (receipt.link_id, receipt.workspace_id, receipt.contract_id, receipt.contract_version, receipt.source_version, receipt.artifact_id) != (
                body.id, workspace_id, contract_id, contract_version, body.source_version, body.artifact_id) or receipt.review_approved or receipt.execution_authorized:
            raise ValueError('Exact non-approving link receipt required')
    except (ValueError, TypeError):
        raise uncertain('Document reference save is unconfirmed. Retry the same saved request and source details.') from None
    return receipt.model_dump(mode='json')


@router.post('/{link_id}/withdrawals')
async def withdraw_link(workspace_id: UUID, contract_id: UUID, contract_version: Version, link_id: UUID,
                        body: LinkWithdrawalRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    if contract_version < 2:
        raise HTTPException(422, 'An original draft cannot have an earlier-version reference.', headers={'Cache-Control': 'no-store'})
    raw = await write(store, 'revoke_contract_document_link', {
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
        'p_version': contract_version, 'p_link': str(link_id), 'p_reason': body.reason})
    try:
        receipt = LinkWithdrawalReceipt.model_validate(raw)
        if (receipt.revocation_id, receipt.workspace_id, receipt.contract_id, receipt.contract_version, receipt.link_id) != (
                body.id, workspace_id, contract_id, contract_version, link_id) or receipt.execution_authorized:
            raise ValueError('Exact non-executing withdrawal receipt required')
    except (ValueError, TypeError):
        raise uncertain('Document reference withdrawal is unconfirmed. Retry the same saved request.') from None
    return receipt.model_dump(mode='json')
