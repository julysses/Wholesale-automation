"""A provider timeout or malformed acceptance must never trigger a redial."""
from unittest.mock import MagicMock

import httpx
import pytest

from tools import retell_adapter as calls


@pytest.fixture
def creation(monkeypatch):
    for key,value in {'retell_api_key':'fixture-key','retell_agent_id':'agent_fixture',
                      'retell_from_number':'+14698049920'}.items():
        monkeypatch.setattr(calls.settings,key,value)
    sdk=MagicMock()
    response=sdk.__enter__.return_value.post.return_value
    response.json.return_value={'call_id':'call_fixture','call_status':'registered'}
    monkeypatch.setattr(calls.httpx,'Client',lambda **_:sdk)
    req=calls.CallRequest(lead_id='fixture-lead',phone_number='+12147010100',
                          property_address='TEST ONLY',owner_name='Launch Verification')
    return calls.RetellAdapter(),req,sdk.__enter__.return_value


def test_current_payload_and_stable_provider_reference(creation):
    adapter,req,sdk=creation
    record=adapter.create_call(req)
    payload=sdk.post.call_args.kwargs['json']
    assert record.call_id=='call_fixture'
    assert payload['override_agent_id']=='agent_fixture'
    assert payload['override_agent_version']=='latest_published'
    assert 'agent_id' not in payload
    assert payload['honor_internal_dnc'] is True
    assert payload['idempotency_key']==req.request_id
    assert payload['metadata']['request_id']==req.request_id
    assert calls.build_retell_call_payload(req,'agent_fixture','+14698049920')['idempotency_key']==req.request_id


@pytest.mark.parametrize('failure',[httpx.ReadTimeout('ambiguous'),httpx.ConnectError('offline')])
def test_provider_failure_submits_once(creation,failure):
    adapter,req,sdk=creation
    sdk.post.side_effect=failure
    with pytest.raises(type(failure)):
        adapter.create_call(req)
    assert sdk.post.call_count==1


@pytest.mark.parametrize('body',[{}, {'call_id':''}, {'call_id':None}, {'call_id':123}])
def test_no_false_acceptance_without_provider_id(creation,body):
    adapter,req,sdk=creation
    sdk.post.return_value.json.return_value=body
    with pytest.raises(RuntimeError,match='no call ID'):
        adapter.create_call(req)
    assert sdk.post.call_count==1


@pytest.mark.parametrize('key',['retell_api_key','retell_agent_id','retell_from_number'])
def test_missing_setup_never_reports_dry_run_as_a_call(creation,monkeypatch,key):
    _,req,sdk=creation
    monkeypatch.setattr(calls.settings,key,'')
    with pytest.raises(RuntimeError,match='required'):
        calls.RetellAdapter().create_call(req)
    sdk.post.assert_not_called()


@pytest.mark.parametrize('reference',['bad','contains spaces','a'*256])
def test_invalid_reference_rejected_before_provider(creation,reference):
    adapter,req,sdk=creation
    req.request_id=reference
    with pytest.raises(ValueError):
        adapter.create_call(req)
    sdk.post.assert_not_called()
