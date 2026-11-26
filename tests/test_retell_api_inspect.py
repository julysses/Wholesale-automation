from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tools import retell_api_inspect as subject
from web.api import nurture_api

OP = '00000000-0000-4000-8000-000000000001'
LEAD = '00000000-0000-4000-8000-000000000002'
PATH = f'/webhooks/_worker/retell-app/inspect/{OP}/chat_test'

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('RETELL_SMS_API_KEY', 'private-key')
    monkeypatch.setenv('CRON_SECRET', 'worker')
    row = {'id': OP, 'lead_id': LEAD, 'agent_id': 'agent_test', 'agent_version': 2, 'chat_id': None}
    read = Mock(return_value=row); monkeypatch.setattr(subject, '_row', read)
    data = {'chat_id': 'chat_test', 'chat_type': 'api_chat', 'agent_id': 'agent_test',
            'agent_version': 2, 'chat_status': 'ongoing', 'transcript': 'private-text',
            'metadata': {'operation_id': OP, 'lead_id': LEAD, 'transport': 'wholesaleos_twilio'}}
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: data))
    post = Mock(side_effect=AssertionError('No provider write permitted'))
    monkeypatch.setattr(subject.requests, 'get', get); monkeypatch.setattr(subject.requests, 'post', post)
    monkeypatch.setattr(nurture_api, '_db', lambda: None)
    app = FastAPI(); app.include_router(nurture_api.router)
    return TestClient(app), get, post, row, data, read

def test_paused_diagnostic_reads_only_and_redacts(setup):
    client, get, post, row, data, read = setup
    result = client.get(PATH, headers={'Authorization': 'Bearer worker'})
    assert result.status_code == 200
    body = result.json()
    assert body['dispatch_authorized'] is False
    assert body['checks']['agent_version_matches'] is True
    assert body['checks']['version_present'] is False
    assert 'private' not in result.text
    get.assert_called_once_with('https://api.retellai.com/get-chat/chat_test',
        headers={'Authorization': 'Bearer private-key'}, timeout=(5,20), allow_redirects=False)
    post.assert_not_called()

@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer wrong'}])
def test_diagnostic_requires_worker_auth_before_database_or_provider(setup, headers):
    client, get, post, row, data, read = setup
    assert client.get(PATH, headers=headers).status_code == 401
    read.assert_not_called(); get.assert_not_called(); post.assert_not_called()

def test_saved_chat_mismatch_never_reads_other_chat(setup):
    client, get, post, row, data, read = setup
    row['chat_id'] = 'chat_other'
    assert subject.inspect_session(None, OP, 'chat_test')['status'] == 'saved_chat_mismatch'
    get.assert_not_called(); post.assert_not_called()

@pytest.mark.parametrize('field', ['metadata', 'agent_id', 'chat_id', 'chat_type'])
def test_mismatched_identity_reported_not_bound(setup, field):
    client, get, post, row, data, read = setup
    data[field] = 'unexpected-private-value'
    result = subject.inspect_session(None, OP, 'chat_test')
    assert result['checks'][field] is False
    assert result['dispatch_authorized'] is False
    assert 'unexpected-private-value' not in str(result)
    post.assert_not_called()

@pytest.mark.parametrize('failure', [requests.Timeout('private-key'), ValueError('private-text')])
def test_provider_failure_is_redacted_without_retry(setup, failure):
    client, get, post, row, data, read = setup
    get.side_effect = failure
    assert subject.inspect_session(None, OP, 'chat_test')['status'] == 'provider_lookup_unconfirmed'
    assert get.call_count == 1; post.assert_not_called()

def test_invalid_chat_does_not_reach_provider(setup):
    client, get, post, row, data, read = setup
    with pytest.raises(ValueError): subject.inspect_session(None, OP, '../unsafe')
    get.assert_not_called(); post.assert_not_called(); read.assert_not_called()


def test_exact_first_turn_proof_has_only_fingerprints(setup):
    import hashlib
    _, get, post, row, data, _ = setup
    data['message_with_tool_calls'] = [
        {'role':'user','message_id':'u1','content':'Please call'},
        {'role':'agent','message_id':'a1','content':'What time works?'}]
    result = subject.inspect_session(None, OP, 'chat_test')
    assert result['first_turn_proof']['content_sha256'] == hashlib.sha256(b'What time works?').hexdigest()
    assert 'What time' not in str(result)
    assert 'Please call' not in str(result)
    post.assert_not_called()

@pytest.mark.parametrize('change', ['extra_user','tool','long','wrong_chat','duplicate_id','media'])
def test_ambiguous_history_never_gets_recovery_proof(setup, change):
    _, get, post, row, data, _ = setup
    messages = [{'role':'user','message_id':'u1','content':'Please call'},
                {'role':'agent','message_id':'a1','content':'What time works?'}]
    if change == 'extra_user': messages.append({'role':'user','message_id':'u2','content':'Again'})
    if change == 'tool': messages[1]['role'] = 'tool_call_invocation'
    if change == 'long': messages[1]['content'] = 'x'*199
    if change == 'wrong_chat': data['chat_id'] = 'chat_other'
    if change == 'duplicate_id': messages[1]['message_id'] = 'u1'
    if change == 'media': messages[0]['multimedia'] = [{}]
    data['message_with_tool_calls'] = messages
    assert 'first_turn_proof' not in subject.inspect_session(None, OP, 'chat_test')
    post.assert_not_called()
