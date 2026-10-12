"""Administrator controls for reviewed county collection. Never dispatches outreach."""
import hmac
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from tools.crm import get_supabase_client

router = APIRouter(tags=['Daily lists'])

async def rpc(name, params):
    try:
        client = get_supabase_client()
        if client is None:
            raise RuntimeError('Database unavailable')
        return await run_in_threadpool(lambda: client.rpc(name, params).execute().data)
    except Exception:
        raise HTTPException(503, 'List operation could not be confirmed. Refresh the receipt before retrying. No outreach was sent.')

class ConfigureSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    lookback_days: int = Field(ge=1, le=365)
    procedure_version: str | None = Field(default=None, max_length=200)

class ResolveRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: UUID
    batch_index: int = Field(ge=0, le=999)
    ordinal: int = Field(ge=0, le=1999)
    county: str = Field(pattern='^(Dallas|Collin)$')
    evidence_url: str = Field(pattern='^https://', max_length=2000)
    lead_id: UUID | None = None
    active_signal: bool = True

def operator(request):
    value = getattr(request.state, 'user_id', None)
    if not value:
        raise HTTPException(401, 'Sign in to continue')
    return str(value)

@router.get('/api/operations/lists')
async def snapshot(day: date | None = None, offset: int = Query(default=0, ge=0)):
    day = day or datetime.now(ZoneInfo('America/Chicago')).date()
    return await rpc('list_pipeline_snapshot', {'p_day': day.isoformat(), 'p_offset': offset})

@router.patch('/api/operations/lists/sources/{source_key}')
async def configure(source_key: str, body: ConfigureSource, request: Request):
    if body.enabled and not (body.procedure_version and len(body.procedure_version.strip()) >= 3):
        raise HTTPException(422, 'Review the source procedure and provide its version before enabling delivery.')
    return await rpc('configure_list_source', {'p_key': source_key, 'p_operator': operator(request),
        'p_enabled': body.enabled, 'p_lookback': body.lookback_days, 'p_procedure': body.procedure_version})

@router.post('/api/operations/lists/resolve')
async def resolve(body: ResolveRecord, request: Request):
    return await rpc('resolve_list_record', {'p_run': str(body.run_id), 'p_batch': body.batch_index,
        'p_ordinal': body.ordinal, 'p_operator': operator(request), 'p_county': body.county,
        'p_evidence_url': body.evidence_url, 'p_lead': str(body.lead_id) if body.lead_id else None,
        'p_active': body.active_signal})

@router.post('/api/operations/lists/scan')
async def scan():
    return await rpc('scan_list_pipeline', {})

@router.get('/webhooks/_worker/daily-lists')
async def worker(authorization: str = Header(default='')):
    secret = os.getenv('CRON_SECRET', '')
    if not secret:
        raise HTTPException(503, 'List worker secret is not configured')
    if not hmac.compare_digest(authorization, f'Bearer {secret}'):
        raise HTTPException(401, 'Unauthorized')
    summary = await scan()
    if summary.get('busy') is True:
        return summary
    from tools.list_digest import deliver_digest
    try:
        delivery = await run_in_threadpool(deliver_digest, summary)
    except Exception:
        raise HTTPException(503, 'Digest delivery could not be confirmed. Inspect its saved receipt before retrying.')
    return {**summary, 'digest_delivery': delivery}
