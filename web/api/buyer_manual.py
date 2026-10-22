"""Recoverable manual buyer creation. Never infer consent or send outreach."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client


class ReceiptResponse(JSONResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headers['Cache-Control'] = 'no-store'
        self.headers['Referrer-Policy'] = 'no-referrer'


router = APIRouter(prefix='/api/buyers/manual', tags=['Manual buyers'], default_response_class=ReceiptResponse)


class ManualBuyer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    first_name: str = Field(min_length=1, max_length=300)
    last_name: str = Field(min_length=1, max_length=300)
    company: str = Field(default='', max_length=500)
    email: str = Field(default='', max_length=320)
    phone: str = Field(default='', max_length=80)
    source: str = Field(default='', max_length=80)
    tier: Literal['A', 'B', 'C'] = 'C'
    target_zips: list[str] = Field(default_factory=list, max_length=100)
    min_price: float | None = Field(default=None, ge=0, le=1000000000)
    max_price: float | None = Field(default=None, ge=0, le=1000000000)
    strategy: list[Literal['fix_flip', 'buy_hold', 'brrrr', 'str']] = Field(default_factory=list, max_length=4)
    property_types: list[Literal['SFR', 'duplex', 'MFR', 'land', 'condo']] = Field(default_factory=list, max_length=5)
    close_speed_days: int | None = Field(default=None, ge=0, le=10000)
    pof_verified: StrictBool = False
    pof_amount: float | None = Field(default=None, ge=0, le=1000000000)
    notes: str = Field(default='', max_length=10000)
    active: StrictBool = True
    buys_land: StrictBool = False
    buys_infill: StrictBool = False
    land_buyer_type: Literal['builder', 'land_banker', 'trailer_park', 'mineral_rights'] | None = None

    @model_validator(mode='after')
    def valid_preferences(self):
        if any(len(z) > 20 for z in self.target_zips):
            raise ValueError('Target ZIP entries are too long')
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError('Minimum price cannot exceed maximum price')
        return self


class CreateManualBuyer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    buyer: ManualBuyer


def execute(name, params):
    db = get_supabase_client()
    if db is None:
        raise HTTPException(503, 'Buyer storage is unavailable. Keep the same save reference.')
    try:
        value = db.rpc(name, params).execute().data
        if (not isinstance(value, dict) or value.get('id') != params['p_id']
                or value.get('state') not in {'saved', 'canceled', 'pending'}
                or type(value.get('saved')) is not bool):
            raise ValueError('Unconfirmed receipt')
        if value['state'] == 'saved':
            snapshot = value.get('buyer')
            if (value['saved'] is not True or value.get('buyer_id') != params['p_id']
                    or not isinstance(snapshot, dict) or snapshot.get('id') != params['p_id']
                    or snapshot.get('sms_opt_in') is not False or snapshot.get('email_opt_in') is not False
                    or type(value.get('current_exists')) is not bool):
                raise ValueError('Unconfirmed buyer snapshot')
        elif value['saved'] is not False:
            raise ValueError('Invalid receipt state')
        return value
    except HTTPException:
        raise
    except Exception as exc:
        code = getattr(exc, 'pgcode', None) or getattr(exc, 'code', None)
        if code == '42501':
            raise HTTPException(403, 'An approved operator must recover their own save') from None
        if code in {'22023', '23505', '23514', '22P02', '22003'}:
            raise HTTPException(409, 'Buyer details or identity require review. Recover or stop this request before another save.') from None
        raise HTTPException(503, 'Buyer save is unconfirmed. Keep the original details and reference.') from None


def operator(request):
    identity = getattr(request.state, 'user_id', None)
    if not identity:
        raise HTTPException(401, 'Sign in to manage buyers')
    return identity


@router.post('')
async def create(body: CreateManualBuyer, request: Request):
    return await run_in_threadpool(execute, 'create_manual_buyer', {
        'p_id': str(body.request_id), 'p_operator': operator(request),
        'p_payload': body.buyer.model_dump(mode='json'),
    })


@router.get('/{request_id}')
async def receipt(request_id: UUID, request: Request):
    return await run_in_threadpool(execute, 'manual_buyer_receipt', {
        'p_id': str(request_id), 'p_operator': operator(request),
    })


@router.post('/{request_id}/cancel')
async def cancel(request_id: UUID, request: Request):
    return await run_in_threadpool(execute, 'cancel_manual_buyer', {
        'p_id': str(request_id), 'p_operator': operator(request),
    })
