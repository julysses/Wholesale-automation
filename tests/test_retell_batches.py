"""Real call handlers with mocked provider and an isolated database boundary.

Atomic RPC behavior is additionally exercised on the isolated Supabase project.
"""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
from tests.test_backend_launch_contracts import Database, Table
from tools.facebook_consent import AI_DISCLOSURE, AI_CHECKBOX_KEY, HILLTOP_CONSENT_FORM_ID
from web.api import calls_api as calls

class Query(Table):
    def neq(self,key,value):
        self.filters.append(lambda row:row.get(key)!=value);return self
    def upsert(self,payload,**kwargs):
        self.action,self.payload='upsert',payload;return self
    def execute(self):
        if self.action=='upsert':
            rows=self.db.tables.setdefault(self.name,[])
            if any(row['id']==self.payload['id'] for row in rows):return SimpleNamespace(data=[])
            row={'created_at':datetime.now(timezone.utc).isoformat(),**deepcopy(self.payload)}
            rows.append(row);return SimpleNamespace(data=[deepcopy(row)])
        return super().execute()

class DB(Database):
    fail_finish=False
    def table(self,name):return Query(self,name)
    def rpc(self,name,args):
        def execute():
            if name=='intake_phone_status':return SimpleNamespace(data={'suppressed':False})
            if name=='outreach_recipient_limits':
                active=any(r['phone_number']==args['p_phone'] and r['status']!='completed' for r in self.tables.get('retell_call_requests',[]))
                return SimpleNamespace(data={'blocker':'unresolved_attempt' if active else None})
            if name=='claim_retell_call':
                active=any(r['phone_number']==args['p_phone'] and r['status']!='completed' for r in self.tables.get('retell_call_requests',[]))
                if active:return SimpleNamespace(data={'claimed':False,'reason':'unresolved_attempt'})
                self.table('retell_call_requests').upsert({'id':args['p_id'],'lead_id':args['p_lead'],
                    'phone_number':args['p_phone'],'requested_by':args['p_operator'],'status':'submitting'}).execute()
                return SimpleNamespace(data={'claimed':True})
            batch=next(r for r in self.tables['retell_call_batches'] if r['id']==args['p_batch'])
            if name=='claim_retell_batch_next':
                if batch['status']!='ready' or batch['requested_by']!=args['p_operator']:return SimpleNamespace(data={'claimed':False})
                item=next(r for r in batch['outcomes'] if r['status']=='pending')
                result=deepcopy(item);item['status']='submitting'
                batch.update(status='processing',claimed_at=datetime.now(timezone.utc).isoformat())
                return SimpleNamespace(data={'claimed':True,'item':result})
            if name=='finish_retell_batch_item':
                if self.fail_finish:self.fail_finish=False;raise RuntimeError('Receipt write interrupted')
                item=next(r for r in batch['outcomes'] if r['request_id']==args['p_reference'])
                item.update(status=args['p_status'],reason=args['p_reason'])
                batch['status']='review' if args['p_status']=='unknown' else 'ready' if any(r['status']=='pending' for r in batch['outcomes']) else 'completed'
                return SimpleNamespace(data={'saved':True})
            raise AssertionError(name)
        return SimpleNamespace(execute=execute)

@pytest.fixture
def fixture(monkeypatch):
    operator=str(uuid4());leads=[];notices=[]
    for phone in ('+12145559970','+12145559971'):
        lead_id=str(uuid4());leadgen=str(uuid4())
        leads.append({'id':lead_id,'source':'facebook_lead_ad','dnc':False,'ai_calling_paused':False,
                      'owner_phone_1':phone,'internal_notes':'FB leadgen_id='+leadgen,'property_address':'TEST ONLY','status':'new'})
        receipt={'source':'facebook_native_form','phone':phone,'leadgen_id':leadgen,'form_id':HILLTOP_CONSENT_FORM_ID,
                 'submitted_at':'2026-10-07T12:00:00+00:00','raw_responses':[{'checkbox_key':AI_CHECKBOX_KEY,'is_checked':'1'}],
                 'ai_calls':{'accepted':True,'disclosure':AI_DISCLOSURE}}
        notices.append({'id':str(uuid5(NAMESPACE_URL,'wholesaleos:intake-alert:'+lead_id)),'metadata':{'consent_receipt':receipt}})
    db=DB({'leads':leads,'app_notifications':notices})
    monkeypatch.setattr(calls,'get_supabase_client',lambda:db)
    for key,value in {'ai_calling_live_enabled':True,'ai_calling_allowed_recipients':','.join(r['owner_phone_1'] for r in leads),
        'retell_api_key':'test-only','retell_agent_id':'agent_test','retell_from_number':'+14698049920',
        'retell_webhook_secret':'test-only','tcpa_allowed_start_hour':9,'tcpa_allowed_end_hour':19}.items():
        monkeypatch.setattr(calls.settings,key,value)
    monkeypatch.setattr(calls,'_texas_now',lambda:datetime(2026,10,8,12,tzinfo=ZoneInfo('America/Chicago')))
    provider=MagicMock();provider.create_call.side_effect=lambda req:SimpleNamespace(call_id='call_'+req.request_id,status='registered')
    monkeypatch.setattr(calls,'RetellAdapter',lambda:provider)
    body=calls.StartBatch(request_id=uuid4(),lead_ids=[r['id'] for r in leads],acknowledged=True)
    return db,provider,body,operator

def test_creation_stores_selection_and_never_calls_provider(fixture):
    db,provider,body,operator=fixture
    batch=calls.create_batch(body,operator)
    assert batch['status']=='ready' and len(batch['outcomes'])==2
    assert batch['outcomes'][0]['request_id']==str(uuid5(body.request_id,'retell:'+str(body.lead_ids[0])))
    provider.create_call.assert_not_called()

def test_each_request_dispatches_one_and_repeated_completion_never_redials(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator)
    assert calls.batch_next(body.request_id,operator)['status']=='ready'
    assert provider.create_call.call_count==1
    result=calls.batch_next(body.request_id,operator)
    assert result['status']=='completed' and provider.create_call.call_count==2
    assert calls.batch_next(body.request_id,operator)['status']=='completed'
    assert calls.create_batch(body,operator)['status']=='completed'
    assert provider.create_call.call_count==2

def test_ambiguous_first_call_stops_remaining_and_never_redials(fixture):
    db,provider,body,operator=fixture
    provider.create_call.side_effect=httpx.ReadTimeout('unknown')
    calls.create_batch(body,operator)
    result=calls.batch_next(body.request_id,operator)
    assert result['status']=='review' and result['outcomes'][1]['status']=='pending'
    assert calls.batch_next(body.request_id,operator)['status']=='review'
    assert provider.create_call.call_count==1
    assert db.tables['retell_call_requests'][0]['status']=='unknown'

def test_lost_batch_receipt_recovers_from_known_call_without_resubmission(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator);db.fail_finish=True
    with pytest.raises(RuntimeError):calls.batch_next(body.request_id,operator)
    assert provider.create_call.call_count==1
    assert calls.batch_status(body.request_id,operator)['status']=='processing'
    assert calls.batch_next(body.request_id,operator)['status']=='processing'
    assert provider.create_call.call_count==1
    assert calls.reconcile_batch(body.request_id,operator)['status']=='ready'
    assert calls.batch_next(body.request_id,operator)['status']=='completed'
    assert provider.create_call.call_count==2

def test_revoked_consent_after_review_blocks_dispatch(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator)
    db.tables['app_notifications'][0]['metadata']['consent_receipt']['raw_responses'][0]['is_checked']='0'
    result=calls.batch_next(body.request_id,operator)
    assert result['outcomes'][0]['status']=='blocked'
    provider.create_call.assert_not_called()
    assert calls.batch_next(body.request_id,operator)['status']=='completed'
    assert provider.create_call.call_count==1

def test_same_reference_cannot_expand_or_replace_selection(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator)
    body.lead_ids.reverse()
    with pytest.raises(HTTPException) as error:calls.create_batch(body,operator)
    assert error.value.status_code==409
    provider.create_call.assert_not_called()

def test_other_operator_cannot_dispatch_batch(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator)
    with pytest.raises(HTTPException) as error:calls.batch_next(body.request_id,str(uuid4()))
    assert error.value.status_code==404
    provider.create_call.assert_not_called()

def test_duplicate_phone_selection_refused_before_enrollment(fixture):
    db,provider,body,operator=fixture
    db.tables['leads'][1]['owner_phone_1']=db.tables['leads'][0]['owner_phone_1']
    state=calls.preview_batch(body)
    assert not state['can_start'] and any('duplicate recipients' in blocker for blocker in state['leads'][0]['blockers'])
    with pytest.raises(HTTPException):calls.create_batch(body,operator)
    provider.create_call.assert_not_called()

def test_empty_or_oversized_batch_rejected():
    for selection in ([],[uuid4() for _ in range(6)]):
        with pytest.raises(ValueError):calls.BatchSelection(lead_ids=selection)

@pytest.mark.asyncio
async def test_cancellation_preserves_accepted_call_and_stops_remaining(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator)
    calls.batch_next(body.request_id,operator)
    request=SimpleNamespace(state=SimpleNamespace(user_id=operator))
    result=await calls.batch_cancel(body.request_id,request)
    assert result['status']=='canceled'
    assert calls.batch_next(body.request_id,operator)['status']=='canceled'
    assert provider.create_call.call_count==1

@pytest.mark.asyncio
async def test_processing_batch_cannot_be_falsely_canceled(fixture):
    db,provider,body,operator=fixture
    calls.create_batch(body,operator)
    db.tables['retell_call_batches'][0]['status']='processing'
    with pytest.raises(HTTPException) as error:
        await calls.batch_cancel(body.request_id,SimpleNamespace(state=SimpleNamespace(user_id=operator)))
    assert error.value.status_code==409
    provider.create_call.assert_not_called()
