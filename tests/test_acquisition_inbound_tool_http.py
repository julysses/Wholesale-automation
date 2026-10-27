"""Signed tool boundary in actual app; database transport is simulated."""
import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from web.app import app
from tests.test_acquisition_inbound_webhooks import CONFIG, WORKSPACE
from tests.test_acquisition_inbound_tools import payload

PATH='/webhooks/retell/acquisition/tools'


def deliver(data=None, *, raw=None, signature=None, offset=0):
    raw=raw if raw is not None else json.dumps(data or payload('request_callback')).encode()
    stamp=str(int(time.time()*1000)+offset)
    signed='v='+stamp+',d='+hmac.new(b'fixture-secret',raw+stamp.encode(),hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        return client.post(PATH,content=raw,headers={'X-Retell-Signature':signed if signature is None else signature})


@pytest.fixture
def transport(monkeypatch):
    for key,value in {**CONFIG,'ACQUISITION_INBOUND_TOOLS_ENABLED':'true'}.items():monkeypatch.setenv(key,value)
    state={'requests':[],'saved':{}}
    def handler(request):
        state['requests'].append(request)
        assert request.url.path=='/rest/v1/rpc/record_acquisition_inbound_request'
        assert request.headers['authorization']=='Bearer dedicated-key'
        data=json.loads(request.content)
        assert set(data)=={'p_integration','p_number','p_agent','p_agent_version','p_call','p_request','p_expected_revision','p_kind','p_evidence'}
        if state.get('status'):return httpx.Response(state['status'],json={'error':'PRIVATE ERROR'})
        duplicate=data['p_request'] in state['saved']
        state['saved'].setdefault(data['p_request'],data)
        if state.pop('lose_reply',False):raise httpx.ReadTimeout('PRIVATE ERROR',request=request)
        result={'id':'30000000-0000-4000-8000-000000000001','workspace_id':WORKSPACE,
            'revision':data['p_expected_revision']+1,'duplicate':duplicate,'execution_authorized':False}
        result.update(state.get('patch',{}))
        return httpx.Response(200,json=result)
    original=httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    return state


@pytest.mark.parametrize('name',['request_callback','request_human'])
def test_review_only_minimal_success_and_private_context_exclusion(transport,name):
    result=deliver(payload(name));assert result.status_code==200
    data=result.json();assert data['status']=='recorded_for_review'
    assert data['execution_authorized'] is False and data['revision']==1
    assert 'workspace_id' not in data and 'id' not in data
    serialized=transport['requests'][0].content.decode()
    for private in ['PRIVATE TRANSCRIPT','+12145550999','untrusted','request_hash','prepared']:
        assert private not in serialized
    assert '2145550101' not in result.text
    assert deliver(payload(name)).json()['duplicate'] is True
    assert len(transport['saved'])==1


def test_commit_response_loss_is_not_acked_or_retried(transport):
    transport['lose_reply']=True
    response=deliver();assert response.status_code==503 and 'PRIVATE' not in response.text
    assert len(transport['requests'])==1 and len(transport['saved'])==1
    assert deliver().json()['duplicate'] is True
    assert len(transport['saved'])==1


@pytest.mark.parametrize('key',['ACQUISITION_ENABLED','ACQUISITION_INBOUND_WEBHOOK_ENABLED',
    'ACQUISITION_INBOUND_TOOLS_ENABLED','ACQUISITION_INBOUND_SECRET','ACQUISITION_INBOUND_SERVICE_KEY'])
def test_flags_and_dedicated_config_required(transport,monkeypatch,key):
    monkeypatch.delenv(key)
    assert deliver().status_code==503 and transport['requests']==[]


@pytest.mark.parametrize('status',[301,400,401,403,409,429,500,503])
def test_no_success_on_database_error(transport,status):
    transport['status']=status
    response=deliver();assert response.status_code==503 and 'PRIVATE' not in response.text
    assert len(transport['requests'])==1


@pytest.mark.parametrize('patch',[{'id':'bad'},{'workspace_id':'other'},{'revision':0},{'revision':2},
    {'revision':True},{'duplicate':0},{'execution_authorized':True},{'extra':'unexpected'}])
def test_unconfirmed_receipt_shape_or_scope(transport,patch):
    transport['patch']=patch
    assert deliver().status_code==503


@pytest.mark.parametrize('kwargs',[{'signature':''},{'signature':'sha256='+'0'*64},
    {'offset':-301000},{'offset':301000}])
def test_authentication_precedes_any_write(transport,kwargs):
    assert deliver(**kwargs).status_code==403
    assert transport['requests']==[]


@pytest.mark.parametrize('raw',[b'{"name":"request_callback","name":"request_human"}',
    b'{"x":NaN}',b'\xff',b'[]',b'{}'])
def test_strict_signed_json(transport,raw):
    assert deliver(raw=raw).status_code==400 and transport['requests']==[]


def test_oversize_body_and_wrong_call_scope(transport):
    assert deliver(raw=b'x'*1048577).status_code==413
    data=payload('request_callback');data['call']['agent_id']='wrong'
    assert deliver(data).status_code==400 and transport['requests']==[]


def test_unimplemented_intake_and_authority_overrides_rejected(transport):
    assert deliver(payload('submit_seller_intake')).status_code==400
    data=payload('request_callback');data['args']['workspace_id']=WORKSPACE
    assert deliver(data).status_code==400
    assert transport['requests']==[]
