"""Administrator controls for reviewed county collection. Never dispatches outreach."""
import hmac
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
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

class ReviewedIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    property_address: str = Field(min_length=1, max_length=300)
    city: str = Field(min_length=1, max_length=100)
    state: Literal['TX']
    zip: str = Field(pattern=r'^[0-9]{5}(-[0-9]{4})?$')
    parcel_id: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=100)

class PropertyReview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_fingerprint: str = Field(pattern='^[a-f0-9]{32}$')
    identity: ReviewedIdentity
    notes: str = Field(min_length=10, max_length=2000)

class ResolveRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: UUID
    batch_index: int = Field(ge=0, le=999)
    ordinal: int = Field(ge=0, le=1999)
    county: str = Field(pattern='^(Dallas|Collin)$')
    evidence_url: str = Field(pattern='^https://', max_length=2000)
    lead_id: UUID | None = None
    active_signal: bool = Field(default=False, strict=True)
    review: PropertyReview

def operator(request):
    value = getattr(request.state, 'user_id', None)
    if not value:
        raise HTTPException(401, 'Sign in to continue')
    return str(value)

@router.get('/api/operations/lists')
async def snapshot(day: date | None = None, offset: int = Query(default=0, ge=0)):
    day = day or datetime.now(ZoneInfo('America/Chicago')).date()
    return await rpc('list_pipeline_snapshot', {'p_day': day.isoformat(), 'p_offset': offset})

@router.get('/api/operations/lists/foreclosures')
async def foreclosure_actions(county: Literal['Dallas', 'Collin'] | None = None, offset: int = Query(default=0, ge=0)):
    day = datetime.now(ZoneInfo('America/Chicago')).date()
    return await rpc('foreclosure_daily_actions', {'p_day': day.isoformat(), 'p_county': county, 'p_offset': offset})

@router.patch('/api/operations/lists/sources/{source_key}')
async def configure(source_key: str, body: ConfigureSource, request: Request):
    if body.enabled and not (body.procedure_version and len(body.procedure_version.strip()) >= 3):
        raise HTTPException(422, 'Review the source procedure and provide its version before enabling delivery.')
    return await rpc('configure_list_source', {'p_key': source_key, 'p_operator': operator(request),
        'p_enabled': body.enabled, 'p_lookback': body.lookback_days, 'p_procedure': body.procedure_version})

@router.post('/api/operations/lists/resolve')
async def resolve(body: ResolveRecord, request: Request):
    value = await rpc('resolve_reviewed_list_record', {'p_run': str(body.run_id), 'p_batch': body.batch_index,
        'p_ordinal': body.ordinal, 'p_operator': operator(request), 'p_county': body.county,
        'p_evidence_url': body.evidence_url, 'p_lead': str(body.lead_id) if body.lead_id else None,
        'p_active': body.active_signal, 'p_review': body.review.model_dump(mode='json')})
    if (not isinstance(value, dict) or not value.get('property_id') or not value.get('lead_id')
            or value.get('outreach_authorized') is not False or value.get('run_id') != str(body.run_id)
            or value.get('batch_index') != body.batch_index or value.get('ordinal') != body.ordinal
            or value.get('review') != body.review.model_dump(mode='json')):
        raise HTTPException(503, 'Property association is unconfirmed. Retry the same evidence.')
    return value

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


class ScoringOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID
    action: Literal['threshold','complete_received']
    expected_version: int | None = Field(default=None, ge=1, le=999999999, strict=True)
    score_threshold: int | None = Field(default=None, ge=0, le=100, strict=True)
    job_id: UUID | None = None

    @model_validator(mode='after')
    def action_fields(self):
        if self.action=='threshold':
            if self.expected_version is None or self.score_threshold is None or self.job_id is not None:
                raise ValueError('Threshold and current version are required')
        elif self.job_id is None or self.expected_version is not None or self.score_threshold is not None:
            raise ValueError('A saved scoring job is required')
        return self

@router.get('/api/operations/lists/scoring')
async def scoring_operations(request: Request, offset: int = Query(default=0,ge=0)):
    return await rpc('list_scoring_operations',{'p_operator':operator(request),'p_offset':offset})

@router.post('/api/operations/lists/scoring/actions')
async def scoring_action(body: ScoringOperation, request: Request):
    actor=operator(request)
    payload=body.model_dump(mode='json',exclude={'event_id','action'},exclude_none=True)
    value=await rpc('apply_list_scoring_operation',{'p_id':str(body.event_id),'p_operator':actor,'p_action':body.action,'p_payload':payload})
    if isinstance(value,dict) and value.get('blocked'):
        raise HTTPException(409,'Scoring action conflicts with current state. Refresh before another action.')
    event=value.get('event') if isinstance(value,dict) else None
    if (not isinstance(event,dict) or event.get('id')!=str(body.event_id) or event.get('operator_id')!=actor
        or event.get('action')!=body.action or event.get('payload')!=payload or not isinstance(event.get('result'),dict)):
        raise HTTPException(503,'Scoring action is unconfirmed. Retry the same event reference.')
    result=event['result']
    if body.action=='threshold':
        confirmed=(type(result.get('score_threshold')) is int and result['score_threshold']==body.score_threshold
            and type(result.get('version')) is int and result['version']==body.expected_version+1)
    else:
        confirmed=(result.get('job_id')==str(body.job_id) and result.get('state') in ('completed','obsolete','review')
            and (result.get('state')!='completed' or result.get('evaluation_id')==str(body.job_id)))
    if not confirmed:
        raise HTTPException(503,'Scoring result is unconfirmed. Retry the same event reference.')
    return value

@router.get('/webhooks/_worker/list-scoring')
async def scoring_worker(authorization: str = Header(default='')):
    secret=os.getenv('CRON_SECRET','')
    if not secret:
        raise HTTPException(503,'Scoring worker secret is not configured')
    if not hmac.compare_digest(authorization,f'Bearer {secret}'):
        raise HTTPException(401,'Unauthorized')
    from tools.list_scoring_worker import process_scoring_batch
    try:
        result=await run_in_threadpool(process_scoring_batch)
    except Exception:
        raise HTTPException(503,'Scoring worker could not confirm its batch. Inspect saved jobs before retrying.')
    return result

@router.get('/api/operations/lists/scoring/jobs/{job_id}')
async def inspect_scoring_job(job_id: UUID, request: Request):
    from fastapi.responses import JSONResponse
    value = await rpc('inspect_list_scoring_job', {'p_operator': operator(request), 'p_id': str(job_id)})
    if isinstance(value, dict) and value.get('blocked') == 'job_missing':
        raise HTTPException(404, 'Scoring job not found')
    job = value.get('job') if isinstance(value, dict) else None
    if (not isinstance(job, dict) or job.get('id') != str(job_id)
        or not isinstance(value.get('freshness'), dict) or value.get('outreach_authorized') is not False):
        raise HTTPException(503, 'Scoring evidence could not be confirmed')
    # Explicit fields prevent internal dispatch credentials from reaching browsers.
    fields = ('id','lead_id','state','requested_model','model_version','prompt_version','model_receipt',
              'input_hash','input_snapshot','assessment','error_code','created_at','claimed_at','received_at','completed_at')
    return JSONResponse({'job': {key: job.get(key) for key in fields}, 'freshness': value['freshness'],
                         'evaluation': value.get('evaluation'), 'outreach_authorized': False},
                        headers={'Cache-Control': 'no-store'})

class LotReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    lead_id: UUID
    input_hash: str = Field(pattern='^[a-f0-9]{64}$')
    is_vacant_lot: bool = Field(strict=True)
    evidence_url: str = Field(pattern=r'^https://\S+$', max_length=2000)
    notes: str = Field(min_length=1, max_length=2000)

class LotHandoff(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    evaluation_id: UUID
    assigned_to: UUID

@router.get('/api/operations/lists/lots')
async def lot_candidates(request: Request, offset: int = Query(default=0, ge=0)):
    return await rpc('list_lot_candidates', {'p_operator': operator(request), 'p_offset': offset})

@router.post('/api/operations/lists/lots/review')
async def review_lot(body: LotReview, request: Request):
    actor = operator(request)
    value = await rpc('review_list_lot', {'p_id':str(body.request_id),'p_operator':actor,'p_lead':str(body.lead_id),
        'p_input_hash':body.input_hash,'p_is_lot':body.is_vacant_lot,'p_evidence':body.evidence_url,'p_notes':body.notes})
    if isinstance(value,dict) and value.get('blocked'):
        raise HTTPException(409, 'Lot review conflicts with current evidence. Refresh before another action.')
    review = value.get('review') if isinstance(value,dict) else None
    expected = {'id':str(body.request_id),'operator_id':actor,'lead_id':str(body.lead_id),'input_hash':body.input_hash,
                'is_vacant_lot':body.is_vacant_lot,'evidence_url':body.evidence_url,'notes':body.notes}
    if not isinstance(review,dict) or any(review.get(key)!=value for key,value in expected.items()):
        raise HTTPException(503, 'Lot review is unconfirmed. Retry the same reference and evidence.')
    return value

@router.post('/api/operations/lists/lots/handoff')
async def handoff_lot(body: LotHandoff, request: Request):
    actor=operator(request)
    value=await rpc('handoff_list_lot',{'p_id':str(body.request_id),'p_operator':actor,'p_evaluation':str(body.evaluation_id),'p_assignee':str(body.assigned_to)})
    if isinstance(value,dict) and value.get('blocked'):
        raise HTTPException(409, 'Lot handoff requires current reviewed evidence, an available assignee and a reconciled land identity. Inspect existing handoffs before retrying.')
    handoff=value.get('handoff') if isinstance(value,dict) else None
    expected={'id':str(body.request_id),'operator_id':actor,'evaluation_id':str(body.evaluation_id),'assigned_to':str(body.assigned_to)}
    if (not isinstance(handoff,dict) or any(handoff.get(key)!=value for key,value in expected.items())
        or not handoff.get('land_lead_id') or not handoff.get('task_id') or value.get('outreach_authorized') is not False):
        raise HTTPException(503, 'Lot handoff is unconfirmed. Retry the same reference.')
    return value

@router.get('/api/land-underwriting/handoffs')
async def received_lot_handoffs(request: Request, offset: int = Query(default=0, ge=0)):
    return await rpc('list_lot_handoffs',{'p_operator':operator(request),'p_offset':offset})

@router.post('/api/land-underwriting/handoffs/{handoff_id}/acknowledge')
async def acknowledge_lot(handoff_id: UUID, request: Request):
    value=await rpc('acknowledge_list_lot',{'p_id':str(handoff_id),'p_operator':operator(request)})
    if isinstance(value,dict) and value.get('blocked'):
        raise HTTPException(409, 'Underwriting destination is unavailable. Inspect the handoff before acknowledgement.')
    handoff=value.get('handoff') if isinstance(value,dict) else None
    if (not isinstance(handoff,dict) or handoff.get('id')!=str(handoff_id) or not handoff.get('acknowledged_by')
        or not handoff.get('acknowledged_at') or value.get('outreach_authorized') is not False):
        raise HTTPException(503, 'Receipt acknowledgement is unconfirmed. Retry the same handoff.')
    return value

@router.get('/webhooks/_worker/list-lots')
async def lot_worker(authorization: str = Header(default='')):
    secret = os.getenv('CRON_SECRET', '')
    if not secret:
        raise HTTPException(503, 'Lot worker secret is not configured')
    if not hmac.compare_digest(authorization, f'Bearer {secret}'):
        raise HTTPException(401, 'Unauthorized')
    from tools.list_lot_worker import process_lot_batch
    try:
        return await run_in_threadpool(process_lot_batch)
    except Exception:
        raise HTTPException(503, 'Lot routing is unconfirmed. Inspect durable handoffs and routing incidents.')

class LotReconciliation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    handoff_id: UUID
    expected_version: int = Field(ge=0, strict=True)
    action: Literal['hold', 'reaffirm']
    evidence_hash: str = Field(pattern='^[a-f0-9]{64}$')
    notes: str = Field(min_length=1, max_length=2000)

@router.post('/api/operations/lists/lots/reconcile')
async def reconcile_lot(body: LotReconciliation, request: Request):
    actor = operator(request)
    value = await rpc('reconcile_list_lot', {'p_id':str(body.request_id),'p_operator':actor,
        'p_handoff':str(body.handoff_id),'p_version':body.expected_version,'p_action':body.action,
        'p_evidence_hash':body.evidence_hash,'p_notes':body.notes})
    if isinstance(value, dict) and value.get('blocked'):
        raise HTTPException(409, 'Reconciliation conflicts with current evidence or a newer decision. Refresh the inbox and review again.')
    event = value.get('event') if isinstance(value, dict) else None
    expected = {'id':str(body.request_id),'handoff_id':str(body.handoff_id),'operator_id':actor,
        'version':body.expected_version+1,'action':body.action,'evidence_hash':body.evidence_hash,'notes':body.notes}
    if (not isinstance(event, dict) or any(event.get(key)!=item for key,item in expected.items())
            or value.get('outreach_authorized') is not False):
        raise HTTPException(503, 'Lot reconciliation is unconfirmed. Retry the same saved decision.')
    return value
