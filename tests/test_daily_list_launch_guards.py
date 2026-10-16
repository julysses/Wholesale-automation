"""Route-level launch guards; no live providers or database are contacted."""
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock
import pytest
from fastapi.testclient import TestClient
from web.app import app
from web import auth, api
from web.api import list_pipeline_api as lists

@pytest.fixture
def client(monkeypatch):
    db = MagicMock()
    db.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='00000000-0000-4000-8000-000000000001'))
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{'status':'approved','role':'user'}])
    monkeypatch.setattr(auth,'get_supabase_client',lambda: db)
    return TestClient(app)

@pytest.mark.parametrize('method,path',[
    ('get','/api/operations/lists'),('post','/api/operations/lists/scan'),
    ('post','/api/operations/lists/resolve'),('patch','/api/operations/lists/sources/tx-dallas-probate'),
])
def test_list_routes_require_admin(client,monkeypatch,method,path):
    rpc=AsyncMock(); monkeypatch.setattr(lists,'rpc',rpc)
    assert getattr(client,method)(path).status_code==401
    assert getattr(client,method)(path,headers={'Authorization':'Bearer test'}).status_code==403
    rpc.assert_not_called()

def test_worker_secret_fails_closed_then_runs_once(client,monkeypatch):
    rpc=AsyncMock(return_value={'missing_sources':0});monkeypatch.setattr(lists,'rpc',rpc)
    path='/webhooks/_worker/daily-lists'
    monkeypatch.delenv('CRON_SECRET',raising=False)
    assert client.get(path).status_code==503
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret-for-tests-only')
    assert client.get(path).status_code==401
    assert client.get(path,headers={'Authorization':'Bearer wrong'}).status_code==401
    rpc.assert_not_called()
    assert client.get(path,headers={'Authorization':'Bearer synthetic-worker-secret-for-tests-only'}).status_code==200
    rpc.assert_awaited_once_with('scan_list_pipeline',{})

def test_digest_worker_propagates_unconfirmed_delivery(client,monkeypatch):
    from tools import list_digest
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret-for-tests-only')
    monkeypatch.setattr(lists,'rpc',AsyncMock(return_value={'day':'2026-10-12'}))
    delivery=MagicMock(side_effect=RuntimeError('lost delivery acknowledgement'))
    monkeypatch.setattr(list_digest,'deliver_digest',delivery)
    response=client.get('/webhooks/_worker/daily-lists',headers={'Authorization':'Bearer synthetic-worker-secret-for-tests-only'})
    assert response.status_code==503
    assert 'saved receipt' in response.json()['detail']
    delivery.assert_called_once_with({'day':'2026-10-12'})


def test_busy_list_scan_never_attempts_digest(client,monkeypatch):
    from tools import list_digest
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret-for-tests-only')
    monkeypatch.setattr(lists,'rpc',AsyncMock(return_value={'busy':True}))
    delivery=MagicMock();monkeypatch.setattr(list_digest,'deliver_digest',delivery)
    response=client.get('/webhooks/_worker/daily-lists',headers={'Authorization':'Bearer synthetic-worker-secret-for-tests-only'})
    assert response.status_code==200 and response.json()=={'busy':True}
    delivery.assert_not_called()
