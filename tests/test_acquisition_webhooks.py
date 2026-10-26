"""Signed HTTP boundary + real inbox client over fake PostgREST; no live I/O."""
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from web.app import app

PATH = '/webhooks/facebook/acquisition'


def envelope(ids=('1',)):
    return {'object':'page','entry':[{'id':'100','changes':[
        {'field':'leadgen','value':{'leadgen_id':identity,'form_id':'200','created_time':1800000000}}
        for identity in ids]}]}


def deliver(payload, *, tamper=False, signature=None):
    body=json.dumps(payload).encode()
    signed='sha256='+hmac.new(b'fixture-secret',body,hashlib.sha256).hexdigest()
    return TestClient(app).post(PATH,content=body+(b' ' if tamper else b''),
        headers={'X-Hub-Signature-256':signed if signature is None else signature})


@pytest.fixture
def inbox(monkeypatch):
    for key,value in {'ACQUISITION_ENABLED':'true','FACEBOOK_ACQUISITION_INGESTION_ENABLED':'true',
        'ACQUISITION_INGESTION_SERVICE_KEY':'dedicated-fixture', 'SUPABASE_URL':'https://fixture.example.test',
        'ACQUISITION_FACEBOOK_APP_SECRET':'fixture-secret','ACQUISITION_FACEBOOK_VERIFY_TOKEN':'fixture-verify'}.items():
        monkeypatch.setenv(key,value)
    state={'requests':[],'saved':{}}
    def handler(request):
        state['requests'].append(request)
        if state.get('status'):
            return httpx.Response(state['status'],json={'secret':'must not leak'})
        payload=json.loads(request.content)
        result=[]
        for event in payload['p_events']:
            identity=(event['page_id'],event['leadgen_id'])
            duplicate=identity in state['saved']
            state['saved'].setdefault(identity,'30000000-0000-4000-8000-'+str(len(state['saved'])+1).zfill(12))
            result.append({'receipt_id':state['saved'][identity],'workspace_id':'10000000-0000-4000-8000-000000000001',
                           'duplicate':duplicate,'status':'acquisition_received'})
        if state.pop('lose_reply',False):
            raise httpx.ReadTimeout('secret error details',request=request)
        return httpx.Response(200,json=state.get('result',result))
    original=httpx.AsyncClient
    monkeypatch.setattr('tools.acquisition_inbox.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    return state


def test_signed_delivery_persists_batch_once_and_replay_reuses_receipts(inbox):
    assert deliver(envelope(('1','2'))).json()=={'received':True,'events':2}
    assert len(inbox['requests'])==1
    request=inbox['requests'][0]
    assert request.url.path=='/rest/v1/rpc/accept_facebook_acquisition_batch'
    assert request.headers['Authorization']=='Bearer dedicated-fixture'
    sent=json.loads(request.content)
    assert sent['p_raw_body']=='\\x'+json.dumps(envelope(('1','2'))).encode().hex()
    assert 'workspace_id' not in sent
    assert deliver(envelope(('1','2'))).status_code==200
    assert len(inbox['saved'])==2


def test_unknown_commit_returns_retryable_error_then_reconciles(inbox):
    inbox['lose_reply']=True
    first=deliver(envelope())
    assert first.status_code==503
    assert 'secret' not in first.text
    assert len(inbox['saved'])==1
    assert deliver(envelope()).status_code==200
    assert len(inbox['saved'])==1


@pytest.mark.parametrize('status',[400,401,403,409,500,503])
def test_any_unconfirmed_database_result_is_not_acknowledged(inbox,status):
    inbox['status']=status
    response=deliver(envelope())
    assert response.status_code==503
    assert 'secret' not in response.text


@pytest.mark.parametrize('result',[{},[],[{'status':'acquisition_received'}]])
def test_malformed_database_success_not_acknowledged(inbox,result):
    inbox['result']=result
    assert deliver(envelope()).status_code==503


def test_bad_signatures_and_oversize_never_persist(inbox):
    assert deliver(envelope(),tamper=True).status_code==403
    assert deliver(envelope(),signature='').status_code==403
    assert TestClient(app).post(PATH,content=b'a'*1048577).status_code==413
    assert inbox['requests']==[]


@pytest.mark.parametrize('payload',[[],{'object':'user','entry':[]},envelope(('bad-id',)),envelope(tuple(str(i) for i in range(101)))])
def test_malformed_batches_do_not_partially_persist(inbox,payload):
    assert deliver(payload).status_code==400
    assert inbox['requests']==[]


@pytest.mark.parametrize('key',['ACQUISITION_ENABLED','FACEBOOK_ACQUISITION_INGESTION_ENABLED',
    'ACQUISITION_INGESTION_SERVICE_KEY','ACQUISITION_FACEBOOK_APP_SECRET','ACQUISITION_FACEBOOK_VERIFY_TOKEN'])
def test_default_off_or_missing_dedicated_config_never_falls_back(inbox,monkeypatch,key):
    monkeypatch.delenv(key)
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','must-not-use-generic-key')
    assert deliver(envelope()).status_code==503
    assert inbox['requests']==[]


def test_challenge_and_nonlead_changes_do_not_access_database(inbox):
    response=TestClient(app).get(PATH,params={'hub.mode':'subscribe','hub.verify_token':'fixture-verify','hub.challenge':'123'})
    assert response.status_code==200 and response.text=='123'
    assert TestClient(app).get(PATH,params={'hub.mode':'subscribe','hub.verify_token':'wrong','hub.challenge':'123'}).status_code==403
    assert deliver({'object':'page','entry':[{'id':'100','changes':[{'field':'feed'}]}]}).json()=={'received':True,'events':0}
    assert inbox['requests']==[]
