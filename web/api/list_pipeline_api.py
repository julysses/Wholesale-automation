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


class CancelTrace(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID


@router.get('/api/operations/lists/tracing')
async def tracing_snapshot(request: Request, offset: int = Query(default=0,ge=0)):
    value=await rpc('list_trace_operations',{'p_operator':operator(request),'p_offset':offset})
    if not isinstance(value,dict) or not isinstance(value.get('requests'),list) or type(value.get('open_count')) is not int:
        raise HTTPException(503,'Tracing status could not be confirmed')
    return value


@router.post('/api/operations/lists/tracing/{trace_id}/cancel')
async def cancel_trace(trace_id: UUID, body: CancelTrace, request: Request):
    actor=operator(request)
    value=await rpc('cancel_list_trace_as_operator',{'p_id':str(body.event_id),'p_request':str(trace_id),'p_operator':actor})
    if isinstance(value,dict) and value.get('blocked'):
        raise HTTPException(409,'Reservation is no longer cancelable or the reference conflicts. Refresh its saved status.')
    event=value.get('event') if isinstance(value,dict) else None
    result=event.get('result') if isinstance(event,dict) else None
    row=result.get('request') if isinstance(result,dict) else None
    if (not isinstance(event,dict) or event.get('id')!=str(body.event_id) or event.get('operator_id')!=actor
        or event.get('request_id')!=str(trace_id) or event.get('action')!='cancel_reserved'
        or not isinstance(row,dict) or row.get('id')!=str(trace_id) or row.get('state')!='failed'
        or row.get('actual_cents')!=0 or row.get('provider_job_id')!='not_submitted'):
        raise HTTPException(503,'Cancellation is unconfirmed. Retry the same event reference.')
    return value
