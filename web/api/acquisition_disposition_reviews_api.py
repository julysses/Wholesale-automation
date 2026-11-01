"""Authenticated original disposition findings; no lifecycle or transaction execution."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_disposition_review import DispositionReviewRequest, DispositionReviewReceipt, DispositionReviewState
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/disposition-review')


@router.post('')
async def record_disposition_review(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                  body: DispositionReviewRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    if body.expected_version != contract_version:
        raise HTTPException(409, 'The saved review belongs to a different contract version.',
                            headers={'X-Acquisition-Disposition-Review-Rejected': 'true', 'Cache-Control': 'no-store'})
    try:
        raw = await rpc(store, 'record_disposition_review', {
            'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
            'p_version': contract_version, 'p_expected_sequence': body.expected_sequence,
            'p_status': body.status, 'p_plan': str(body.plan_id),
            'p_original_review': str(body.original_review_id) if body.original_review_id else None,
            'p_policy': str(body.policy_id),
            'p_expires': body.expires_at.isoformat() if body.expires_at else None,
            'p_personally_reviewed': body.personally_reviewed, 'p_note': body.note,
            'p_findings': body.findings.model_dump(mode='json') if body.findings is not None else None})
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), 'X-Acquisition-Disposition-Review-Rejected': 'true'}
        raise
    try:
        receipt = DispositionReviewReceipt.model_validate(raw)
        if ((receipt.workspace_id, receipt.contract_id, receipt.contract_version, receipt.review_id,
             receipt.sequence, receipt.status) != (workspace_id, contract_id, contract_version, body.id,
                                                  body.expected_sequence+1, body.status)):
            raise ValueError('Exact historical disposition review receipt required')
    except (ValueError, TypeError):
        raise uncertain('Disposition review save is unconfirmed. Keep the same request and findings for recovery.') from None
    return receipt.model_dump(mode='json')


@router.get('')
async def disposition_review_state(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                  response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'disposition_review_state', {'p_workspace': str(workspace_id),
        'p_contract': str(contract_id), 'p_version': contract_version})
    try:
        state = DispositionReviewState.model_validate(raw)
        now = datetime.now(timezone.utc)
        if ((state.workspace_id, state.contract_id, state.contract_version) != (workspace_id, contract_id, contract_version)
                or not now-timedelta(seconds=30) <= state.checked_at <= now+timedelta(seconds=5)
                or state.approval_current and state.expires_at <= now):
            raise ValueError('Fresh exact disposition review required')
    except (ValueError, TypeError):
        raise uncertain('Current disposition review could not be confirmed. Refresh before proceeding.') from None
    return state.model_dump(mode='json')



