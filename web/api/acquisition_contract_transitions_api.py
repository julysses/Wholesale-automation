"""Recorded lifecycle changes; never send, sign or settle a transaction."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_contract_transitions import ContractTransitionRequest, ContractTransitionReceipt
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/transitions')


@router.post('')
async def record_transition(workspace_id: UUID, contract_id: UUID, body: ContractTransitionRequest,
                            response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        raw = await rpc(store, 'record_contract_transition', dict(
            p_id=str(body.id), p_workspace=str(workspace_id), p_contract=str(contract_id),
            p_expected_version=body.expected_version, p_expected_sequence=body.expected_sequence,
            p_expected_status=body.expected_status, p_target_status=body.target_status, p_reason=body.reason))
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), 'X-Acquisition-Transition-Rejected': 'true'}
        raise
    try:
        receipt = ContractTransitionReceipt.model_validate(raw)
        if not receipt.confirms(body, workspace_id=workspace_id, contract_id=contract_id):
            raise ValueError('Exact transition receipt required')
    except (ValueError, TypeError):
        raise uncertain('Status change is unconfirmed. Keep the same request and reason for recovery.') from None
    return receipt.model_dump(mode='json')
