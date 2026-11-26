from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from web.api import nurture_api

IDENTITY = '00000000-0000-4000-8000-000000000001'


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.setenv('CRON_SECRET', 'recovery-test')
    monkeypatch.setattr(nurture_api.settings, 'sms_live_enabled', False)
    db = Mock()
    db.rpc.return_value.execute.return_value.data = {'recovered': True, 'status': 'review', 'dispatch_authorized': False}
    get_db = Mock(return_value=db)
    monkeypatch.setattr(nurture_api, '_db', get_db)
    app = FastAPI(); app.include_router(nurture_api.router)
    return TestClient(app), db, get_db


@pytest.mark.parametrize('kind,function,key', [('ack', 'recover_retell_app_ack', 'p_job'),
                                               ('turn', 'recover_retell_api_turn', 'p_turn')])
def test_recovery_is_authenticated_exact_post_and_available_while_sending_off(recovery, kind, function, key):
    client, db, get_db = recovery
    auth = {'Authorization': 'Bearer recovery-test'}
    path = f'/webhooks/_worker/retell-app/recover/{kind}/{IDENTITY}'
    assert client.get(path, headers=auth).status_code == 405
    assert client.post(path).status_code == 401
    assert client.post(path.replace(IDENTITY, 'invalid'), headers=auth).status_code == 422
    get_db.assert_not_called()
    response = client.post(path, headers=auth)
    assert response.status_code == 200
    assert response.json() == {'recovered': True, 'status': 'review', 'dispatch_authorized': False}
    db.rpc.assert_called_once_with(function, {key: IDENTITY})
    db.table.assert_not_called()


@pytest.mark.parametrize('response', [None, {}, {'recovered': True, 'dispatch_authorized': True}])
def test_recovery_refuses_unconfirmed_response(recovery, response):
    client, db, _ = recovery
    db.rpc.return_value.execute.return_value.data = response
    assert client.post('/webhooks/_worker/retell-app/recover/turn/'+IDENTITY,
        headers={'Authorization': 'Bearer recovery-test'}).status_code == 503
    assert db.rpc.call_count == 1


def test_recovery_timeout_does_not_repeat_rpc_or_expose_error(recovery):
    client, db, _ = recovery
    db.rpc.return_value.execute.side_effect = RuntimeError('private provider detail')
    response = client.post('/webhooks/_worker/retell-app/recover/turn/'+IDENTITY,
        headers={'Authorization': 'Bearer recovery-test'})
    assert response.status_code == 503 and 'private' not in response.text
    assert db.rpc.call_count == 1
