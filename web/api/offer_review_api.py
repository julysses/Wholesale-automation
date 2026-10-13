"""Versioned human offer decisions. This API never dispatches an offer."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Query
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
    reviewed_content_id: UUID | None = None

    @model_validator(mode='after')
    def shape(self):
        if (self.action == 'approve' and self.reviewed_content_id != self.revision_id) or (self.action != 'approve' and self.reviewed_content_id is not None):
            raise ValueError('Approval requires the displayed content revision')
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
    value = await rpc('record_offer_review_v2', {
        'p_id': str(body.request_id), 'p_lead': str(lead_id), 'p_expected': body.expected_version,
        'p_action': body.action, 'p_revision': str(body.revision_id),
        'p_reviewed_content': str(body.reviewed_content_id) if body.reviewed_content_id else None,
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

@router.get('/{lead_id}/history')
async def history(lead_id: UUID, request: Request, before: int | None = Query(default=None, ge=0)):
    value = await rpc('offer_review_history', {'p_lead': str(lead_id), 'p_before': before}, request)
    valid = isinstance(value, dict) and value.get('lead_id') == str(lead_id)
    events = value.get('events') if valid else None
    cursor = value.get('next_before') if valid else None
    valid = valid and isinstance(events, list) and len(events) <= 50
    previous = before
    for event in events if valid else []:
        version = event.get('expected_version') if isinstance(event, dict) else None
        if (type(version) is not int or version < 0 or event.get('lead_id') != str(lead_id)
            or (previous is not None and version >= previous)):
            valid = False
            break
        previous = version
    if cursor is not None and (type(cursor) is not int or not events or len(events) != 50 or cursor != previous):
        valid = False
    if not valid:
        raise HTTPException(503, 'Offer history could not be confirmed')
    return value
