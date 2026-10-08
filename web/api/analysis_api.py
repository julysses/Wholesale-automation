"""Atomic, recoverable operator estimates; no offer sent or contract implied."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, model_validator
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client

router = APIRouter(prefix='/api/analyses', tags=['Analysis'])
class Comp(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    address: str = Field(max_length=500)
    sqft: float = Field(ge=0, le=1000000)
    sale_price: float = Field(ge=0, le=100000000)
    sale_date: str = Field(max_length=10)
    distance: float = Field(ge=0, le=1000)
class LineItem(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    label: str = Field(max_length=100)
    amount: float = Field(ge=0, le=100000000)
class Inputs(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    address: str = Field(max_length=500)
    sqft: float = Field(ge=0, le=1000000)
    beds: float = Field(ge=0, le=100)
    baths: float = Field(ge=0, le=100)
    condition: Literal['cosmetic','moderate','full_renovation']
    comps: list[Comp] = Field(max_length=6)
    line_items: list[LineItem] = Field(max_length=30)
    arv: float = Field(gt=0, le=100000000)
    repairs: float = Field(ge=0, le=100000000)
    repair_override: float | None = Field(default=None, ge=0, le=100000000)
    assignment_fee: float = Field(ge=0, le=100000000)
    summary: str = Field(max_length=10000)
    @model_validator(mode='after')
    def consistent_repairs(self):
        total = sum(item.amount for item in self.line_items)
        expected = self.repair_override if self.repair_override is not None else total or {'cosmetic':10000,'moderate':37500,'full_renovation':90000}[self.condition]
        if abs(self.repairs - expected) > 0.01:
            raise ValueError('Repair estimate does not match the saved inputs')
        return self
class SaveAnalysis(BaseModel):
    request_id: UUID
    lead_id: UUID
    inputs: Inputs

@router.post('')
async def save_analysis(body: SaveAnalysis, request: Request):
    operator = getattr(request.state,'user_id',None)
    if not operator: raise HTTPException(401,'Sign in to continue')
    try:
        def write():
            return get_supabase_client().rpc('save_manual_analysis', {
                'p_id':str(body.request_id),'p_lead':str(body.lead_id),
                'p_operator':str(operator),'p_inputs':body.inputs.model_dump(),
            }).execute().data
        value = await run_in_threadpool(write)
    except Exception:
        raise HTTPException(503,'Analysis outcome is unconfirmed. Retry the same reference and inputs.')
    if isinstance(value,dict) and value.get('conflict'): raise HTTPException(409,'Analysis reference has different inputs. Recover the original save before creating a new analysis.')
    if isinstance(value,dict) and value.get('missing'): raise HTTPException(404,'Lead not found')
    saved = value.get('analysis') if isinstance(value,dict) else None
    if not isinstance(saved,dict) or saved.get('id') != str(body.request_id) or saved.get('lead_id') != str(body.lead_id):
        raise HTTPException(503,'Analysis outcome is unconfirmed. Retry the same reference and inputs.')
    return {'analysis':saved,'reused':bool(value.get('reused'))}
