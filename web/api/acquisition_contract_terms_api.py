"""Sourced draft term versions; saved history does not confer current approval."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, Field, StrictBool, model_validator

from schemas.acquisition_contract_terms import Exact, ContractTermsDraft, ContractTermsRequest
from tools.acquisition_store import acquisition_store
from web.api.acquisition_contracts_api import request

router = APIRouter(prefix='/workspaces/{workspace_id}/contracts/{contract_id}')


class ContractTermsReceipt(Exact):
    request_id: UUID
    workspace_id: UUID
    contract_id: UUID
    version: int = Field(strict=True, ge=2, le=2147483647)
    status: Literal['draft']
    duplicate: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def preparation_only(self):
        if self.execution_authorized:
            raise ValueError('Terms cannot authorize execution')
        return self


class ContractVersionRecord(Exact):
    id: UUID
    workspace_id: UUID
    deal_id: UUID
    version: int = Field(strict=True, ge=1, le=2147483647)
    status: Literal['draft']
    previous_version: int | None = Field(strict=True, ge=1, le=2147483646)
    terms: ContractTermsDraft | None
    actor_id: UUID
    created_at: AwareDatetime

    @model_validator(mode='after')
    def exact_version(self):
        if self.version == 1:
            if self.previous_version is not None or self.terms is not None:
                raise ValueError('Original draft has no sourced terms')
        elif self.previous_version != self.version - 1 or self.terms is None:
            raise ValueError('Version must preserve its predecessor and terms')
        if self.terms is not None and any(s.artifact_version >= self.version for s in self.terms.sources):
            raise ValueError('Term sources must retain their original earlier version')
        return self


@router.post('/terms')
async def save_contract_terms(workspace_id: UUID, contract_id: UUID, body: ContractTermsRequest,
                              response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    try:
        raw = await request(store, 'POST', 'rpc/save_contract_terms', body={
            'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_contract': str(contract_id),
            'p_expected_version': body.expected_version, 'p_terms': body.terms.model_dump(mode='json')})
    except HTTPException as error:
        if error.status_code in {401, 403, 409}:
            # Settles only this attempt, never an earlier lost reply.
            error.headers = {**(error.headers or {}), 'X-Acquisition-Terms-Rejected': 'true'}
        raise
    try:
        receipt = ContractTermsReceipt.model_validate(raw)
        if (receipt.request_id, receipt.workspace_id, receipt.contract_id, receipt.version) != (
                body.id, workspace_id, contract_id, body.expected_version + 1):
            raise ValueError('Saved version identity mismatch')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Terms save is unconfirmed. Retry the same saved request and details.',
                            headers={'Cache-Control': 'no-store'}) from None
    return receipt.model_dump(mode='json')


@router.get('/versions')
async def contract_versions(workspace_id: UUID, contract_id: UUID, response: Response,
                            after: int | None = Query(default=None, ge=1, le=2147483647),
                            limit: int = Query(default=20, ge=1, le=50), store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    params = {'select': ','.join(ContractVersionRecord.model_fields), 'workspace_id': 'eq.' + str(workspace_id),
              'deal_id': 'eq.' + str(contract_id), 'order': 'version', 'limit': str(limit + 1)}
    if after is not None:
        params['version'] = 'gt.' + str(after)
    raw = await request(store, 'GET', 'acquisition_contract_versions', params=params)
    try:
        if not isinstance(raw, list) or len(raw) > limit + 1:
            raise ValueError('Unexpected version page')
        rows = [ContractVersionRecord.model_validate(row) for row in raw]
        previous = after or 0
        seen = set()
        for row in rows:
            if (row.workspace_id, row.deal_id) != (workspace_id, contract_id) or row.version <= previous or row.id in seen:
                raise ValueError('Version page scope or sequence mismatch')
            seen.add(row.id)
            previous = row.version
    except (ValueError, TypeError):
        raise HTTPException(503, 'Contract history could not be confirmed. Refresh before continuing.',
                            headers={'Cache-Control': 'no-store'}) from None
    return {'workspace_id': str(workspace_id), 'contract_id': str(contract_id),
            'items': [row.model_dump(mode='json') for row in rows[:limit]],
            'next_after': rows[limit - 1].version if len(rows) > limit else None,
            'execution_authorized': False}
