"""Actual app boundary with simulated persistence; no provider/network I/O."""
import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from web.app import app

PATH = '/webhooks/retell/acquisition'
WORKSPACE = '10000000-0000-4000-8000-000000000001'
CONFIG = {'ACQUISITION_ENABLED':'true', 'ACQUISITION_INBOUND_WEBHOOK_ENABLED':'true',
    'ACQUISITION_INBOUND_SECRET':'fixture-secret', 'ACQUISITION_INBOUND_SERVICE_KEY':'dedicated-key',
    'ACQUISITION_INBOUND_WORKSPACE_ID':WORKSPACE,
    'ACQUISITION_INBOUND_INTEGRATION_ID':'96000000-0000-4000-8000-000000000001',
    'ACQUISITION_INBOUND_AGENT_ID':'agent_test', 'ACQUISITION_INBOUND_AGENT_VERSION':'3',
    'ACQUISITION_INBOUND_ACQUISITION_NUMBER':'+12145550100', 'SUPABASE_URL':'https://fixture.example.test'}


def envelope():
    return {'event':'call_started', 'call':{'call_id':'call_test', 'agent_id':'agent_test',
        'agent_version':3, 'call_type':'phone_call', 'direction':'inbound', 'to_number':'+12145550100',
        'from_number':'+12145550101', 'call_status':'ongoing', 'start_timestamp':1000,
        'transcript':'SENSITIVE CONTENT', 'recording_url':'https://private.example.test',
        'metadata':{'workspace_id':'attacker-scope'}}}


def deliver(payload=None, *, raw=None, offset=0, signature=None, tamper=False):
    raw = raw if raw is not None else json.dumps(payload if payload is not None else envelope()).encode()
    stamp = str(int(time.time()*1000) + offset)
    signed = 'v='+stamp+',d='+hmac.new(b'fixture-secret', raw+stamp.encode(), hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        return client.post(PATH, content=raw+(b' ' if tamper else b''),
            headers={'X-Retell-Signature': signed if signature is None else signature})


@pytest.fixture
def inbox(monkeypatch):
    for key,value in CONFIG.items():
        monkeypatch.setenv(key,value)
    state={'requests':[], 'saved':{}}
    def handler(request):
        state['requests'].append(request)
        assert request.url.path == '/rest/v1/rpc/accept_acquisition_inbound_event'
        assert request.headers['authorization'] == 'Bearer dedicated-key'
        assert request.headers['apikey'] == 'dedicated-key'
        if state.get('status'):
            return httpx.Response(state['status'], json={'error':'PRIVATE FAILURE'})
        data=json.loads(request.content)['p_data']
        duplicate=data['event_key'] in state['saved']
        state['saved'].setdefault(data['event_key'],data)
        if state.pop('lose_reply',False):
            raise httpx.ReadTimeout('PRIVATE FAILURE',request=request)
        result={'id':'30000000-0000-4000-8000-000000000001', 'workspace_id':WORKSPACE,
                'duplicate':duplicate, 'execution_authorized':False}
        return httpx.Response(200,json=state.get('result',result))
    original=httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    return state


def test_receipt_strips_private_content_and_ignores_untrusted_scope(inbox):
    response=deliver()
    assert response.status_code == 204 and response.content == b''
    data=json.loads(inbox['requests'][0].content)
    assert set(data)=={'p_integration','p_number','p_data'}
    assert data['p_data']['workspace_id']==WORKSPACE
    assert data['p_data']['sensitive_content_present'] is True
    assert b'SENSITIVE CONTENT' not in inbox['requests'][0].content
    assert b'private.example' not in inbox['requests'][0].content
    assert b'+12145550101' not in inbox['requests'][0].content
    assert deliver().status_code==204
    assert len(inbox['saved'])==1


def test_unknown_commit_is_not_acked_or_internally_retried(inbox):
    inbox['lose_reply']=True
    assert deliver().status_code==503
    assert len(inbox['requests'])==1 and len(inbox['saved'])==1
    assert deliver().status_code==204
    assert len(inbox['saved'])==1


@pytest.mark.parametrize('status',[301,400,401,403,409,429,500,503])
def test_no_ack_for_database_failures(inbox,status):
    inbox['status']=status
    response=deliver()
    assert response.status_code==503 and 'PRIVATE' not in response.text
    assert len(inbox['requests'])==1


@pytest.mark.parametrize('result',[{},[],None,{'id':'x'},
    {'id':'30000000-0000-4000-8000-000000000001','workspace_id':'wrong','duplicate':False,'execution_authorized':False},
    {'id':'30000000-0000-4000-8000-000000000001','workspace_id':WORKSPACE,'duplicate':0,'execution_authorized':False},
    {'id':'30000000-0000-4000-8000-000000000001','workspace_id':WORKSPACE,'duplicate':False,'execution_authorized':True}])
def test_malformed_receipt_is_unconfirmed(inbox,result):
    inbox['result']=result
    assert deliver().status_code==503


@pytest.mark.parametrize('kwargs',[{'offset':-301000},{'offset':301000},{'tamper':True},
    {'signature':''},{'signature':'sha256='+'0'*64},{'signature':'v=1,d='+'0'*64},
    {'signature':'v=123,d=x,v=123'},{'signature':'é'}])
def test_bad_signature_never_reaches_database(inbox,kwargs):
    if kwargs.get('signature')=='é':
        # ASGI can carry Latin-1 headers; httpx text headers are ASCII only.
        with TestClient(app) as client:
            response=client.post(PATH,content=b'{}',headers=[(b'x-retell-signature',b'\xe9')])
    else:
        response=deliver(**kwargs)
    assert response.status_code==403
    assert inbox['requests']==[]


@pytest.mark.parametrize('key,value',[('direction','outbound'),('agent_id','other'),('agent_version',True),
    ('agent_version',4),('to_number','+12145550199'),('call_type','web_call'),('call_status','ended')])
def test_route_and_lifecycle_mismatch(inbox,key,value):
    payload=envelope();payload['call'][key]=value
    assert deliver(payload).status_code==400
    assert inbox['requests']==[]


@pytest.mark.parametrize('raw',[b'{"event":1,"event":2}',b'{"call":{"x":1,"x":2}}',
    b'{"x":NaN}',b'{"x":Infinity}',b'\xff',b'[]',b'{}',b'[ '*1200+b']'*1200])
def test_strict_json_and_shape(inbox,raw):
    assert deliver(raw=raw).status_code==400
    assert inbox['requests']==[]


def test_body_bound_and_duplicate_signature_headers(inbox):
    assert deliver(raw=b'x'*1048577).status_code==413
    with TestClient(app) as client:
        response=client.post(PATH,content=b'{}',headers=[('x-retell-signature','one'),('x-retell-signature','two')])
    assert response.status_code==403 and inbox['requests']==[]


@pytest.mark.parametrize('key,value',[(key,'') for key in CONFIG]+[
    ('SUPABASE_URL','http://fixture.example.test'),('SUPABASE_URL','https://fixture.example.test/path'),
    ('SUPABASE_URL','https://user:pass@fixture.example.test'),('SUPABASE_URL','https://fixture.example.test:bad'),
    ('ACQUISITION_INBOUND_AGENT_VERSION','2147483648'),('ACQUISITION_INBOUND_WORKSPACE_ID','bad'),
    ('ACQUISITION_INBOUND_ACQUISITION_NUMBER','2145550100')])
def test_invalid_or_disabled_config_cannot_fall_back(inbox,monkeypatch,key,value):
    monkeypatch.setenv(key,value)
    monkeypatch.setenv('RETELL_API_KEY','legacy-secret')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','legacy-key')
    assert deliver().status_code==503
    assert inbox['requests']==[]
