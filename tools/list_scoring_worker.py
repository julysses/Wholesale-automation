"""Bounded scoring worker, disabled until deployment and model acceptance."""
import os
import time
from uuid import UUID
from config.settings import settings
from tools.crm import get_supabase_client
from tools.list_scoring import score_list_lead


def process_scoring_batch(*, db=None, client=None, clock=time.monotonic):
    if os.getenv('LIST_SCORING_ENABLED','false').lower()!='true':
        return {'status':'disabled','selected':0,'completed':0}
    try:
        limit=int(os.getenv('LIST_SCORING_BATCH_SIZE','5'))
    except ValueError as exc:
        raise RuntimeError('Invalid scoring batch size') from exc
    if not 1<=limit<=10:
        raise RuntimeError('Scoring batch size must be between 1 and 10')
    db=db if db is not None else get_supabase_client()
    if db is None:
        raise RuntimeError('Scoring storage unavailable')
    selected=db.rpc('next_list_scoring_jobs',{'p_model':settings.claude_model,'p_limit':limit}).execute().data
    if not isinstance(selected,dict) or not isinstance(selected.get('jobs'),list) or len(selected['jobs'])>limit:
        raise RuntimeError('Scoring selection is unconfirmed')
    jobs=selected['jobs']
    # Validate the whole selection before any external call.
    seen=set()
    for job in jobs:
        if not isinstance(job,dict) or job.get('state') not in ('queued','received') or not isinstance(job.get('requested_model'),str) or not job['requested_model']:
            raise RuntimeError('Invalid scoring job selection')
        UUID(job['id']);UUID(job['lead_id'])
        if job['id'] in seen:raise RuntimeError('Duplicate scoring job selection')
        seen.add(job['id'])
    deadline=clock()+40
    outcomes=[]
    for job in jobs:
        if clock()>=deadline:break
        # Received responses finish without credentials or another model request.
        if job['state']=='queued' and client is None:
            if not settings.anthropic_api_key:
                outcomes.append({'job_id':job['id'],'state':'queued','blocked':'model_not_configured'})
                continue
            import anthropic
            client=anthropic.Anthropic(api_key=settings.anthropic_api_key,max_retries=0,timeout=15.0)
        try:
            result=score_list_lead(db,client,UUID(job['id']),UUID(job['lead_id']),enabled=True,model=job['requested_model'])
            state=result.get('job',{}).get('state')
            outcomes.append({'job_id':job['id'],'state':state or 'unconfirmed','blocked':result.get('blocked')})
        except Exception:
            # Durable submitted/received state survives; never create another ID.
            outcomes.append({'job_id':job['id'],'state':'unconfirmed','blocked':'reconciliation_required'})
    return {'status':'processed','selected':len(jobs),'processed':len(outcomes),
            'completed':sum(row['state']=='completed' for row in outcomes),'deferred':len(jobs)-len(outcomes),'outcomes':outcomes}
