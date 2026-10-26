"""HTTP contract/auth forwarding tests; SQL authorization uses real PostgreSQL QA."""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api.acquisition_api import router

W = '10000000-0000-4000-8000-000000000001'
U = '00000000-0000-4000-8000-000000000001'


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED', 'true')
    monkeypatch.setenv('SUPABASE_URL', 'https://database.example.test')
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', 'public-test-key')
    monkeypatch.delenv('VITE_SUPABASE_URL', raising=False)
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'must-never-be-used')
    state = {'requests': [], 'status': 200, 'body': []}
    def handle(request):
        state['requests'].append(request)
        if state.get('timeout'):
            raise httpx.ReadTimeout('secret upstream details', request=request)
        return httpx.Response(state['status'], json=state['body'])
    original = httpx.AsyncClient
    monkeypatch.setattr('tools.acquisition_store.httpx.AsyncClient',
                        lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    app = FastAPI()
    app.include_router(router)
    from web.api.outreach_eligibility_api import router as eligibility_router
    app.include_router(eligibility_router)
    with TestClient(app) as client:
        yield client, state


def test_disabled_has_no_database_effect(api, monkeypatch):
    client, state = api
    monkeypatch.delenv('ACQUISITION_ENABLED')
    assert client.get('/api/acquisition/workspaces').status_code == 404
    assert not state['requests']


@pytest.mark.parametrize('header', ['', 'Basic password', 'Bearer ', 'Bearer two tokens'])
def test_missing_or_malformed_bearer_rejected(api, header):
    client, state = api
    assert client.get('/api/acquisition/workspaces', headers={'Authorization': header}).status_code == 401
    assert not state['requests']


def test_forwards_user_token_and_public_key_only(api):
    client, state = api
    response = client.get('/api/acquisition/workspaces', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 200
    request = state['requests'][0]
    assert request.headers['authorization'] == 'Bearer user-token'
    assert request.headers['apikey'] == 'public-test-key'
    assert request.url.path == '/rest/v1/workspaces'
    assert request.url.params['limit'] == '100'


def test_membership_routing_uses_validated_ids_and_database_auth(api):
    client, state = api
    response = client.put(f'/api/acquisition/workspaces/{W}/memberships/{U}',
                          headers={'Authorization': 'Bearer user-token'},
                          json={'role': 'operator', 'status': 'active'})
    assert response.status_code == 200
    assert json.loads(state['requests'][0].content) == {
        'p_workspace': W, 'p_user': U, 'p_role': 'operator', 'p_status': 'active',
    }
    # Actor identity cannot be supplied by the client.
    response = client.put(f'/api/acquisition/workspaces/{W}/memberships/{U}',
                          headers={'Authorization': 'Bearer user-token'},
                          json={'role': 'owner', 'status': 'active', 'actor_id': U})
    assert response.status_code == 422
    assert len(state['requests']) == 1


@pytest.mark.parametrize('status,code,expected', [(401,'PGRST301',401), (403,'42501',403),
                                                 (400,'55000',409), (400,'22023',409), (409,'23505',409), (500,'XX000',503)])
def test_database_failures_are_fail_closed_and_sanitized(api, status, code, expected):
    client, state = api
    state.update(status=status, body={'code': code, 'message': 'secret upstream details'})
    response = client.post('/api/acquisition/workspaces', headers={'Authorization': 'Bearer user-token'},
                           json={'id': W, 'name': 'Hilltop'})
    assert response.status_code == expected
    assert 'secret upstream details' not in response.text


def test_timeout_does_not_retry_mutation(api):
    client, state = api
    state['timeout'] = True
    response = client.post('/api/acquisition/workspaces', headers={'Authorization': 'Bearer user-token'},
                           json={'id': W, 'name': 'Hilltop'})
    assert response.status_code == 503
    assert len(state['requests']) == 1


def test_service_key_cannot_replace_missing_public_key(api, monkeypatch):
    client, state = api
    for name in ('SUPABASE_PUBLISHABLE_KEY','SUPABASE_ANON_KEY','VITE_SUPABASE_ANON_KEY'):
        monkeypatch.delenv(name, raising=False)
    assert client.get('/api/acquisition/workspaces', headers={'Authorization': 'Bearer user-token'}).status_code == 503
    assert not state['requests']


def test_lead_queue_is_bounded_and_workspace_scoped(api):
    client, state = api
    response = client.get(f'/api/acquisition/workspaces/{W}/leads?limit=25&after={U}',
                          headers={'Authorization':'Bearer user-token'})
    assert response.status_code == 200
    assert json.loads(state['requests'][0].content) == {'p_workspace': W, 'p_after': U, 'p_limit': 25}
    assert client.get(f'/api/acquisition/workspaces/{W}/leads?limit=500',
                      headers={'Authorization':'Bearer user-token'}).status_code == 422
    assert len(state['requests']) == 1


def test_lead_binding_rejects_client_supplied_owner_and_requires_uuid(api):
    client, state = api
    response = client.post(f'/api/acquisition/workspaces/{W}/leads',
                           headers={'Authorization':'Bearer user-token'},json={'lead_id':U})
    assert response.status_code == 200
    assert json.loads(state['requests'][0].content) == {'p_workspace':W,'p_lead':U,'p_property':None}
    assert client.post(f'/api/acquisition/workspaces/{W}/leads',
                       headers={'Authorization':'Bearer user-token'},
                       json={'lead_id':U,'bound_by':U}).status_code == 422
    assert len(state['requests']) == 1


def test_contact_import_uses_source_reference_not_client_claims(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/leads/{U}/contacts/import'
    response = client.post(path, headers={'Authorization':'Bearer user-token'},
                           json={'source_field':'owner_phone_1'})
    assert response.status_code == 200
    assert json.loads(state['requests'][0].content) == {
        'p_workspace':W, 'p_lead':U, 'p_source_contact':None, 'p_field':'owner_phone_1',
    }
    for extra in ({'normalized_value':'+12145550101'}, {'verified':True}, {'consent':True}):
        assert client.post(path, headers={'Authorization':'Bearer user-token'},
                           json={'source_field':'owner_phone_1', **extra}).status_code == 422
    assert len(state['requests']) == 1


def test_eligibility_request_is_forwarded_without_client_authority(api):
    client, state = api
    payload = {'workspace_id':W, 'lead_id':U, 'contact_point_id':U, 'channel':'human_voice',
               'purpose':'principal_property_acquisition', 'actor_type':'human'}
    path = '/internal/outreach/eligibility/evaluate'
    state['body'] = {'decision':'REVIEW', 'permitted_actions':[]}
    assert client.post(path, headers={'Authorization':'Bearer user-token'}, json=payload).json() == state['body']
    assert json.loads(state['requests'][0].content) == {
        'p_workspace':W, 'p_lead':U, 'p_contact':U, 'p_channel':'human_voice',
        'p_purpose':'principal_property_acquisition', 'p_actor_type':'human', 'p_campaign':None,
    }
    assert client.post(path, headers={'Authorization':'Bearer user-token'},
                       json={**payload,'decision':'ALLOW'}).status_code == 422
    assert len(state['requests']) == 1


def test_suppression_request_rejects_client_actor(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/leads/{U}/contacts/{U}/suppressions'
    payload = {'id':U, 'channel':'all', 'reason':'seller_opt_out'}
    assert client.post(path, headers={'Authorization':'Bearer user-token'}, json=payload).status_code == 200
    assert json.loads(state['requests'][0].content)['p_reason'] == 'seller_opt_out'
    assert client.post(path, headers={'Authorization':'Bearer user-token'},
                       json={**payload,'actor_id':U}).status_code == 422
