"""Authenticated original disposition findings; no lifecycle or transaction execution."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from schemas.acquisition_disposition_review import DispositionReviewRequest, DispositionReviewReceipt, DispositionReviewState
from schemas.acquisition_disposition_history import DispositionHistorySummary, DispositionHistoryDetail
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




@router.get('/history')
async def disposition_review_history(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                               response: Response, before: int | None = Query(None, ge=1, le=2147483647),
                               limit: int = Query(20, ge=1, le=20), store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    # Existing state RPC establishes actual role, MFA, live session and exact
    # contract-version access. The following SELECT independently applies RLS.
    await disposition_review_state(workspace_id, contract_id, contract_version, response, store)
    params = {'select': ','.join(DispositionHistorySummary.model_fields), 'workspace_id': 'eq.'+str(workspace_id),
              'contract_id': 'eq.'+str(contract_id), 'contract_version': 'eq.'+str(contract_version),
              'kind': 'eq.disposition_findings', 'order': 'sequence.desc', 'limit': str(limit+1)}
    if before is not None:
        params['sequence'] = 'lt.'+str(before)
    raw = await history_request(store, params)
    try:
        if not isinstance(raw, list) or len(raw) > limit+1:
            raise ValueError('Bounded disposition history required')
        rows = [DispositionHistorySummary.model_validate(row) for row in raw]
        previous = before
        seen = set()
        now = datetime.now(timezone.utc)
        for row in rows:
            validate_history_scope(row, workspace_id, contract_id, contract_version, now)
            if previous is not None and row.sequence >= previous or row.id in seen:
                raise ValueError('Ordered unique original decisions required')
            previous = row.sequence
            seen.add(row.id)
    except (ValueError, TypeError):
        raise uncertain('Disposition decision history could not be confirmed. Refresh before continuing.') from None
    return {'workspace_id': str(workspace_id), 'contract_id': str(contract_id), 'contract_version': contract_version,
            'items': [row.model_dump(mode='json') for row in rows[:limit]],
            'next_before': rows[limit-1].sequence if len(rows) > limit else None,
            'history_only': True, 'approval_current': False, 'execution_authorized': False}


@router.get('/history/{review_id}')
async def disposition_review_history_detail(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                                      review_id: UUID, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    await disposition_review_state(workspace_id, contract_id, contract_version, response, store)
    raw = await history_request(store, {'select': ','.join(DispositionHistoryDetail.model_fields),
        'workspace_id': 'eq.'+str(workspace_id), 'contract_id': 'eq.'+str(contract_id),
        'contract_version': 'eq.'+str(contract_version), 'kind': 'eq.disposition_findings', 'id': 'eq.'+str(review_id), 'limit': '2'})
    if raw == []:
        raise HTTPException(404, 'Disposition decision is unavailable in this contract version.', headers={'Cache-Control': 'no-store'})
    try:
        if not isinstance(raw, list) or len(raw) != 1:
            raise ValueError('One original disposition decision required')
        row = DispositionHistoryDetail.model_validate(raw[0])
        validate_history_scope(row, workspace_id, contract_id, contract_version, datetime.now(timezone.utc))
        if row.id != review_id:
            raise ValueError('Original review identity changed')
    except (ValueError, TypeError):
        raise uncertain('The original disposition decision could not be confirmed. Refresh before continuing.') from None
    return {'workspace_id': str(workspace_id), 'contract_id': str(contract_id), 'contract_version': contract_version,
            'record': row.model_dump(mode='json'), 'history_only': True, 'approval_current': False, 'execution_authorized': False}


async def history_request(store, params):
    try:
        return await store.request('GET', 'acquisition_contract_reviews', params=params)
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise


def validate_history_scope(row, workspace, contract, version, now):
    if (row.workspace_id, row.contract_id, row.contract_version) != (workspace, contract, version) or row.created_at > now:
        raise ValueError('Exact original disposition history scope required')
