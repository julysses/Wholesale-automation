import asyncio
import copy
import json

import httpx
import pytest
from tools.acquisition_facebook_worker import process_facebook_inquiry, WorkerUnavailable

I='10000000-0000-4000-8000-000000000001'
R='20000000-0000-4000-8000-000000000001'
T='30000000-0000-4000-8000-000000000001'


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED','true')
    for key,value in dict(WORKER_ENABLED='true',WORKER_SERVICE_KEY='database-fixture',PAGE_TOKEN='page-fixture',
        APP_SECRET='secret-fixture',PAGE_ID='100',INTEGRATION_ID=I,GRAPH_VERSION='v26.0').items():
        monkeypatch.setenv('ACQUISITION_FACEBOOK_'+key,value)
    monkeypatch.setenv('SUPABASE_URL','https://database.example.test')
    claim={'receipt_id':R,'lease_token':T,'workspace_id':I,'integration_id':I,'provider':'facebook',
           'account_id':'100','event_type':'leadgen','external_event_id':'1',
           'payload':{'page_id':'100','leadgen_id':'1','form_id':'200'}}
    state={'requests':[],'claims':[claim], 'provider':{'id':'1','form_id':'200','field_data':[],
           'custom_disclaimer_responses':[{'checkbox_key':'sms','is_checked':False}]},'complete_calls':0}
    def handle(request):
        state['requests'].append(request)
        if request.url.host=='graph.facebook.com':
            if state.get('timeout'): raise httpx.ReadTimeout('private provider secret',request=request)
            return httpx.Response(state.get('provider_status',200),json=state['provider'])
        name=request.url.path.split('/')[-1]
        if name=='claim_acquisition_events': return httpx.Response(200,json=state['claims'])
        body=json.loads(request.content)
        if name=='defer_acquisition_event':
            return httpx.Response(200,json={'receipt_id':R,'state':body['p_outcome'],'reason_code':body['p_reason']})
        assert name=='complete_facebook_acquisition_intake'
        state['complete_calls']+=1
        if state.get('lose_completion') and state['complete_calls']==1:
            raise httpx.ReadTimeout('private database secret',request=request)
        return httpx.Response(200,json={'intake_id':R,'lead_id':T,'workspace_id':I,'duplicate':state['complete_calls']>1,
            'classification':body['p_prepared']['classification']})
    original=httpx.AsyncClient
    monkeypatch.setattr('tools.acquisition_facebook_worker.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    return state


def test_worker_fetches_exact_claim_with_separate_credentials_and_preserves_consent(worker):
    result=asyncio.run(process_facebook_inquiry())
    assert result['status']=='completed'
    claim,provider,complete=worker['requests']
    assert provider.url.path=='/v26.0/1'
    assert provider.headers['Authorization']=='Bearer page-fixture'
    assert 'apikey' not in provider.headers
    assert provider.url.params.get('access_token') is None
    assert provider.url.params.get('appsecret_proof')
    assert complete.headers['Authorization']=='Bearer database-fixture'
    prepared=json.loads(complete.content)['p_prepared']
    assert prepared['provider_evidence']['custom_disclaimer_responses'][0]['is_checked'] is False
    assert not prepared['contact_permission_granted']


def test_completion_lost_reply_retries_identical_snapshot_without_refetch(worker):
    worker['lose_completion']=True
    assert asyncio.run(process_facebook_inquiry())['duplicate'] is True
    assert worker['requests'][-1].content==worker['requests'][-2].content
    assert sum(r.url.host=='graph.facebook.com' for r in worker['requests'])==1


@pytest.mark.parametrize('code,status,expected',[(190,400,'CREDENTIALS_INVALID'),(200,400,'PERMISSION_DENIED'),
    (4,400,'PROVIDER_RATE_LIMIT'),(None,429,'PROVIDER_RATE_LIMIT'),(None,503,'PROVIDER_UNAVAILABLE'),(100,400,'INVALID_PROVIDER_DATA')])
def test_provider_failures_park_or_retry_without_sensitive_errors(worker,code,status,expected):
    worker['provider']={'error':{'code':code,'message':'private token fixture'}}
    worker['provider_status']=status
    result=asyncio.run(process_facebook_inquiry())
    assert result['reason_code']==expected
    assert worker['complete_calls']==0
    assert 'private token' not in worker['requests'][-1].content.decode()


def test_provider_timeout_deferred(worker):
    worker['timeout']=True
    assert asyncio.run(process_facebook_inquiry())['reason_code']=='PROVIDER_TIMEOUT'


def test_form_mismatch_never_completes(worker):
    worker['provider']['form_id']='999'
    assert asyncio.run(process_facebook_inquiry())['reason_code']=='IDENTITY_CONFLICT'
    assert worker['complete_calls']==0


def test_wrong_account_claim_never_contacts_provider(worker):
    worker['claims'][0]['account_id']='999'
    with pytest.raises(WorkerUnavailable): asyncio.run(process_facebook_inquiry())
    assert len(worker['requests'])==1


def test_disabled_and_missing_credentials_never_claim(worker,monkeypatch):
    monkeypatch.delenv('ACQUISITION_FACEBOOK_WORKER_SERVICE_KEY')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','not-a-fallback')
    with pytest.raises(WorkerUnavailable): asyncio.run(process_facebook_inquiry())
    assert worker['requests']==[]


def test_idle_worker_does_not_fetch(worker):
    worker['claims']=[]
    assert asyncio.run(process_facebook_inquiry())=={'status':'idle'}
    assert len(worker['requests'])==1


def test_missing_empty_and_declined_disclaimers_remain_distinct():
    from tools.acquisition_intake import prepare_facebook_intake
    base={'id':'1','field_data':[]}
    missing=prepare_facebook_intake(leadgen_id='1',provider_data=base)
    empty=prepare_facebook_intake(leadgen_id='1',provider_data={**base,'custom_disclaimer_responses':[]})
    declined=prepare_facebook_intake(leadgen_id='1',provider_data={**base,'custom_disclaimer_responses':[{'is_checked':False}]})
    assert 'custom_disclaimer_responses' not in missing['provider_evidence']
    assert empty['provider_evidence']['custom_disclaimer_responses']==[]
    assert len({v['provider_evidence_hash'] for v in (missing,empty,declined)})==3


def test_worker_trigger_requires_own_secret_and_never_uses_public_webhook_secret(worker,monkeypatch):
    from fastapi.testclient import TestClient
    from web.app import app
    client=TestClient(app)
    path='/webhooks/facebook/acquisition/worker'
    monkeypatch.delenv('ACQUISITION_FACEBOOK_WORKER_TRIGGER_SECRET',raising=False)
    assert client.post(path).status_code==503
    monkeypatch.setenv('ACQUISITION_FACEBOOK_WORKER_TRIGGER_SECRET','trigger-fixture')
    assert client.post(path,headers={'Authorization':'Bearer secret-fixture'}).status_code==403
    assert worker['requests']==[]
    result=client.post(path,headers={'Authorization':'Bearer trigger-fixture'})
    assert result.status_code==200 and result.json()['status']=='completed'


def test_missing_form_claim_never_contacts_provider(worker):
    worker['claims'][0]['payload'].pop('form_id')
    with pytest.raises(WorkerUnavailable): asyncio.run(process_facebook_inquiry())
    assert len(worker['requests'])==1


@pytest.mark.parametrize('field', ['ad_id','adset_id','campaign_id'])
def test_conflicting_campaign_identifiers_hold_before_intake(worker,field):
    worker['claims'][0]['payload'][field]='101'
    worker['provider'][field]='102'
    assert asyncio.run(process_facebook_inquiry())['reason_code']=='IDENTITY_CONFLICT'
    assert worker['complete_calls']==0


@pytest.mark.parametrize('value', [True, 123, ['123'], 'not-an-id'])
def test_malformed_campaign_identifiers_are_not_coerced(worker,value):
    worker['provider']['campaign_id']=value
    assert asyncio.run(process_facebook_inquiry())['reason_code']=='INVALID_PROVIDER_DATA'
    assert worker['complete_calls']==0


def test_missing_provider_campaign_does_not_get_invented_from_receipt(worker):
    worker['claims'][0]['payload']['campaign_id']='101'
    assert asyncio.run(process_facebook_inquiry())['status']=='completed'
    evidence=json.loads(worker['requests'][-1].content)['p_prepared']['provider_evidence']
    assert 'campaign_id' not in evidence


def test_supervised_runner_executes_existing_worker_once(worker, monkeypatch):
    from tools.acquisition_facebook_runner import run
    monkeypatch.setenv('ACQUISITION_FACEBOOK_RUNNER_ENABLED', 'true')
    rows = []
    assert asyncio.run(run(report=rows.append)) == 0
    assert worker['complete_calls'] == 1
    assert sum(r.url.host == 'graph.facebook.com' for r in worker['requests']) == 1
    assert rows[1]['status'] == 'completed'
    assert 'page-fixture' not in json.dumps(rows)
    assert 'database-fixture' not in json.dumps(rows)


def test_supervised_runner_stops_after_real_worker_parks_credentials(worker, monkeypatch):
    from tools.acquisition_facebook_runner import run
    monkeypatch.setenv('ACQUISITION_FACEBOOK_RUNNER_ENABLED', 'true')
    worker['provider'] = {'error': {'code': 190, 'message': 'private provider token'}}
    worker['provider_status'] = 400
    rows = []
    assert asyncio.run(run(max_cycles=3, report=rows.append)) == 2
    assert worker['complete_calls'] == 0
    assert sum(r.url.host == 'graph.facebook.com' for r in worker['requests']) == 1
    assert rows[1]['reason_code'] == 'CREDENTIALS_INVALID'
    assert 'private provider token' not in json.dumps(rows)
