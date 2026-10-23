"""Correlated atomic CSV intake and one-way optional model scoring."""
import json
import logging
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, Request
from tools.crm import get_supabase_client

logger = logging.getLogger(__name__)


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('Invalid canonical UUID')
    return value


def _data_receipt(value, reference, operator, rows, options):
    try:
        receipt = value['receipt']; result = receipt['result']
        if (receipt['id'] != reference or receipt['operator_id'] != operator
            or receipt['payload'] != rows or receipt['options'] != options
            or type(value['replayed']) is not bool or value['outreach_authorized'] is not False):
            raise ValueError('Uncorrelated receipt')
        counts = ['imported','existing','owner_review','scored','scoring_eligible']
        if any(type(result.get(k)) is not int or result[k] < 0 for k in counts):
            raise ValueError('Unconfirmed counts')
        if (result['imported']+result['existing'] != len(rows) or result['owner_review']>result['existing']
            or result['scored']>result['scoring_eligible'] or result['scoring_eligible']>len(rows)):
            raise ValueError('Invalid counts')
        _uuid(result['intake_owner_id'])
        expected_state = 'disabled' if not options['score_on_import'] else 'completed' if options['engine']=='rules' else 'pending'
        if result['scoring_state'] != expected_state or (expected_state!='completed' and result['scored']!=0):
            raise ValueError('Scoring does not match import options')
        if options['list_name']:
            _uuid(result['list_id'])
        elif result['list_id'] is not None:
            raise ValueError('Unexpected list')
        mappings = result['rows']
        if not isinstance(mappings,list) or len(mappings)!=len(rows):
            raise ValueError('Unconfirmed row linkage')
        ids=[]; tasks=[]
        for mapping in mappings:
            ids.append(_uuid(mapping['lead_id']))
            if type(mapping['created']) is not bool:
                raise ValueError('Unconfirmed creation outcome')
            if mapping['created']:
                tasks.append(_uuid(mapping['task_id']))
            elif mapping['task_id'] is not None:
                raise ValueError('Unexpected task for existing work')
        if len(set(ids))!=len(rows) or len(tasks)!=result['imported'] or len(set(tasks))!=len(tasks):
            raise ValueError('Conflicting row/task linkage')
        return result
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(503,'Import receipt is unconfirmed. Check or retry the original import reference.')


def _scoring_result(value, reference, operator, eligible, *, claim=None):
    if not isinstance(value,dict) or value.get('import_id')!=reference or value.get('operator_id')!=operator:
        raise ValueError('Uncorrelated scoring receipt')
    if claim is not None and value.get('claim_id')!=claim:
        raise ValueError('Uncorrelated scoring claim')
    state=value.get('state'); result=value.get('result')
    if state not in {'pending','submitting','completed','review'} or not isinstance(result,dict):
        raise ValueError('Unconfirmed scoring state')
    if (any(type(result.get(k)) is not int or result[k]<0 for k in ['scored','held','remaining','in_flight'])
        or sum(result[k] for k in ['scored','held','remaining','in_flight'])!=eligible
        or (state=='completed' and any(result[k]!=0 for k in ['held','remaining','in_flight']))
        or (state=='submitting' and not 1<=result['in_flight']<=25)
        or (state=='pending' and (result['remaining']==0 or result['in_flight']!=0))
        or (state=='review' and result['in_flight']!=0)):
        raise ValueError('Unconfirmed scoring counts')
    return state,result


def _score_import(db, reference, operator, result, rows, scorer, *, initial_only=False):
    from . import _lead_import_key
    claim=str(uuid4()); eligible=result['scoring_eligible']
    try:
        value=db.rpc('claim_csv_import_scoring',{'p_id':reference,'p_operator':operator,'p_claim':claim,'p_initial_only':initial_only}).execute().data
        state,counts=_scoring_result(value,reference,operator,eligible)
        if type(value.get('claimed')) is not bool:
            raise ValueError('Unconfirmed claim')
        if not value['claimed']:
            return state,counts
        if value.get('claim_id')!=claim or state!='submitting':
            raise ValueError('Uncorrelated dispatch claim')
        snapshots=value.get('snapshots')
        if not isinstance(snapshots,list) or not snapshots or len(snapshots)>min(25,eligible):
            raise ValueError('Unconfirmed scoring snapshots')
        expected={m['lead_id']:_lead_import_key(row) for m,row in zip(result['rows'],rows)} if rows is not None else None
        ids=[_uuid(row['id']) for row in snapshots]
        batch_ids=value.get('batch_lead_ids')
        if not isinstance(batch_ids,list) or not 1<=len(batch_ids)<=25 or len(set(batch_ids))!=len(batch_ids):
            raise ValueError('Unconfirmed bounded batch')
        for lead_id in batch_ids: _uuid(lead_id)
        _uuid(value.get('batch_id'))
        if (len(set(ids))!=len(ids) or not set(ids)<=set(batch_ids)
            or (expected is not None and any(row['id'] not in expected or _lead_import_key(row)!=expected[row['id']] for row in snapshots))):
            raise ValueError('Scoring properties do not match this import')
        leads=[{'lead_id':row['id'],**{key:row.get(key) for key in [
            'property_address','city','state','owner_first_name','owner_last_name','source',
            'motivation_tag','seller_notes','internal_notes','property_type']}} for row in snapshots]
    except Exception:
        logger.warning('CSV data saved; AI claim response unconfirmed for import %s',reference)
        return 'unconfirmed',None
    try:
        scores=scorer(leads,single_attempt=True)
    except Exception:
        # A provider timeout may still have spent money. Record review if possible;
        # neither this request nor a replay is allowed to dispatch the claim again.
        scores=None
    try:
        finished=db.rpc('finish_csv_import_scoring',{'p_id':reference,'p_operator':operator,'p_claim':claim,'p_scores':scores}).execute().data
        state,counts=_scoring_result(finished,reference,operator,eligible,claim=claim)
        if state not in {'pending','completed','review'}:
            raise ValueError('Scoring result not terminal')
        return state,counts
    except Exception:
        logger.warning('CSV data saved; AI result response unconfirmed for import %s',reference)
        return 'unconfirmed',None


def execute_import(body, request: Request, scorer):
    from . import _payload_from_import_row, _lead_import_key, _merge_payloads
    operator=getattr(request.state,'user_id',None)
    if not operator:
        raise HTTPException(401,'Sign in to continue')
    try:
        operator=_uuid(str(operator))
    except ValueError:
        raise HTTPException(401,'Sign in to continue')
    incoming={}; skipped=0
    try:
        for row in body.rows:
            payload=_payload_from_import_row(row)
            if not payload.get('property_address') or not payload.get('city'):
                skipped+=1; continue
            key=_lead_import_key(payload)
            incoming[key]=_merge_payloads(incoming.get(key,{}),payload)
    except (ValueError, TypeError, ArithmeticError):
        raise HTTPException(422,'An import value has an invalid number, precision, range or state code. No rows were saved.')
    if not incoming:
        raise HTTPException(400,'No importable rows with property_address and verified city')
    rows=list(incoming.values())
    options={'score_on_import':body.score_with_claude,'engine':body.engine,
        'list_name':(body.list_name or '').strip()[:120], 'filename':(body.filename or '')[:200] or None}
    # Legacy callers also get stable same-payload retry identity. Modern callers
    # retain an explicit UUID per prepared upload; no timestamp enters this key.
    reference=str(body.request_id or uuid5(NAMESPACE_URL,'wholesaleos:csv:'+operator+':'+json.dumps(
        {'rows':rows,'options':options},sort_keys=True,separators=(',',':'))))
    db=get_supabase_client()
    if db is None:
        raise HTTPException(503,'Supabase service role is not configured')
    try:
        value=db.rpc('import_csv_leads',{'p_id':reference,'p_operator':operator,'p_rows':rows,'p_options':options}).execute().data
    except Exception as exc:
        code=getattr(exc,'code',None) or getattr(exc,'pgcode',None)
        if code=='22023':
            raise HTTPException(409,'Import refused: review the original reference, approved intake owner and ambiguous existing properties. No partial batch was saved.')
        if code in {'22P02','22003','23514'}:
            raise HTTPException(422,'An import field violates the database format or range. No rows in this batch were saved.')
        raise HTTPException(503,'Import outcome is unconfirmed. Check or retry the original import reference.')
    result=_data_receipt(value,reference,operator,rows,options)
    state=result['scoring_state']; counts={'scored':result['scored'],'held':0,'remaining':0,'in_flight':0}
    if state=='pending':
        state,counts=_score_import(db,reference,operator,result,rows,scorer,initial_only=True)
    warnings=[]
    warning=_progress_warning(state,counts)
    if warning: warnings.append(warning)
    if result['owner_review']:
        warnings.append(f"{result['owner_review']} existing leads need ownership review; their saved assignments were preserved.")
    return {'status':'ok','request_id':reference,'replayed':value['replayed'],'input_rows':len(body.rows),
        'progress_url':f'/leads?csv_import={reference}' if options['score_on_import'] and options['engine']=='ai' else None,
        'scoring_eligible':result['scoring_eligible'],'consolidated_rows':len(rows),'imported':result['imported'],'updated':result['existing'],'skipped':skipped,
        'scored':counts['scored'] if counts else None,'scoring_state':state,
        'scoring_remaining':counts['remaining'] if counts else None,'scoring_held':counts['held'] if counts else None,
        'scoring_in_flight':counts['in_flight'] if counts else None,'list_id':result['list_id'],'owner_review':result['owner_review'],
        'warning':' '.join(warnings) or None}



def _progress_warning(state, counts):
    if state=='pending':
        return f"Leads saved. {counts['remaining']} AI scores remain; continue scoring to process the next batch. {counts['held']} held for review."
    if state in {'submitting','review','unconfirmed'}:
        return 'Leads saved. AI scoring is in progress or needs review. Submitted batches will not be dispatched again.'
    return None


def import_progress(reference, request, scorer=None):
    """Read-only GET or one explicit bounded continuation; no scheduler or polling."""
    operator=getattr(request.state,'user_id',None)
    if not operator: raise HTTPException(401,'Sign in to continue')
    db=get_supabase_client()
    if db is None: raise HTTPException(503,'Supabase service role is not configured')
    try:
        value=db.rpc('csv_import_scoring_status',{'p_id':str(reference),'p_operator':str(operator)}).execute().data
        eligible=value.get('eligible') if isinstance(value,dict) else None
        if type(eligible) is not int or eligible<0: raise ValueError('Unconfirmed scoring size')
        state,counts=_scoring_result(value,str(reference),str(operator),eligible)
    except Exception as exc:
        if (getattr(exc,'code',None) or getattr(exc,'pgcode',None))=='22023':
            raise HTTPException(404,'This AI import is unavailable for your account')
        raise HTTPException(503,'Scoring progress is unconfirmed. No new model request was started.')
    if scorer is not None and state=='pending':
        state,counts=_score_import(db,str(reference),str(operator),{'scoring_eligible':eligible},None,scorer)
    return {'status':'ok','request_id':str(reference),'scoring_eligible':eligible,'scoring_state':state,
        'scored':counts['scored'] if counts else None,'scoring_remaining':counts['remaining'] if counts else None,
        'scoring_held':counts['held'] if counts else None,'scoring_in_flight':counts['in_flight'] if counts else None,
        'warning':_progress_warning(state,counts)}
