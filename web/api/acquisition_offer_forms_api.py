"""Authenticated form preparation over immutable versions; no public activation."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, Field, StrictBool, StringConstraints, model_validator

from schemas.acquisition_online_offer import Exact, OfferFormDefinition, Version
from tools.acquisition_store import acquisition_store

router = APIRouter(prefix='/workspaces/{workspace_id}/campaigns/{campaign_id}/offer-forms')
Hash = Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9a-f]{64}$')]


class OfferFormDraft(Exact):
    id: UUID
    expected_revision: int = Field(strict=True, ge=0, lt=1000000000)
    definition: OfferFormDefinition

    @model_validator(mode='after')
    def nonblank_wording(self):
        if any(not value.strip() for value in self.definition.model_dump().values()):
            raise ValueError('Form wording is required')
        return self


class OfferFormReceipt(Exact):
    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    form_key: Version
    revision: int = Field(strict=True, ge=1, le=1000000000)
    version: Version
    definition_hash: Hash
    status: Literal['draft']
    duplicate: StrictBool
    public_enabled: StrictBool
    execution_authorized: StrictBool

    @model_validator(mode='after')
    def preparation_only(self):
        if self.public_enabled or self.execution_authorized:
            raise ValueError('Form draft cannot authorize publication')
        return self


class OfferFormVersion(Exact):
    id: UUID
    workspace_id: UUID
    campaign_id: UUID
    acquisition_form_key: Version
    acquisition_form_revision: int = Field(strict=True, ge=1, le=1000000000)
    acquisition_form_version: Version
    acquisition_form_definition: OfferFormDefinition
    acquisition_definition_hash: Hash
    created_at: AwareDatetime
    active: StrictBool
    send_confirmation_sms: StrictBool
    send_confirmation_email: StrictBool

    @model_validator(mode='after')
    def immutable_definition(self):
        if (self.active or self.send_confirmation_sms or self.send_confirmation_email
                or self.acquisition_form_definition.form_key != self.acquisition_form_key
                or self.acquisition_form_definition.version != self.acquisition_form_version):
            raise ValueError('Unexpected form version state')
        if any(not value.strip() for value in self.acquisition_form_definition.model_dump().values()):
            raise ValueError('Form wording missing')
        return self


async def _request(store, *args, **kwargs):
    try:
        return await store.request(*args, **kwargs)
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise


@router.post('')
async def save_offer_form(workspace_id: UUID, campaign_id: UUID, body: OfferFormDraft,
                          response: Response, store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    result = await _request(store, 'POST', 'rpc/save_acquisition_offer_form', body={
        'p_id': str(body.id), 'p_workspace': str(workspace_id), 'p_campaign': str(campaign_id),
        'p_expected_revision': body.expected_revision, 'p_definition': body.definition.model_dump(mode='json'),
    })
    try:
        receipt = OfferFormReceipt.model_validate(result)
        if ((receipt.id, receipt.workspace_id, receipt.campaign_id, receipt.form_key, receipt.version, receipt.revision)
                != (body.id, workspace_id, campaign_id, body.definition.form_key, body.definition.version, body.expected_revision+1)):
            raise ValueError('Saved form identity mismatch')
    except (ValueError, TypeError):
        raise HTTPException(503, 'Form save could not be confirmed. Retry the same saved request.',
                            headers={'Cache-Control': 'no-store'}) from None
    return receipt.model_dump(mode='json')


@router.get('')
async def offer_form_versions(workspace_id: UUID, campaign_id: UUID, response: Response,
                              form_key: str | None = Query(default=None, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$'),
                              after: UUID | None = None, limit: int = Query(default=20, ge=1, le=50),
                              store=Depends(acquisition_store)):
    response.headers['Cache-Control'] = 'no-store'
    params = {'select': ','.join(OfferFormVersion.model_fields),
              'workspace_id': 'eq.'+str(workspace_id), 'campaign_id': 'eq.'+str(campaign_id),
              'acquisition_form_key': 'not.is.null', 'order': 'id', 'limit': str(limit+1)}
    if form_key is not None:
        params['acquisition_form_key'] = 'eq.'+form_key
    if after is not None:
        params['id'] = 'gt.'+str(after)
    result = await _request(store, 'GET', 'lead_form_configs', params=params)
    try:
        if not isinstance(result, list) or len(result)>limit+1:
            raise ValueError('Unexpected form page')
        rows = [OfferFormVersion.model_validate(row) for row in result]
        previous = after
        for row in rows:
            if ((row.workspace_id, row.campaign_id)!=(workspace_id, campaign_id)
                    or (form_key is not None and row.acquisition_form_key!=form_key)
                    or (previous is not None and row.id.int<=previous.int)):
                raise ValueError('Form page identity mismatch')
            previous = row.id
    except (ValueError, TypeError):
        raise HTTPException(503, 'Saved form versions could not be confirmed. Refresh before continuing.',
                            headers={'Cache-Control': 'no-store'}) from None
    return {'items': [row.model_dump(mode='json') for row in rows[:limit]],
            'next_after': str(rows[limit-1].id) if len(rows)>limit else None}
