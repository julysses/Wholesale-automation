"""User-scoped acquisition persistence. Never substitute service-role credentials."""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException, Request


class AcquisitionStore:
    def __init__(self, client):
        self.client = client

    async def admit_evidence_upload(self, artifact_id, *, workspace_id, campaign_id, purpose):
        from tools.acquisition_evidence_admission import admit_evidence_upload
        return await admit_evidence_upload(self, artifact_id, workspace_id=workspace_id,
                                          campaign_id=campaign_id, purpose=purpose)

    async def upload_evidence_with_admission(self, artifact_id, source, *, workspace_id, campaign_id, purpose):
        from tools.acquisition_evidence_admission import upload_with_admission
        return await upload_with_admission(self, artifact_id, source, workspace_id=workspace_id,
                                           campaign_id=campaign_id, purpose=purpose)

    async def persist_evidence_attestation(self, signed_request, *, workspace_id, campaign_id, artifact_id, actor_id, session_id):
        """One bounded write of the original signed request; never regenerate on retry."""
        from tools.acquisition_evidence_persistence import persist_evidence_attestation
        return await persist_evidence_attestation(self.client, signed_request, workspace_id=workspace_id,
            campaign_id=campaign_id, artifact_id=artifact_id, actor_id=actor_id, session_id=session_id)

    async def scan_evidence(self, artifact_id, *, workspace_id, campaign_id, purpose, policy):
        """Internal reviewed local scanner; no public or persistent approval authority."""
        from tools.acquisition_evidence_scan import scan_registered_evidence
        return await scan_registered_evidence(self.client, artifact_id, workspace_id=workspace_id,
                                              campaign_id=campaign_id, purpose=purpose, policy=policy)

    async def verify_evidence(self, artifact_id, *, workspace_id, campaign_id, purpose):
        """Resolve protected registry state; callers supply identity only, never expectations."""
        from tools.acquisition_evidence import verify_registered_evidence
        return await verify_registered_evidence(self.client, artifact_id, workspace_id=workspace_id,
                                                campaign_id=campaign_id, purpose=purpose)

    async def upload_evidence(self, artifact_id, source, *, workspace_id, campaign_id, purpose):
        """Internal bounded upload; preserves identity for uncertain-outcome recovery."""
        from tools.acquisition_evidence_upload import upload_registered_evidence
        return await upload_registered_evidence(self.client, artifact_id, source, workspace_id=workspace_id,
                                                campaign_id=campaign_id, purpose=purpose)

    async def request(self, method, path, *, params=None, body=None):
        try:
            response = await self.client.request(method, path, params=params, json=body)
        except httpx.HTTPError:
            raise HTTPException(503, 'Acquisition database is unavailable') from None
        if response.status_code >= 300:
            # Never leak SQL details, auth tokens or raw provider responses.
            try:
                code = response.json().get('code')
            except (ValueError, AttributeError):
                code = None
            if response.status_code == 401:
                raise HTTPException(401, 'Session is invalid or expired')
            if response.status_code == 403 or code == '42501':
                raise HTTPException(403, 'Workspace access is not authorized')
            if code == '55000':
                raise HTTPException(409, 'Operation is unavailable in the current acquisition state')
            if code == '40001':
                raise HTTPException(409, 'Workspace state changed; refresh before trying again')
            if code in {'22023', '23503', '23505', '23514'}:
                raise HTTPException(409, 'Request conflicts with workspace state')
            raise HTTPException(503, 'Acquisition database request could not be completed')
        try:
            return response.json()
        except ValueError:
            raise HTTPException(503, 'Acquisition database returned an invalid response') from None


@asynccontextmanager
async def open_acquisition_store(request: Request):
    if os.getenv('ACQUISITION_ENABLED', '').lower() != 'true':
        raise HTTPException(404, 'Acquisition workspace is not enabled')
    scheme, _, token = request.headers.get('authorization', '').partition(' ')
    if scheme.lower() != 'bearer' or not token or len(token) > 16384 or any(c.isspace() for c in token):
        raise HTTPException(401, 'Sign in to continue')
    url = (os.getenv('VITE_SUPABASE_URL') or os.getenv('SUPABASE_URL') or '').rstrip('/')
    key = (os.getenv('SUPABASE_PUBLISHABLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
           or os.getenv('VITE_SUPABASE_ANON_KEY') or '')
    if not url.startswith('https://') or not key:
        raise HTTPException(503, 'Acquisition database is not configured')
    async with httpx.AsyncClient(
        base_url=url+'/rest/v1/', timeout=15.0, follow_redirects=False,
        headers={'apikey': key, 'Authorization': 'Bearer '+token},
    ) as client:
        yield AcquisitionStore(client)


async def acquisition_store(request: Request):
    async with open_acquisition_store(request) as store:
        yield store
