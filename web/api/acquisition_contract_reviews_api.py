"""Authenticated human decisions; database policy and evidence remain authoritative."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from schemas.acquisition_contract_reviews import ContractReviewRequest, ContractReviewReceipt, ContractReviewState, ReviewKind
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/reviews')


def scope_matches(value, workspace_id, contract_id, contract_version, kind):
    return (value.workspace_id, value.contract_id, value.contract_version, value.kind) == (workspace_id, contract_id, contract_version, kind)


@router.get('/{kind}')
async def review_state(workspace_id: UUID, contract_id: UUID, contract_version: Version, kind: ReviewKind,
                       response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'contract_review_state', {'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
        'p_version': contract_version, 'p_kind': kind})
    try:
        state = ContractReviewState.model_validate(raw)
        now = datetime.now(timezone.utc)
        if (not scope_matches(state, workspace_id, contract_id, contract_version, kind)
                or not now-timedelta(seconds=30) <= state.checked_at <= now+timedelta(seconds=5)
                or state.approval_current and state.expires_at <= now):
            raise ValueError('Current exact review required')
    except (ValueError, TypeError):
        raise uncertain('Current contract review could not be confirmed. Refresh before proceeding.') from None
    return state.model_dump(mode='json')


@router.post('/{kind}')
async def record_review(workspace_id: UUID, contract_id: UUID, contract_version: Version, kind: ReviewKind,
                        body: ContractReviewRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    # Preserve exact note, request identity and expired historical retry input.
    # Database authorization is evaluated afresh; client assertions grant no authority.
    raw = await rpc(store, 'record_contract_review', {'p_id': str(body.id), 'p_workspace': str(workspace_id),
        'p_contract': str(contract_id), 'p_version': contract_version, 'p_kind': kind,
        'p_expected_sequence': body.expected_sequence, 'p_status': body.status,
        'p_artifact': str(body.artifact_id), 'p_verification': str(body.verification_id),
        'p_policy': str(body.policy_id), 'p_expires': body.expires_at.isoformat() if body.expires_at else None,
        'p_personally_reviewed': body.personally_reviewed, 'p_note': body.note})
    try:
        receipt = ContractReviewReceipt.model_validate(raw)
        if (not scope_matches(receipt, workspace_id, contract_id, contract_version, kind)
                or receipt.review_id != body.id or receipt.sequence != body.expected_sequence+1
                or receipt.status != body.status):
            raise ValueError('Exact review receipt required')
    except (ValueError, TypeError):
        raise uncertain('Review save is unconfirmed. Keep the same request and decision details for recovery.') from None
    return receipt.model_dump(mode='json')


@router.get('/{kind}/documents/{artifact_id}/candidate')
async def review_candidate(workspace_id: UUID, contract_id: UUID, contract_version: Version, kind: ReviewKind,
                           artifact_id: UUID, response: Response, store=Depends(acquisition_store)):
    from schemas.acquisition_contract_reviews import ContractReviewCandidate
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'contract_review_candidate', {'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
        'p_version': contract_version, 'p_kind': kind, 'p_artifact': str(artifact_id)})
    try:
        choice = ContractReviewCandidate.model_validate(raw)
        now = datetime.now(timezone.utc)
        if (not scope_matches(choice, workspace_id, contract_id, contract_version, kind)
                or choice.artifact_id != artifact_id
                or not now-timedelta(seconds=30) <= choice.checked_at <= now+timedelta(seconds=5)
                or choice.candidate is not None and choice.candidate.max_expires_at <= now
                or choice.current_review.approval_current and choice.current_review.expires_at <= now):
            raise ValueError('Current exact review choices required')
    except (ValueError, TypeError):
        raise uncertain('Review choices could not be confirmed. Refresh the selected document before continuing.') from None
    return choice.model_dump(mode='json')
