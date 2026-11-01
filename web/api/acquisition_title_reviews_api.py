"""Authenticated exact title decisions; no disposition or lifecycle advancement."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_title_review import TitleReviewRequest, TitleReviewReceipt, TitleReviewState, TitleReviewCandidate
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/title-review')


@router.post('')
async def record_title_review(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                  body: TitleReviewRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    if body.expected_version != contract_version:
        raise HTTPException(409, 'The saved review belongs to a different contract version.',
                            headers={'X-Acquisition-Title-Review-Rejected': 'true', 'Cache-Control': 'no-store'})
    try:
        raw = await rpc(store, 'record_title_review', {
            'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
            'p_version': contract_version, 'p_expected_sequence': body.expected_sequence,
            'p_status': body.status, 'p_artifact': str(body.artifact_id),
            'p_verification': str(body.verification_id), 'p_policy': str(body.policy_id),
            'p_expires': body.expires_at.isoformat() if body.expires_at else None,
            'p_personally_reviewed': body.personally_reviewed, 'p_note': body.note,
            'p_findings': body.findings.model_dump(mode='json') if body.findings is not None else None})
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), 'X-Acquisition-Title-Review-Rejected': 'true'}
        raise
    try:
        receipt = TitleReviewReceipt.model_validate(raw)
        if ((receipt.workspace_id, receipt.contract_id, receipt.contract_version, receipt.review_id,
             receipt.sequence, receipt.status) != (workspace_id, contract_id, contract_version, body.id,
                                                  body.expected_sequence+1, body.status)):
            raise ValueError('Exact historical title review receipt required')
    except (ValueError, TypeError):
        raise uncertain('Title review save is unconfirmed. Keep the same request and findings for recovery.') from None
    return receipt.model_dump(mode='json')


@router.get('')
async def title_review_state(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                  response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'title_review_state', {'p_workspace': str(workspace_id),
        'p_contract': str(contract_id), 'p_version': contract_version})
    try:
        state = TitleReviewState.model_validate(raw)
        now = datetime.now(timezone.utc)
        if ((state.workspace_id, state.contract_id, state.contract_version) != (workspace_id, contract_id, contract_version)
                or not now-timedelta(seconds=30) <= state.checked_at <= now+timedelta(seconds=5)
                or state.approval_current and state.expires_at <= now):
            raise ValueError('Fresh exact title review required')
    except (ValueError, TypeError):
        raise uncertain('Current title review could not be confirmed. Refresh before proceeding.') from None
    return state.model_dump(mode='json')



@router.get('/candidate')
async def title_review_candidate(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                 response: Response, artifact_id: UUID | None = None, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'title_review_candidate', {'p_workspace': str(workspace_id),
        'p_contract': str(contract_id), 'p_version': contract_version,
        'p_artifact': str(artifact_id) if artifact_id is not None else None})
    try:
        choice = TitleReviewCandidate.model_validate(raw)
        now = datetime.now(timezone.utc)
        if ((choice.workspace_id, choice.contract_id, choice.contract_version, choice.artifact_id)
                != (workspace_id, contract_id, contract_version, artifact_id)
                or not now-timedelta(seconds=30) <= choice.checked_at <= now+timedelta(seconds=5)
                or choice.resolution is not None and choice.resolution.available_until <= now
                or choice.candidate is not None and choice.candidate.max_expires_at <= now
                or choice.current_review.approval_current and choice.current_review.expires_at <= now):
            raise ValueError('Current exact title choices required')
    except (ValueError, TypeError):
        raise uncertain('Title review choices could not be confirmed. Refresh before proceeding.') from None
    return choice.model_dump(mode='json')
