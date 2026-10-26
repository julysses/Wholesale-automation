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


def test_owner_creation_uses_server_source_and_rejects_verified_claim(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/owners'
    response = client.post(path, headers={'Authorization':'Bearer user-token'},
                           json={'id':U,'source_lead_id':U})
    assert response.status_code == 200
    assert json.loads(state['requests'][0].content) == {'p_id':U,'p_workspace':W,'p_lead':U}
    assert client.post(path, headers={'Authorization':'Bearer user-token'},
                       json={'id':U,'source_lead_id':U,'verification_status':'verified'}).status_code == 422
    assert client.get(path+'?limit=51',headers={'Authorization':'Bearer user-token'}).status_code == 422


def test_owner_relationship_references_derive_property_server_side(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/owners/{U}/properties'
    payload = {'id':U,'lead_id':U,'relationship':'reported_owner','review_note':'Recorded assertion for review'}
    assert client.post(path,headers={'Authorization':'Bearer user-token'},json=payload).status_code == 200
    assert json.loads(state['requests'][0].content)['p_relationship'] == 'reported_owner'
    assert client.post(path,headers={'Authorization':'Bearer user-token'},
                       json={**payload,'property_id':U}).status_code == 422


def test_permission_import_derives_evidence_from_receipt_not_client_fields(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/leads/{U}/contacts/{U}/permissions/import'
    payload = {'source_kind':'facebook','source_id':U,'channel':'sms'}
    assert client.post(path,headers={'Authorization':'Bearer user-token'},json=payload).status_code == 200
    assert json.loads(state['requests'][0].content) == {
        'p_workspace':W,'p_lead':U,'p_contact':U,'p_source_kind':'facebook','p_source':U,'p_channel':'sms',
    }
    for field in ({'accepted':True},{'expires_at':'2099-01-01'},{'review_status':'approved'}):
        assert client.post(path,headers={'Authorization':'Bearer user-token'},json={**payload,**field}).status_code == 422
    assert len(state['requests']) == 1


def test_permission_revocation_and_status_routes_are_scoped(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/permissions/{U}/revocations'
    assert client.post(path,headers={'Authorization':'Bearer user-token'},
                       json={'id':U,'reason':'seller_revoked'}).status_code == 200
    assert json.loads(state['requests'][0].content) == {'p_id':U,'p_workspace':W,'p_permission':U,'p_reason':'seller_revoked'}
    path = f'/api/acquisition/workspaces/{W}/leads/{U}/permissions'
    assert client.get(path,headers={'Authorization':'Bearer user-token'}).status_code == 200
    assert state['requests'][1].url.params['workspace_id'] == 'eq.'+W
    assert state['requests'][1].url.params['lead_id'] == 'eq.'+U
    assert client.get(path+'?limit=51',headers={'Authorization':'Bearer user-token'}).status_code == 422


def test_underwriting_preview_checks_scoped_binding_and_does_not_write(api):
    client,state=api
    path=f'/api/acquisition/workspaces/{W}/leads/{U}/underwriting/preview'
    payload={'cases':{name:{'strategy':'fix_and_flip'} for name in ['base','downside','upside']}}
    state['body']=[]
    assert client.post(path,headers={'Authorization':'Bearer user-token'},json=payload).status_code==403
    state['body']=[{'workspace_id':W,'lead_id':U,'property_id':None}]
    response=client.post(path,headers={'Authorization':'Bearer user-token'},json=payload)
    assert response.status_code==200
    result=response.json()
    assert result['persisted'] is False and result['binding_offer'] is False
    assert result['cases']['base']['mao'] is None
    assert result['status']=='incomplete'
    assert result['property_id'] is None
    assert all(request.method=='GET' for request in state['requests'])
    assert all(request.url.params['workspace_id']=='eq.'+W for request in state['requests'])
