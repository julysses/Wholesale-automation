"""Scoped renewal discovery and exact personal saves; no lifecycle advancement."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from schemas.acquisition_review_renewal import ReviewRenewalRequest, ReviewRenewalReceipt
from schemas.acquisition_renewal_choices import ReviewRenewalCandidate, ReviewRenewalIndex
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contract_documents_api import Version, rpc, uncertain

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}/versions/{contract_version}/review-renewals')


def validate_scope_and_time(value, workspace, contract, version):
    now = datetime.now(timezone.utc)
    if ((value.workspace_id,value.contract_id,value.contract_version)!=(workspace,contract,version)
            or not now-timedelta(seconds=30)<=value.checked_at<=now+timedelta(seconds=5)):
        raise ValueError('Current exact renewal scope required')
    return now


@router.get('')
async def renewal_index(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                        response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'acquisition_review_renewal_index',{'p_workspace':str(workspace_id),'p_contract':str(contract_id),'p_version':contract_version})
    try:
        index=ReviewRenewalIndex.model_validate(raw)
        now=validate_scope_and_time(index,workspace_id,contract_id,contract_version)
        if any(item.current_review and item.current_review.approval_current and item.current_review.expires_at<=now for item in index.items):
            raise ValueError('Renewal index expired in transit')
    except (ValueError,TypeError):
        raise uncertain('Current renewal reviews could not be confirmed. Refresh before proceeding.') from None
    return index.model_dump(mode='json')


@router.get('/{root_review_id}/candidate')
async def renewal_candidate(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                            root_review_id: UUID, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    raw=await rpc(store,'acquisition_review_renewal_candidate',{'p_workspace':str(workspace_id),'p_contract':str(contract_id),
        'p_version':contract_version,'p_root':str(root_review_id)})
    try:
        choice=ReviewRenewalCandidate.model_validate(raw)
        now=validate_scope_and_time(choice,workspace_id,contract_id,contract_version)
        if (choice.root_review_id!=root_review_id or choice.candidate and choice.candidate.max_expires_at<=now
                or choice.current_review and choice.current_review.approval_current and choice.current_review.expires_at<=now
                or any(d.approval_current and d.expires_at<=now for d in choice.dependencies)):
            raise ValueError('Renewal choice expired or mismatched')
    except (ValueError,TypeError):
        raise uncertain('Current renewal choices could not be confirmed. Refresh before proceeding.') from None
    return choice.model_dump(mode='json')


@router.post('')
async def record_renewal(workspace_id: UUID, contract_id: UUID, contract_version: Version,
                         body: ReviewRenewalRequest, response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control']='no-store'
    if body.expected_version!=contract_version:
        raise HTTPException(409,'The saved renewal belongs to a different contract version.',
            headers={'Cache-Control':'no-store','X-Acquisition-Renewal-Rejected':'true'})
    try:
        raw=await rpc(store,'record_acquisition_review_renewal',{'p_id':str(body.id),'p_workspace':str(workspace_id),
            'p_contract':str(contract_id),'p_version':contract_version,'p_kind':body.kind,'p_term':body.deadline_term,
            'p_expected_sequence':body.expected_sequence,'p_root':str(body.root_review_id),'p_previous':str(body.previous_review_id),
            'p_policy':str(body.policy_id),'p_snapshot':body.expected_snapshot_sha256,'p_expires':body.expires_at.isoformat(),
            'p_personally_reviewed':body.personally_reviewed,'p_note':body.note})
    except HTTPException as error:
        if error.status_code in {401,403,409}:
            error.headers={**(error.headers or {}),'X-Acquisition-Renewal-Rejected':'true'}
        raise
    try:
        receipt=ReviewRenewalReceipt.model_validate(raw)
        if not receipt.confirms(body,workspace_id=workspace_id,contract_id=contract_id):
            raise ValueError('Exact historical renewal receipt required')
    except (ValueError,TypeError):
        raise uncertain('Renewal save is unconfirmed. Keep the same request for recovery.') from None
    return receipt.model_dump(mode='json')
