"""Authenticated deadline decisions; signed dates and lifecycle remain unchanged."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_deadline_resolution import DeadlineResolutionReviewRequest, DeadlineResolutionReviewReceipt
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/deadline-reviews')


@router.post('')
async def record_deadline_resolution_review(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                  body: DeadlineResolutionReviewRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    if body.expected_version != contract_version:
        raise HTTPException(409, 'The saved review belongs to a different contract version.',
                            headers={'X-Acquisition-Deadline-Review-Rejected': 'true', 'Cache-Control': 'no-store'})
    try:
        raw = await rpc(store, 'record_deadline_resolution_review', {
            'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
            'p_version': contract_version, 'p_expected_sequence': body.expected_sequence,
            'p_status': body.status, 'p_artifact': str(body.artifact_id),
            'p_verification': str(body.verification_id), 'p_policy': str(body.policy_id),
            'p_expires': body.expires_at.isoformat() if body.expires_at else None,
            'p_personally_reviewed': body.personally_reviewed, 'p_note': body.note,
            'p_term': body.term,
            'p_resolution': body.resolution.model_dump(mode='json') if body.resolution is not None else None,
            'p_original': str(body.original_review_id) if body.original_review_id is not None else None})
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            error.headers = {**(error.headers or {}), 'X-Acquisition-Deadline-Review-Rejected': 'true'}
        raise
    try:
        receipt = DeadlineResolutionReviewReceipt.model_validate(raw)
        if ((receipt.workspace_id, receipt.contract_id, receipt.contract_version, receipt.review_id,
             receipt.sequence, receipt.status, receipt.term, receipt.interpretation_review_id) != (workspace_id, contract_id, contract_version, body.id,
                                                  body.expected_sequence+1, body.status, body.term, body.original_review_id or body.id)):
            raise ValueError('Exact historical deadline review receipt required')
    except (ValueError, TypeError):
        raise uncertain('Deadline review save is unconfirmed. Keep the same request and interpretation for recovery.') from None
    return receipt.model_dump(mode='json')

