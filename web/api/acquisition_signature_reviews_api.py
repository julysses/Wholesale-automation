"""User-JWT signature review persistence. No signing provider or service fallback."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_signature_reviews import SignatureReviewRequest, SignatureReviewReceipt, SignatureReviewState, SignatureReviewCandidate
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/signature-review')


def same_scope(value, workspace_id, contract_id, contract_version):
    return (value.workspace_id, value.contract_id, value.contract_version) == (workspace_id, contract_id, contract_version)


@router.get('/candidate')
async def signature_candidate(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                              response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'signature_review_candidate', {'p_workspace': str(workspace_id),
        'p_contract': str(contract_id), 'p_version': contract_version})
    try:
        choice = SignatureReviewCandidate.model_validate(raw)
        now = datetime.now(timezone.utc)
        if (not same_scope(choice, workspace_id, contract_id, contract_version)
                or not now-timedelta(seconds=30) <= choice.checked_at <= now+timedelta(seconds=5)
                or choice.candidate is not None and choice.candidate.max_expires_at <= now
                or choice.current_review.approval_current and choice.current_review.expires_at <= now):
            raise ValueError('Fresh exact signature choices required')
    except (ValueError, TypeError):
        raise uncertain('Signature review choices could not be confirmed. Refresh before continuing.') from None
    return choice.model_dump(mode='json')


@router.get('')
async def signature_state(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                          response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    raw = await rpc(store, 'signature_review_state', {'p_workspace': str(workspace_id),
        'p_contract': str(contract_id), 'p_version': contract_version})
    try:
        state = SignatureReviewState.model_validate(raw)
        now = datetime.now(timezone.utc)
        if (not same_scope(state, workspace_id, contract_id, contract_version)
                or not now-timedelta(seconds=30) <= state.checked_at <= now+timedelta(seconds=5)
                or state.approval_current and state.expires_at <= now):
            raise ValueError('Current exact signature review required')
    except (ValueError, TypeError):
        raise uncertain('Signature review could not be confirmed. Refresh before proceeding.') from None
    return state.model_dump(mode='json')


@router.post('')
async def record_signature_review(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                  body: SignatureReviewRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        raw = await rpc(store, 'record_signature_review', {'p_id': str(body.id),
            'p_workspace': str(workspace_id), 'p_contract': str(contract_id), 'p_version': contract_version,
            'p_expected_sequence': body.expected_sequence, 'p_status': body.status,
            'p_basis': str(body.basis_review_id), 'p_policy': str(body.policy_id),
            'p_expires': body.expires_at.isoformat() if body.expires_at else None,
            'p_personally_reviewed': body.personally_reviewed, 'p_note': body.note})
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), 'X-Acquisition-Signature-Rejected': 'true'}
        raise
    try:
        receipt = SignatureReviewReceipt.model_validate(raw)
        if (not same_scope(receipt, workspace_id, contract_id, contract_version)
                or receipt.review_id != body.id or receipt.sequence != body.expected_sequence+1
                or receipt.status != body.status):
            raise ValueError('Exact signature review receipt required')
    except (ValueError, TypeError):
        raise uncertain('Signature review save is unconfirmed. Keep the same request and decision details for recovery.') from None
    return receipt.model_dump(mode='json')
