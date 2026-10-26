"""Credential boundary and async/threadpool isolation; database RLS tested separately."""
import asyncio
from unittest.mock import MagicMock
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool

from tools.database_identity import DatabaseIdentity, DatabaseIdentityMiddleware, database_credentials, identity
from tools.crm import CRMStore, get_supabase_client


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED', 'true')
    monkeypatch.setenv('SUPABASE_URL', 'https://database.example.test')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'public-fixture')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-fixture')
    for name in ('VITE_SUPABASE_URL','VITE_SUPABASE_ANON_KEY','SUPABASE_ANON_KEY'):
        monkeypatch.delenv(name, raising=False)


def scope(path='/api/leads', method='GET', token='user-fixture'):
    return {'type':'http','path':path,'method':method,
            'headers':[(b'authorization',('Bearer '+token).encode())]}


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/api/leads','/api/buyers/import','/internal/outreach/eligibility/evaluate',
                                 '/v1/leads','/webhooks/launch_control/csv-queue'])
async def test_protected_paths_use_user_identity_and_reset_afterward(path):
    seen = []
    async def handler(*_):
        seen.append(database_credentials())
        seen.append(await run_in_threadpool(database_credentials))
    await DatabaseIdentityMiddleware(handler)(scope(path), None, None)
    assert seen == [('public-fixture','user-fixture')]*2
    assert identity.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize('path,method', [('/api/health','GET'),('/api/readiness','GET'),('/api/config','GET'),
                                       ('/api/forms/hilltop','GET'),('/api/forms/hilltop/submit','POST'),
                                       ('/webhooks/retell','POST'),('/webhooks/_worker/drain','POST')])
async def test_explicit_server_paths_preserve_existing_provider_boundary(path, method):
    async def handler(*_):
        assert identity.get() is None
        assert database_credentials() == ('service-fixture','service-fixture')
    await DatabaseIdentityMiddleware(handler)(scope(path,method), None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('headers', [[], [(b'authorization',b'Basic x')],
                                    [(b'authorization',b'Bearer one two')],
                                    [(b'authorization',b'Bearer one'),(b'authorization',b'Bearer two')]])
async def test_invalid_or_duplicate_auth_never_falls_back_to_service(headers):
    request = scope()
    request['headers'] = headers
    async def handler(*_):
        assert identity.get() is not None
        assert database_credentials() == ('public-fixture','')
        assert get_supabase_client() is None
    await DatabaseIdentityMiddleware(handler)(request,None,None)


@pytest.mark.asyncio
async def test_parallel_requests_cannot_borrow_tokens():
    app = FastAPI()
    app.add_middleware(DatabaseIdentityMiddleware)
    @app.get('/api/probe')
    async def probe():
        before = database_credentials()
        await asyncio.sleep(0.01)
        after = await run_in_threadpool(database_credentials)
        return {'before':before,'after':after}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
        one,two = await asyncio.gather(
            client.get('/api/probe',headers={'Authorization':'Bearer one'}),
            client.get('/api/probe',headers={'Authorization':'Bearer two'}))
    assert one.json() == {'before':['public-fixture','one'],'after':['public-fixture','one']}
    assert two.json() == {'before':['public-fixture','two'],'after':['public-fixture','two']}
    assert identity.get() is None


@pytest.mark.asyncio
async def test_exception_restores_context():
    async def fail(*_):
        assert identity.get().bearer == 'user-fixture'
        raise ValueError('fixture')
    with pytest.raises(ValueError):
        await DatabaseIdentityMiddleware(fail)(scope(),None,None)
    assert identity.get() is None


@pytest.mark.asyncio
async def test_flag_off_preserves_existing_client_selection(monkeypatch):
    monkeypatch.delenv('ACQUISITION_ENABLED')
    async def handler(*_):
        assert database_credentials() == ('service-fixture','service-fixture')
    await DatabaseIdentityMiddleware(handler)(scope(),None,None)


def test_sdk_has_public_apikey_and_user_authorization_without_refresh(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr('supabase.create_client',factory)
    marker = identity.set(DatabaseIdentity('user-fixture'))
    try:
        assert get_supabase_client() is factory.return_value
    finally:
        identity.reset(marker)
    args,kw = factory.call_args
    assert args == ('https://database.example.test','public-fixture')
    options = kw['options']
    assert options.headers['Authorization'] == 'Bearer user-fixture'
    assert not options.auto_refresh_token and not options.persist_session
    assert options.postgrest_client_timeout == 15


def test_missing_public_key_does_not_use_available_service_key(monkeypatch):
    monkeypatch.delenv('SUPABASE_PUBLISHABLE_KEY')
    marker = identity.set(DatabaseIdentity('user-fixture'))
    try:
        assert get_supabase_client() is None
    finally:
        identity.reset(marker)


def test_cached_sqlite_store_cannot_bypass_request_scope():
    cached = CRMStore('sqlite:///:memory:')
    marker = identity.set(DatabaseIdentity('user-fixture'))
    try:
        with pytest.raises(PermissionError):
            CRMStore('sqlite:///:memory:')
        with pytest.raises(PermissionError):
            cached.get_all_leads()
    finally:
        identity.reset(marker)
        cached._engine.dispose()


def test_monitor_http_transport_uses_request_credentials(monkeypatch):
    from tools import launch_monitor
    client = MagicMock()
    client.return_value.__enter__.return_value.request.return_value.json.return_value = []
    monkeypatch.setattr(launch_monitor.httpx,'Client',client)
    marker = identity.set(DatabaseIdentity('user-fixture'))
    try:
        launch_monitor.incidents()
    finally:
        identity.reset(marker)
    assert client.return_value.__enter__.return_value.request.call_args.kwargs['headers'] == {
        'apikey':'public-fixture','Authorization':'Bearer user-fixture'}


def test_buyer_and_webhook_factories_delegate_to_scoped_client(monkeypatch):
    from web.api import buyers_api, webhooks
    sentinel = object()
    factory = MagicMock(return_value=sentinel)
    monkeypatch.setattr('tools.crm.get_supabase_client',factory)
    assert buyers_api._get_supabase() is sentinel
    assert webhooks._get_supabase() is sentinel
    assert factory.call_count == 2


def test_real_app_auth_and_legacy_reader_share_the_user_identity(monkeypatch):
    from web.app import app
    from web import api
    clients = []
    def factory(url, key, options=None):
        assert key == 'public-fixture'
        assert options.headers['Authorization'] == 'Bearer verified-fixture'
        client = MagicMock()
        client.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id='fixture-user'))
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {'role':'user','status':'approved','acquisition_only':False}]
        clients.append(client)
        return client
    monkeypatch.setattr('supabase.create_client',factory)
    def read(db):
        assert db in clients
        return {'total':0}
    monkeypatch.setattr(api,'_lead_scoring_status',read)
    response = TestClient(app).get('/api/ai/lead-scoring-status',headers={'Authorization':'Bearer verified-fixture'})
    assert response.status_code == 200 and response.json() == {'total':0}
    assert len(clients) == 2  # Auth/profile and handler each use request-scoped clients.
    assert identity.get() is None
