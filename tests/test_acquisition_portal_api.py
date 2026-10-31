import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest

from web.api import acquisition_portal_api as api
from tools.acquisition_portal_runtime import PortalRuntime, PortalStore, configured_portal
from tools.acquisition_portal_submission import PortalReceipt
from tools.acquisition_portal_admission import portal_network_hash
from tests.test_acquisition_portal_submission import BODY, DEFINITION, CONFIG, ID, Store, success

RUNTIME=PortalRuntime(CONFIG,'public-test-key',b'x'*32,'https://fixture.supabase.co','synthetic-service-key')
PATH='/api/acquisition/portal/synthetic'
ENV={'ACQUISITION_ENABLED':'true','ACQUISITION_PORTAL_ENABLED':'true',
     'ACQUISITION_PORTAL_TRANSPORT_APPROVED':'true','ACQUISITION_PORTAL_BOT_ENABLED':'true',
     'ACQUISITION_PORTAL_TURNSTILE_SECRET':'synthetic-secret','ACQUISITION_PORTAL_HOSTNAME':'seller.example.test',
     'ACQUISITION_PORTAL_TURNSTILE_SITE_KEY':'public-test-key','ACQUISITION_PORTAL_NETWORK_KEY_HEX':'ab'*32,
     'SUPABASE_URL':'https://fixture.supabase.co','SUPABASE_SERVICE_ROLE_KEY':'synthetic-service-key'}


@pytest.mark.parametrize('missing',list(ENV))
def test_runtime_requires_every_explicit_configuration(missing):
    env=ENV.copy();env.pop(missing)
    with pytest.raises(HTTPException):configured_portal(env)


def test_valid_runtime_hides_secrets_and_rejects_other_database_hosts():
    value=configured_portal(ENV)
    assert 'synthetic-service-key' not in repr(value) and 'synthetic-secret' not in repr(value)
    with pytest.raises(HTTPException):configured_portal(ENV|{'SUPABASE_URL':'https://untrusted.example'})


@pytest.fixture
def endpoint(monkeypatch):
    app=FastAPI();app.include_router(api.router)
    monkeypatch.setattr(api,'configured_portal',lambda:RUNTIME)
    store=AsyncMock()
    @asynccontextmanager
    async def open_store(config):
        assert config is RUNTIME
        yield store
    monkeypatch.setattr(api,'open_portal_store',open_store)
    with TestClient(app,client=('192.0.2.10',12345)) as client:
        yield client,store


def test_disabled_receiver_never_opens_database_or_parses_body(endpoint,monkeypatch):
    client,store=endpoint
    def disabled():raise HTTPException(404,'Offer request form is unavailable')
    monkeypatch.setattr(api,'configured_portal',disabled)
    response=client.post(PATH,content=b'not json')
    assert response.status_code==404 and response.headers['cache-control']=='no-store'
    store.request.assert_not_awaited()


def test_display_admission_precedes_definition_and_ignores_forwarded_identity(endpoint,monkeypatch):
    client,store=endpoint;admit=AsyncMock();monkeypatch.setattr(api,'admit_portal_request',admit)
    async def read(*args,**kwargs):
        admit.assert_awaited_once()
        return DEFINITION
    store.request.side_effect=read
    response=client.get(PATH,headers={'x-forwarded-for':'203.0.113.99'})
    assert response.json()=={'definition':DEFINITION,'bot_site_key':'public-test-key'}
    assert response.headers['cache-control']=='no-store'
    assert admit.await_args.kwargs['network_hash']==portal_network_hash('192.0.2.10',RUNTIME.network_key)


@pytest.mark.parametrize('change',[{'form_key':'other'},{'internal_owner':'secret'}])
def test_display_invalid_projection_does_not_leak(endpoint,monkeypatch,change):
    client,store=endpoint;monkeypatch.setattr(api,'admit_portal_request',AsyncMock())
    store.request.return_value=DEFINITION|change
    response=client.get(PATH)
    assert response.status_code==503 and 'secret' not in response.text


def test_capacity_denial_stops_display(endpoint,monkeypatch):
    client,store=endpoint
    monkeypatch.setattr(api,'admit_portal_request',AsyncMock(side_effect=HTTPException(429,'Please wait',headers={'Retry-After':'5'})))
    response=client.get(PATH)
    assert response.status_code==429 and response.headers['retry-after']=='5'
    assert response.headers['cache-control']=='no-store'
    store.request.assert_not_awaited()


@pytest.mark.parametrize('suffix,headers',[('?workspace_id=other',{}),('',{'Origin':'https://other.example'})])
def test_injected_routing_and_wrong_origin_denied_before_storage(endpoint,suffix,headers):
    client,store=endpoint
    response=client.post(PATH+suffix,json={'inquiry':BODY,'bot_token':'synthetic-token'},headers=headers)
    assert response.status_code in (403,404)
    store.request.assert_not_awaited()


def test_http_request_uses_real_submission_preparation_and_minimal_receipt(endpoint,monkeypatch):
    client,mock_store=endpoint;store=Store()
    mock_store.request.side_effect=store.request
    from tools import acquisition_portal_submission as submission
    original=submission.verify_portal_bot
    async def verify(config,**kwargs):
        kwargs['transport']=httpx.MockTransport(success)
        return await original(config,**kwargs)
    monkeypatch.setattr(submission,'verify_portal_bot',verify)
    response=client.post(PATH,json={'inquiry':BODY,'bot_token':'synthetic-token'},
                         headers={'Origin':'https://seller.example.test','Authorization':'Bearer attacker'})
    assert response.status_code==200
    assert response.json()=={'submission_id':str(ID),'status':'received','duplicate':False}
    assert response.headers['cache-control']=='no-store'
    assert [p for p,_ in store.calls]==['rpc/read_acquisition_public_form','rpc/admit_acquisition_portal_request','rpc/complete_acquisition_portal_request']
    assert 'attacker' not in str(store.calls) and 'synthetic-token' not in str(store.calls)


def test_unknown_fields_rejected_before_database(endpoint):
    client,store=endpoint
    response=client.post(PATH,json={'inquiry':BODY,'bot_token':'synthetic-token','workspace_id':'private'})
    assert response.status_code==422 and 'private' not in response.text
    store.request.assert_not_awaited()


@pytest.mark.parametrize('response,status',[(httpx.Response(302,headers={'location':'https://elsewhere'}),503),
    (httpx.Response(403,json={'message':'secret SQL'}),404),
    (httpx.Response(200,content=b'x'*65537),503),
    (httpx.Response(200,content=b'not JSON'),503)])
def test_bounded_store_rejects_errors_without_response_leak(response,status):
    async def run():
        async with httpx.AsyncClient(base_url='https://fixture.supabase.co/rest/v1/',transport=httpx.MockTransport(lambda _:response)) as client:
            await PortalStore(client).request('POST','rpc/read_acquisition_public_form',body={'p_form_key':'synthetic'})
    with pytest.raises(HTTPException) as error:asyncio.run(run())
    assert error.value.status_code==status and 'SQL' not in str(error.value.detail)


def test_store_cannot_call_arbitrary_table():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:pytest.fail('unexpected request'))) as client:
            await PortalStore(client).request('POST','leads',body={})
    with pytest.raises(HTTPException):asyncio.run(run())


def test_actual_app_mount_is_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv('ACQUISITION_PORTAL_ENABLED',raising=False)
    from web.app import app
    with TestClient(app,client=('192.0.2.10',12345)) as client:
        for method in ('get','post'):
            response=getattr(client,method)(PATH)
            assert response.status_code==404
            assert response.headers['cache-control']=='no-store'


def test_portal_auth_exception_does_not_open_neighboring_acquisition_routes(monkeypatch):
    from web.app import app
    with TestClient(app,client=('192.0.2.10',12345)) as client:
        for path in ('/api/acquisition/workspaces','/api/acquisition/workspaces/00000000-0000-0000-0000-000000000001/memberships'):
            assert client.get(path).status_code==401
