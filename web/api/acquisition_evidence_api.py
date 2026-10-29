"""Scoped evidence metadata and guarded uploads; no download or approval endpoint."""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, Query, Request
from starlette.requests import ClientDisconnect

from schemas.acquisition_evidence import (
    MAX_EVIDENCE_BYTES, EvidenceUploadReceipt, EvidenceCandidates, EvidenceRegistration, EvidenceRegistrationReceipt, EvidenceRevocation, EvidenceRevocationReceipt, EvidenceState,
)
from tools.acquisition_store import acquisition_store, open_acquisition_store
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_upload import EvidenceUploadUnconfirmed

router = APIRouter(prefix='/workspaces/{workspace_id}/campaigns/{campaign_id}/evidence')


async def evidence_rpc(store, name, body):
    try:
        return await store.request('POST', 'rpc/'+name, body=body)
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise


def unconfirmed(message):
    return HTTPException(503, message, headers={'Cache-Control': 'no-store'})


@router.get('')
async def evidence_candidates(workspace_id: UUID, campaign_id: UUID, response: Response,
                              purpose: Literal['mail_content', 'mail_destination'],
                              limit: int = Query(20, ge=1, le=50), after: UUID | None = None,
                              store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    result = await evidence_rpc(store, 'acquisition_evidence_candidates', {
        'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id), 'p_purpose': purpose,
        'p_after': str(after) if after else None, 'p_limit': limit})
    try:
        page = EvidenceCandidates.model_validate(result)
        now = datetime.now(timezone.utc)
        if ((page.workspace_id, page.campaign_id, page.purpose) != (workspace_id, campaign_id, purpose)
                or not now-timedelta(seconds=30) <= page.checked_at <= now+timedelta(seconds=5)
                or len(page.items) > limit or page.next_after is not None and len(page.items) != limit
                or after is not None and any(item.id.int <= after.int for item in page.items)
                or page.current_policy is not None and page.current_policy.valid_until <= now):
            raise ValueError('Evidence discovery scope, page or freshness mismatch')
    except (ValueError, TypeError):
        raise unconfirmed('Current evidence choices could not be confirmed') from None
    return {**result, 'upload_enabled': os.getenv('ACQUISITION_EVIDENCE_UPLOAD_ENABLED', '').lower() == 'true'}


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


async def evidence_upload_store(request: Request):
    if os.getenv('ACQUISITION_EVIDENCE_UPLOAD_ENABLED', '').lower() != 'true':
        raise HTTPException(404, 'Evidence upload is not enabled', headers={'Cache-Control': 'no-store'})
    try:
        async with open_acquisition_store(request) as store:
            yield store
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise


def upload_uncertain():
    return HTTPException(503, {'code': 'EVIDENCE_UPLOAD_UNCONFIRMED',
        'message': 'Upload could not be confirmed. Preserve the same evidence record and exact file for recovery.'},
        headers={'Cache-Control': 'no-store'})


@router.post('/{artifact_id}/bytes')
async def upload_evidence(workspace_id: UUID, campaign_id: UUID, artifact_id: UUID,
                          purpose: Literal['mail_content', 'mail_destination'], request: Request,
                          response: Response, store=Depends(evidence_upload_store)):
    response.headers['Cache-Control'] = 'no-store'
    if set(request.query_params) != {'purpose'} or len(request.query_params.getlist('purpose')) != 1:
        raise HTTPException(422, 'Only one evidence purpose is accepted', headers={'Cache-Control': 'no-store'})
    if (request.headers.getlist('content-type') != ['application/octet-stream']
            or request.headers.getlist('content-encoding') not in ([], ['identity'])
            or 'content-disposition' in request.headers):
        raise HTTPException(415, 'Send the original file as an uncompressed binary stream', headers={'Cache-Control': 'no-store'})
    length_values = request.headers.getlist('content-length')
    declared = None
    if length_values:
        value = length_values[0]
        if len(length_values)!=1 or len(value)>10 or not value.isascii() or not value.isdigit() or int(value)<1:
            raise HTTPException(422, 'A valid file size is required', headers={'Cache-Control': 'no-store'})
        declared = int(value)
        if declared > MAX_EVIDENCE_BYTES:
            raise HTTPException(413, 'Evidence files must be no larger than 10 MiB', headers={'Cache-Control': 'no-store'})

    async def source():
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > MAX_EVIDENCE_BYTES or declared is not None and received > declared:
                raise ValueError('Evidence body length exceeded')
            yield chunk
        if declared is not None and received != declared:
            raise ValueError('Evidence body length mismatch')

    try:
        result = await store.upload_evidence_with_admission(artifact_id, source(), workspace_id=workspace_id,
                                                           campaign_id=campaign_id, purpose=purpose)
    except EvidenceUploadUnconfirmed:
        raise upload_uncertain() from None
    except (EvidenceUnavailable, ClientDisconnect):
        raise HTTPException(409, {'code': 'EVIDENCE_UPLOAD_NOT_ACCEPTED',
            'message': 'The file or current evidence state could not be accepted. Check the evidence record and original file.'},
            headers={'Cache-Control': 'no-store'}) from None
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise
    try:
        receipt = EvidenceUploadReceipt.model_validate(result)
        now = datetime.now(timezone.utc)
        if ((receipt.workspace_id, receipt.campaign_id, receipt.evidence_ref, receipt.purpose)
                != (workspace_id, campaign_id, artifact_id, purpose)
                or receipt.retain_until <= now
                or any(not now-timedelta(seconds=30) <= checked <= now+timedelta(seconds=5)
                       for checked in (receipt.checked_at, receipt.registry_checked_at))):
            raise ValueError('Upload receipt scope or freshness mismatch')
    except (ValueError, TypeError):
        raise upload_uncertain() from None
    return result
