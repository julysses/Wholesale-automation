"""Signed lookup boundary: provider context cannot select private records."""
import json

import httpx
import pytest

from tests.test_acquisition_inbound_tool_http import deliver
from tests.test_acquisition_inbound_tools import payload, ROUTE
from tests.test_acquisition_inbound_webhooks import CONFIG


def lookup():
    data=payload();data['name']='lookup_property';data['args']={'intake_revision':1}
    return data


@pytest.fixture
def transport(monkeypatch):
    for key,value in {**CONFIG,'ACQUISITION_INBOUND_TOOLS_ENABLED':'true','ACQUISITION_INBOUND_LOOKUP_ENABLED':'true'}.items():
        monkeypatch.setenv(key,value)
    state={'requests':[]}
    def handler(request):
        state['requests'].append(request)
        assert request.url.path=='/rest/v1/rpc/acquisition_inbound_property_lookup'
        assert request.headers['authorization']=='Bearer dedicated-key'
        data=json.loads(request.content)
        assert set(data)=={'p_integration','p_number','p_agent','p_agent_version','p_call','p_intake_revision'}
        assert data['p_intake_revision']==1
        if state.get('error'): return httpx.Response(state['error'],json={'error':'PRIVATE ERROR'})
        result={key:ROUTE[key] for key in ('workspace_id','integration_id')}
        result.update(call_id='call_test',intake_revision=1,status='address_candidate',
                      policy_version='inbound-property-lookup-v1',review_required=True,
                      property_verified=False,ownership_verified=False,execution_authorized=False)
        result.update(state.get('patch',{}))
        return httpx.Response(200,json=result)
    original=httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    return state


@pytest.mark.parametrize('status',['incomplete_address','no_address_candidate','address_candidate','multiple_address_candidates'])
def test_minimal_unverified_status(transport,status):
    transport['patch']={'status':status}
    response=deliver(lookup());assert response.status_code==200
    assert response.json()['status']==status
    assert not response.json()['property_verified'] and not response.json()['ownership_verified']
    for private in ['workspace_id','integration_id','call_id','PRIVATE','123 Main','214555','parcel_id']:
        assert private not in response.text
    for private in ['PRIVATE TRANSCRIPT','from_number','metadata','answers']:
        assert private not in transport['requests'][0].content.decode()


@pytest.mark.parametrize('args',[{}, {'intake_revision':True},{'intake_revision':0},{'intake_revision':1.0},
    {'intake_revision':1000000001},{'intake_revision':'1'}, {'intake_revision':1,'workspace_id':'other'},
    {'intake_revision':1,'property_address':'1 Main'}, {'intake_revision':1,'property_id':'other'}])
def test_untrusted_selectors_rejected(transport,args):
    data=lookup();data['args']=args
    assert deliver(data).status_code==400 and not transport['requests']


@pytest.mark.parametrize('patch',[{'workspace_id':'other'},{'integration_id':'other'},{'call_id':'other'},
    {'intake_revision':2},{'intake_revision':True},{'review_required':1},{'property_verified':True},
    {'ownership_verified':True},{'execution_authorized':True},{'status':'verified'},
    {'policy_version':'unknown'},{'owner_name':'PRIVATE NAME'}])
def test_malformed_or_private_receipt_never_exposed(transport,patch):
    transport['patch']=patch
    response=deliver(lookup());assert response.status_code==503 and 'PRIVATE' not in response.text


@pytest.mark.parametrize('status',[301,403,409,429,500])
def test_database_errors_never_mean_no_match(transport,status):
    transport['error']=status
    response=deliver(lookup());assert response.status_code==503
    assert 'PRIVATE' not in response.text and len(transport['requests'])==1


def test_lookup_disabled_and_signature_required(transport,monkeypatch):
    assert deliver(lookup(),signature='invalid').status_code==403
    monkeypatch.delenv('ACQUISITION_INBOUND_LOOKUP_ENABLED')
    assert deliver(lookup()).status_code==503 and not transport['requests']
