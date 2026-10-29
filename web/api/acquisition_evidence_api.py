"""Workspace evidence metadata. Upload/download and approval are deliberately separate contracts."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from schemas.acquisition_evidence import (
    EvidenceRegistration, EvidenceRegistrationReceipt, EvidenceRevocation, EvidenceRevocationReceipt, EvidenceState,
)
from tools.acquisition_store import acquisition_store

router = APIRouter(prefix='/workspaces/{workspace_id}/campaigns/{campaign_id}/evidence')


async def evidence_rpc(store, name, body):
    try:
        return await store.request('POST', 'rpc/'+name, body=body)
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise


def unconfirmed(message):
    return HTTPException(503, message, headers={'Cache-Control': 'no-store'})


@router.post('')
async def register_evidence(workspace_id: UUID, campaign_id: UUID, body: EvidenceRegistration,
                            response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    result = await evidence_rpc(store, 'register_acquisition_evidence', {
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_purpose': body.purpose, 'p_sha256': body.expected_sha256, 'p_byte_size': body.expected_byte_size,
        'p_media_type': body.media_type, 'p_policy': str(body.retention_policy_id), 'p_note': body.provenance_note})
    try:
        receipt = EvidenceRegistrationReceipt.model_validate(result)
        if (receipt.artifact_id, receipt.workspace_id) != (body.id, workspace_id):
            raise ValueError('Registration scope mismatch')
    except (ValueError, TypeError):
        raise unconfirmed('Evidence registration could not be confirmed; retain the same request for reconciliation') from None
    return result


@router.get('/{artifact_id}')
async def evidence_state(workspace_id: UUID, campaign_id: UUID, artifact_id: UUID,
                          response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    result = await evidence_rpc(store, 'acquisition_evidence_state', {
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_artifact': str(artifact_id)})
    try:
        state = EvidenceState.model_validate(result)
        now = datetime.now(timezone.utc)
        if ((state.workspace_id, state.campaign_id, state.id) != (workspace_id, campaign_id, artifact_id)
                or not now-timedelta(seconds=30) <= state.checked_at <= now+timedelta(seconds=5)):
            raise ValueError('Evidence state scope or freshness mismatch')
    except (ValueError, TypeError):
        raise unconfirmed('Current evidence state could not be confirmed') from None
    return result


@router.post('/{artifact_id}/revocations')
async def revoke_evidence(workspace_id: UUID, campaign_id: UUID, artifact_id: UUID, body: EvidenceRevocation,
                          response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    result = await evidence_rpc(store, 'revoke_acquisition_evidence', {
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_artifact': str(artifact_id), 'p_reason': body.reason})
    try:
        receipt = EvidenceRevocationReceipt.model_validate(result)
        if (receipt.revocation_id, receipt.artifact_id, receipt.workspace_id) != (body.id, artifact_id, workspace_id):
            raise ValueError('Revocation scope mismatch')
    except (ValueError, TypeError):
        raise unconfirmed('Evidence revocation could not be confirmed; retain the same request for reconciliation') from None
    return result
