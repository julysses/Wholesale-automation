"""Validated valuation evidence with immutable save receipts; never sets offers."""
from datetime import date as Date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client

router = APIRouter(prefix='/api/land-underwriting/valuations', tags=['Land valuation'])

class CompInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    address: str = Field(min_length=1, max_length=500)
    price: float = Field(gt=0, le=9999999999.99, multiple_of=0.01, strict=True)
    sqft: float | None = Field(default=None, gt=0, le=1000000000000, strict=True)
    date: Date | None = None
    distance_mi: float | None = Field(default=None, ge=0, le=10000, strict=True)
    source_url: str | None = Field(default=None, pattern=r'^https://\S+$', max_length=2000)

    @field_validator('address')
    @classmethod
    def address_present(cls, value):
        if not value.strip(): raise ValueError('Comparable address is required')
        return value

    @field_validator('date')
    @classmethod
    def not_future(cls, value):
        if value and value > datetime.now(ZoneInfo('America/Chicago')).date():
            raise ValueError('Sale date cannot be in the future')
        return value

class ValuationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    direct_comp_details: list[CompInput] = Field(max_length=50)
    avg_house_arv: float | None = Field(default=None, gt=0, le=9999999999.99, multiple_of=0.01, strict=True)
    house_comp_count: int | None = Field(default=None, ge=1, le=10000, strict=True)
    tav: float | None = Field(default=None, ge=0, le=9999999999.99, multiple_of=0.01, strict=True)
    tav_source: Literal['county', 'xleads', 'manual']
    tav_assessment_date: Date | None = None
    comp_notes: str = Field(max_length=10000)

    @model_validator(mode='after')
    def consistent_inputs(self):
        if (self.avg_house_arv is None) != (self.house_comp_count is None):
            raise ValueError('House ARV and count must be provided together')
        if self.tav_assessment_date and (self.tav is None or self.tav_assessment_date > datetime.now(ZoneInfo('America/Chicago')).date()):
            raise ValueError('Assessment date requires TAV and cannot be in the future')
        if not self.direct_comp_details and self.avg_house_arv is None and self.tav is None:
            raise ValueError('At least one valuation input is required')
        return self

class ValuationSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_hash: str = Field(pattern='^[a-f0-9]{64}$')
    payload: ValuationInput

async def rpc(name, params, request):
    actor = getattr(request.state, 'user_id', None)
    if not actor: raise HTTPException(401, 'Sign in to continue')
    try:
        return await run_in_threadpool(lambda: get_supabase_client().rpc(name, {**params, 'p_operator':str(actor)}).execute().data)
    except Exception:
        raise HTTPException(503, 'Valuation storage is unconfirmed. Retry the original saved request.')

@router.get('/{land_id}')
async def read(land_id: UUID, request: Request):
    value = await rpc('read_land_valuation', {'p_land':str(land_id)}, request)
    if isinstance(value, dict) and value.get('blocked') == 'land_missing':
        raise HTTPException(404, 'Land record not found')
    if (not isinstance(value, dict) or value.get('land_lead_id') != str(land_id)
            or not isinstance(value.get('snapshot_hash'),str) or len(value['snapshot_hash']) != 64
            or type(value.get('record_count')) is not int or value['record_count'] < 0
            or value.get('outreach_authorized') is not False):
        raise HTTPException(503, 'Saved valuation could not be confirmed')
    return JSONResponse(value, headers={'Cache-Control':'no-store'})

@router.post('/{land_id}')
async def save(land_id: UUID, body: ValuationSave, request: Request):
    payload=body.payload.model_dump(mode='json')
    value=await rpc('save_land_valuation',{'p_id':str(body.request_id),'p_land':str(land_id),
        'p_expected_hash':body.expected_hash,'p_payload':payload},request)
    if isinstance(value,dict) and value.get('blocked'):
        raise HTTPException(409, 'Valuation inputs or saved record changed. Reload the current analysis and review before saving again.')
    event=value.get('event') if isinstance(value,dict) else None
    expected={'id':str(body.request_id),'land_lead_id':str(land_id),'operator_id':str(request.state.user_id),
              'expected_hash':body.expected_hash,'payload':payload}
    saved=event.get('saved_snapshot') if isinstance(event,dict) else None
    comp=saved.get('comp') if isinstance(saved,dict) else None
    if (not isinstance(event,dict) or any(event.get(key)!=item for key,item in expected.items())
            or not isinstance(comp,dict) or comp.get('id')!=event.get('comp_id') or comp.get('land_lead_id')!=str(land_id)
            or saved.get('land_lead_id')!=str(land_id) or value.get('outreach_authorized') is not False):
        raise HTTPException(503, 'Valuation receipt is unconfirmed. Retry the original saved request.')
    return value
