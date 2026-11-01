"""User-scoped purchase-path proposals, with exact uncertain-save recovery."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_disposition_plans import DispositionPlanRequest, DispositionPlanReceipt, DispositionPlanState
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/disposition-plan')
REJECTED = 'X-Acquisition-Disposition-Plan-Rejected'


@router.post('')
async def record_plan(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                      body: DispositionPlanRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    if body.expected_version != contract_version:
        raise HTTPException(409, 'The saved proposal belongs to another contract version.',
                            headers={REJECTED: 'true', 'Cache-Control': 'no-store'})
    try:
        raw = await rpc(store, 'record_disposition_plan', dict(p_id=str(body.id), p_workspace=str(workspace_id),
            p_contract=str(contract_id), p_version=contract_version, p_expected_sequence=body.expected_sequence,
            p_status=body.status, p_exit_type=body.exit_type, p_note=body.note,
            p_original_plan=str(body.original_plan_id) if body.original_plan_id else None))
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), REJECTED: 'true'}
        raise
    try:
        result = DispositionPlanReceipt.model_validate(raw)
        if ((result.workspace_id, result.contract_id, result.contract_version, result.plan_id, result.sequence,
             result.status, result.exit_type, result.original_plan_id) !=
            (workspace_id, contract_id, contract_version, body.id, body.expected_sequence+1,
             body.status, body.exit_type, body.original_plan_id)):
            raise ValueError('Exact original proposal receipt required')
    except (ValueError, TypeError):
        raise uncertain('Purchase-path save is unconfirmed. Keep the same request for recovery.') from None
    return result.model_dump(mode='json')


@router.get('')
async def plan_state(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                     response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'disposition_plan_state', dict(p_workspace=str(workspace_id), p_contract=str(contract_id), p_version=contract_version))
    try:
        result = DispositionPlanState.model_validate(raw)
        now = datetime.now(timezone.utc)
        if ((result.workspace_id, result.contract_id, result.contract_version) != (workspace_id, contract_id, contract_version)
                or not now-timedelta(seconds=30) <= result.checked_at <= now+timedelta(seconds=5)):
            raise ValueError('Current scoped plan state required')
    except (ValueError, TypeError):
        raise uncertain('Current purchase-path proposal could not be confirmed.') from None
    return result.model_dump(mode='json')
