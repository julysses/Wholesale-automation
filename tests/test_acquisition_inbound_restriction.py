import json
import httpx
import pytest
from tests.test_acquisition_inbound_tool_http import deliver
from tests.test_acquisition_inbound_tools import payload, ROUTE
from tests.test_acquisition_inbound_webhooks import CONFIG


def restriction(kind='do_not_contact'):
    data=payload();data.update(name='record_contact_restriction',args={
        'request_id':'50000000-0000-4000-8000-000000000001','kind':kind,'channels':['all'] if kind=='do_not_contact' else [],
        'requested_by_caller':True,'details':'Caller explicitly asks for no further contact.'})
    return data


@pytest.fixture
def transport(monkeypatch):
    for key,value in {**CONFIG,'ACQUISITION_INBOUND_TOOLS_ENABLED':'true','ACQUISITION_INBOUND_RESTRICTIONS_ENABLED':'true'}.items():monkeypatch.setenv(key,value)
    state={'requests':[],'saved':set()}
    def handler(request):
        state['requests'].append(request)
        assert request.url.path=='/rest/v1/rpc/record_acquisition_inbound_restriction'
        assert request.headers['authorization']=='Bearer dedicated-key'
        data=json.loads(request.content)
        assert set(data)=={'p_integration','p_number','p_agent','p_agent_version','p_call','p_request','p_kind','p_evidence'}
        if state.get('status'):return httpx.Response(state['status'],json={'error':'PRIVATE ERROR'})
        duplicate=data['p_request'] in state['saved'];state['saved'].add(data['p_request'])
        if state.pop('lose_reply',False):raise httpx.ReadTimeout('PRIVATE ERROR',request=request)
        result={'id':data['p_request'],'workspace_id':ROUTE['workspace_id'],'kind':data['p_kind'],'channels':data['p_evidence']['channels'],'duplicate':duplicate,'execution_authorized':False}
        result.update(state.get('patch',{}))
        return httpx.Response(200,json=result)
    original=httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    return state


@pytest.mark.parametrize('kind',['do_not_contact','cancel_callback'])
def test_exact_retry_minimal_receipt(transport,kind):
    transport['lose_reply']=True
    assert deliver(restriction(kind)).status_code==503
    assert len(transport['requests'])==1
    result=deliver(restriction(kind));assert result.status_code==200
    assert result.json()['status']=='restriction_recorded' and result.json()['duplicate'] is True
    assert len(transport['saved'])==1 and result.json()['execution_authorized'] is False
    for private in ['PRIVATE','workspace_id','214555','actor_id','evidence']:
        assert private not in result.text
    for private in ['PRIVATE TRANSCRIPT','from_number','metadata','answers']:
        assert private not in transport['requests'][0].content.decode()


@pytest.mark.parametrize('patch',[{'requested_by_caller':False},{'requested_by_caller':'true'},{'kind':'allow_contact'},
    {'channels':['sms','sms']},{'channels':['all','sms']},{'channels':[]},{'channels':[True]},
    {'request_id':'bad'},{'phone':'2145550199'},{'workspace_id':'other'},{'details':''},{'details':'x'*1001}])
def test_explicit_restrictions_only_without_arbitrary_contact_selectors(transport,patch):
    data=restriction();data['args'].update(patch)
    assert deliver(data).status_code==400 and not transport['requests']


@pytest.mark.parametrize('patch',[{'id':'other'},{'workspace_id':'other'},{'kind':'cancel_callback'},
    {'channels':['sms']},{'duplicate':1},{'execution_authorized':True},{'extra':'PRIVATE VALUE'}])
def test_unconfirmed_or_private_result_not_acknowledged(transport,patch):
    transport['patch']=patch
    response=deliver(restriction());assert response.status_code==503 and 'PRIVATE' not in response.text


@pytest.mark.parametrize('status',[301,403,409,429,500])
def test_database_failure_never_claims_optout_saved(transport,status):
    transport['status']=status
    response=deliver(restriction());assert response.status_code==503 and 'PRIVATE' not in response.text
    assert len(transport['requests'])==1


def test_signature_and_default_off_gate(transport,monkeypatch):
    assert deliver(restriction(),signature='invalid').status_code==403
    monkeypatch.delenv('ACQUISITION_INBOUND_RESTRICTIONS_ENABLED')
    assert deliver(restriction()).status_code==503 and not transport['requests']
