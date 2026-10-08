from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from web.app import app
from web import auth


@pytest.fixture
def identity(monkeypatch):
    client = MagicMock()
    client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id="operator-1"))
    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = SimpleNamespace(data=[{"status": "approved", "role": "user"}])
    monkeypatch.setattr(auth, "get_supabase_client", lambda: client)
    return client


@pytest.mark.parametrize("method,path", [
    ("get", "/api/ai/lead-scoring-status"), ("post", "/api/ai/import-master-list"),
    ("post", "/api/buyers/outreach/sms"), ("post", "/api/marketing/bulk-sms-warm"),
    ("get", "/api/lead-gen/forms"), ("post", "/api/appointments"),
    ("post", "/api/deals"), ("patch", "/api/deals/11234567-0000-4000-8000-000000000001"),
    ("get", "/v1/leads"), ("get", "/webhooks/launch_control/csv-queue"),
    ("post", "/api/calls/retell"), ("get", "/api/calls/retell/call_test"),
])
def test_operational_routes_reject_anonymous_requests(method, path):
    assert getattr(TestClient(app), method)(path).status_code == 401


@pytest.mark.parametrize("profile", [[], [{"status": "pending"}], [{"status": "suspended"}], [{"status": "denied"}]])
def test_unapproved_profiles_are_rejected(identity, profile):
    identity.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = profile
    response = TestClient(app).get("/api/ai/lead-scoring-status", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 403
    identity.auth.get_user.assert_called_once_with("test-token")

@pytest.mark.parametrize('method,path',[('post','/api/deals'),('patch','/api/deals/11234567-0000-4000-8000-000000000001')])
def test_deal_writes_reject_unapproved_operator(identity,method,path):
    identity.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data=[{'status':'pending'}]
    assert getattr(TestClient(app),method)(path,headers={'Authorization':'Bearer valid'}).status_code==403


def test_invalid_token_never_reaches_profile_lookup(identity):
    identity.auth.get_user.side_effect = ValueError("invalid token")
    response = TestClient(app).get("/api/ai/lead-scoring-status", headers={"Authorization": "Bearer fake"})
    assert response.status_code == 401
    identity.table.assert_not_called()


def test_approved_operator_can_access_api(identity, monkeypatch):
    from web import api
    monkeypatch.setattr(api, "_supabase_or_503", lambda: object())
    monkeypatch.setattr(api, "_lead_scoring_status", lambda _: {"total": 17})
    response = TestClient(app).get("/api/ai/lead-scoring-status", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert response.json()["total"] == 17


def test_non_admin_cannot_test_provider_keys(identity):
    response = TestClient(app).post("/api/ai/test-key", headers={"Authorization": "Bearer valid"}, json={"key": "dummy"})
    assert response.status_code == 403


def test_unconfigured_auth_fails_closed(monkeypatch):
    monkeypatch.setattr(auth, "get_supabase_client", lambda: None)
    response = TestClient(app).get("/api/ai/lead-scoring-status", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 503


def test_public_system_routes_remain_available():
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/config").status_code == 200

@pytest.mark.parametrize('method,path',[('get','/api/email/messages'),('post','/api/email/test')])
def test_email_controls_require_admin(identity,method,path):
    client=TestClient(app)
    assert getattr(client,method)(path).status_code==401
    assert getattr(client,method)(path,headers={'Authorization':'Bearer valid'}).status_code==403


@pytest.mark.parametrize('method,path',[('post','/api/calls/retell'),('get','/api/calls/retell/call_test')])
def test_call_controls_require_admin(identity,method,path):
    assert getattr(TestClient(app),method)(path,headers={'Authorization':'Bearer valid'}).status_code==403


@pytest.mark.parametrize('method,path',[('get','/api/operations/monitor'),('post','/api/operations/monitor/scan')])
def test_monitor_controls_require_admin(identity,method,path):
    assert getattr(TestClient(app),method)(path).status_code==401
    assert getattr(TestClient(app),method)(path,headers={'Authorization':'Bearer valid'}).status_code==403


def test_readiness_route_is_public_but_dependency_failure_is_not_healthy(monkeypatch):
    from tools import launch_monitor
    monkeypatch.setattr(launch_monitor,'snapshot',lambda: {'database':True,'intake':False,'owner':True,'aged':{}})
    response=TestClient(app).get('/api/readiness')
    assert response.status_code==503 and response.json()=={'status':'unavailable'}
