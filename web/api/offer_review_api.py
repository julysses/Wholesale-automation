"""Versioned human offer decisions. This API never dispatches an offer."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client

router = APIRouter(prefix='/api/operations/offers', tags=['Offer review'])

class Terms(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    price: Decimal = Field(gt=0, le=100000000, decimal_places=2)
    closing_date: date
    expires_at: AwareDatetime
    recipient: str = Field(min_length=1, max_length=320)
    channel: Literal['manual', 'email', 'sms']
    conditions: str = Field(min_length=1, max_length=10000)

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: int = Field(ge=0)
    action: Literal['draft', 'approve', 'revoke']
    revision_id: UUID
    terms: Terms | None = None

    @model_validator(mode='after')
    def shape(self):
        if self.action == 'draft':
            if self.terms is None or self.revision_id != self.request_id:
                raise ValueError('A new draft needs terms and matching request/revision IDs')
        elif self.terms is not None:
            raise ValueError('Approve or revoke the saved revision; do not replace its terms')
        return self

async def rpc(name, params, request):
    operator = getattr(request.state, 'user_id', None)
    if not operator:
        raise HTTPException(401, 'Sign in to continue')
    try:
        return await run_in_threadpool(lambda: get_supabase_client().rpc(name, {
            **params, 'p_operator': str(operator),
        }).execute().data)
    except Exception:
        raise HTTPException(503, 'Offer review outcome is unconfirmed. Refresh, or retry the same reference and details. Nothing was sent.')

@router.get('/{lead_id}')
async def snapshot(lead_id: UUID, request: Request):
    result = await rpc('offer_review_snapshot', {'p_lead': str(lead_id)}, request)
    if not isinstance(result, dict) or result.get('lead_id') != str(lead_id) or result.get('outbound_enabled') is not False:
        raise HTTPException(503, 'Offer review could not be confirmed')
    return result

@router.post('/{lead_id}')
async def decide(lead_id: UUID, body: Decision, request: Request):
    value = await rpc('record_offer_review', {
        'p_id': str(body.request_id), 'p_lead': str(lead_id), 'p_expected': body.expected_version,
        'p_action': body.action, 'p_revision': str(body.revision_id),
        'p_terms': body.terms.model_dump(mode='json') if body.terms else None,
    }, request)
    if isinstance(value, dict):
        if value.get('conflict'): raise HTTPException(409, 'Offer terms or review version changed. Refresh before acting.')
        if value.get('missing'): raise HTTPException(404, 'Lead not found')
        if value.get('invalid') or value.get('expired'): raise HTTPException(422, 'Review recipient, price, conditions and dates. Expired offers cannot be approved.')
        event, current = value.get('event'), value.get('current')
        if (isinstance(event, dict) and event.get('id') == str(body.request_id)
            and event.get('lead_id') == str(lead_id) and event.get('action') == body.action
            and event.get('revision_id') == str(body.revision_id)
            and event.get('operator_id') == str(getattr(request.state, 'user_id', ''))
            and event.get('expected_version') == body.expected_version
            and event.get('terms') == (body.terms.model_dump(mode='json') if body.terms else None)
            and isinstance(current, dict) and current.get('lead_id') == str(lead_id)
            and type(current.get('version')) is int and current['version'] >= body.expected_version + 1
            and current.get('outbound_enabled') is False):
            return value
    raise HTTPException(503, 'Offer review outcome is unconfirmed. Retry the same reference and details. Nothing was sent.')
