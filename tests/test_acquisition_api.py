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
        body=state['responses'].pop(0) if state.get('responses') else state['body']
        return httpx.Response(state['status'], json=body)
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
                                                 (400,'55000',409), (409,'40001',409), (400,'22023',409), (409,'23505',409), (500,'XX000',503)])
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


def test_scenario_reservation_stays_user_scoped_when_worker_disabled(api,monkeypatch):
    client,state=api
    monkeypatch.delenv('ACQUISITION_CALCULATOR_ENABLED',raising=False)
    path=f'/api/acquisition/workspaces/{W}/leads/{U}/underwriting/scenarios'
    state['responses']=[{'id':U,'workspace_id':W,'lead_id':U,'status':'pending'},
                        [{'id':U,'workspace_id':W,'lead_id':U,'acquisition_status':'pending'}]]
    body={'id':U,'inputs':{'cases':{name:{'strategy':'fix_and_flip'} for name in ['base','downside','upside']}}}
    response=client.post(path,headers={'Authorization':'Bearer user-token'},json=body)
    assert response.status_code==200
    assert response.json()['analysis']['acquisition_status']=='pending'
    assert response.json()['calculation']['reason']=='CALCULATOR_NOT_ENABLED'
    assert len(state['requests'])==2
    assert all(request.headers['Authorization']=='Bearer user-token' for request in state['requests'])
    assert 'p_outputs' not in json.loads(state['requests'][0].content)
    assert client.post(path,headers={'Authorization':'Bearer user-token'},json={**body,'outputs':{'mao':999999}}).status_code==422


def test_offer_proposals_and_reviews_use_user_identity_and_bounded_contract(api):
    client,state=api
    headers={'Authorization':'Bearer user-token'}
    path=f'/api/acquisition/workspaces/{W}/offers'
    body={'id':U,'analysis_id':U,'case':'base','amount':'140000.00','note':'Review requested'}
    assert client.post(path,headers=headers,json=body).status_code==200
    req=state['requests'][-1]
    assert req.headers['Authorization']=='Bearer user-token'
    assert json.loads(req.content)['p_amount']=='140000.00'
    assert client.post(path,headers=headers,json={**body,'approved_by':U}).status_code==422
    assert client.post(path,headers=headers,json={**body,'amount':'140000.001'}).status_code==422
    review={'id':U,'expected_sequence':1,'status':'amount_approved','note':'Internal review','review_notes':{}}
    assert client.post(path+f'/{U}/reviews',headers=headers,json=review).status_code==200
    assert json.loads(state['requests'][-1].content)['p_expected_sequence']==1
    assert client.post(path+f'/{U}/reviews',headers=headers,json={**review,'status':'sent'}).status_code==422
    assert client.get(path+f'/{U}/reviews?limit=51',headers=headers).status_code==422
    assert client.get(path+f'/{U}/reviews',headers=headers).status_code==200
    assert state['requests'][-1].url.params['workspace_id']=='eq.'+W


def test_current_offer_review_and_queue_use_scoped_read_rpcs(api):
    client,state=api
    headers={'Authorization':'Bearer user-token'}
    path=f'/api/acquisition/workspaces/{W}/offers'
    state['body']={'items':[],'next_after':None,'transmission_authorized':False}
    response=client.get(path+f'?after={U}&limit=10',headers=headers)
    assert response.status_code==200
    request=state['requests'][-1]
    assert request.url.path.endswith('/rpc/acquisition_offer_review_queue')
    assert request.headers['Authorization']=='Bearer user-token'
    assert json.loads(request.content)=={'p_workspace':W,'p_after':U,'p_limit':10}
    assert client.get(path+'?limit=51',headers=headers).status_code==422
    state['body']={'historical_status':'amount_approved','amount_approval_current':False,'transmission_authorized':False}
    response=client.get(path+f'/{U}/state',headers=headers)
    assert response.status_code==200 and response.json()['amount_approval_current'] is False
    assert json.loads(state['requests'][-1].content)=={'p_workspace':W,'p_offer':U}


def test_review_lead_summary_requires_exact_workspace_binding_before_address_read(api):
    client,state=api
    headers={'Authorization':'Bearer user-token'}
    path=f'/api/acquisition/workspaces/{W}/leads/{U}/summary'
    state['body']=[]
    assert client.get(path,headers=headers).status_code==403
    assert len(state['requests'])==1
    state['responses']=[[{'workspace_id':W,'lead_id':U,'property_id':U}],[{'id':U,'property_address':'Fixture address','city':'Dallas'}]]
    response=client.get(path,headers=headers)
    assert response.status_code==200
    assert response.json()['property_id']==U
    assert state['requests'][-1].url.params['select']=='id,property_address,city'
    assert all(request.headers['Authorization']=='Bearer user-token' for request in state['requests'])


def test_inquiry_health_forwards_user_scope_and_bounds_page(api):
    client,state=api
    header={'Authorization':'Bearer operator-session'}
    response=client.get(f'/api/acquisition/workspaces/{W}/inquiries/health?limit=5',headers=header)
    assert response.status_code==200
    request=state['requests'][-1]
    assert request.url.path.endswith('/rpc/acquisition_inquiry_health')
    assert request.headers['Authorization']=='Bearer operator-session'
    assert json.loads(request.content)=={'p_workspace':W,'p_after':None,'p_limit':5}
    count=len(state['requests'])
    assert client.get(f'/api/acquisition/workspaces/{W}/inquiries/health?limit=51',headers=header).status_code==422
    assert client.get(f'/api/acquisition/workspaces/{W}/inquiries/health?after=invalid',headers=header).status_code==422
    assert len(state['requests'])==count


def test_recovery_requires_exact_review_and_forwards_no_actor_override(api):
    client,state=api
    receipt='20000000-0000-4000-8000-000000000001'
    path=f'/api/acquisition/workspaces/{W}/inquiries/{receipt}/recoveries'
    body={'id':'e0000000-0000-4000-8000-000000000001','expected_updated_at':'2026-10-26T12:00:00.123456Z',
          'expected_reason':'CREDENTIALS_INVALID','review_note':'Replaced credential and verified Page access','evidence_ref':'review/1'}
    header={'Authorization':'Bearer owner-session'}
    assert client.post(path,headers=header,json=body).status_code==200
    sent=json.loads(state['requests'][-1].content)
    assert sent['p_expected_updated_at']=='2026-10-26T12:00:00.123456+00:00'
    assert 'actor_id' not in sent
    assert state['requests'][-1].headers['Authorization']=='Bearer owner-session'
    count=len(state['requests'])
    assert client.post(path,headers=header,json={**body,'actor_id':U}).status_code==422
    assert client.post(path,headers=header,json={**body,'expected_updated_at':'2026-10-26T12:00:00'}).status_code==422
    assert client.post(path,headers=header,json={**body,'expected_reason':'PAYLOAD_EXPIRED'}).status_code==422
    assert len(state['requests'])==count


def test_intake_candidates_forwards_user_scope_and_validates_bounds(api):
    client, state = api
    intake = '70000000-0000-4000-8000-000000000001'
    path = f'/api/acquisition/workspaces/{W}/intakes/{intake}/candidates'
    response = client.get(path+'?limit=12', headers={'Authorization': 'Bearer test-jwt'})
    assert response.status_code == 200
    request = state['requests'][-1]
    assert request.url.path.endswith('/rpc/acquisition_intake_candidates')
    assert request.headers['authorization'] == 'Bearer test-jwt'
    assert json.loads(request.content) == {'p_workspace': W, 'p_intake': intake, 'p_limit': 12}
    count = len(state['requests'])
    for limit in (0, 51):
        assert client.get(path+f'?limit={limit}', headers={'Authorization': 'Bearer test-jwt'}).status_code == 422
    assert len(state['requests']) == count


def test_identity_review_state_history_and_mutation_use_current_user_scope(api):
    client, state = api
    intake = '70000000-0000-4000-8000-000000000001'
    target = '20000000-0000-4000-8000-000000000001'
    base = f'/api/acquisition/workspaces/{W}/intakes/{intake}'
    headers = {'Authorization': 'Bearer test-jwt'}
    assert client.get(base+'/identity-state', headers=headers).status_code == 200
    assert json.loads(state['requests'][-1].content)['p_target'] is None
    assert client.get(base+'/identity-state?target='+target, headers=headers).status_code == 200
    assert json.loads(state['requests'][-1].content)['p_target'] == target
    body = {'id': intake, 'expected_sequence': 0, 'preparation_hash': 'a'*64, 'action': 'repeat_inquiry',
            'target_lead_id': target, 'target_hash': 'b'*64, 'property_basis': 'parcel_document',
            'property_evidence_ref': 'parcel-review-42', 'seller_evidence_ref': 'seller-review-42',
            'review_note': 'Reviewer verified the independent identity evidence.'}
    assert client.post(base+'/identity-reviews', headers=headers, json=body).status_code == 200
    request = state['requests'][-1]
    assert request.url.path.endswith('/rpc/review_acquisition_intake_identity')
    assert request.headers['authorization'] == 'Bearer test-jwt'
    forwarded = json.loads(request.content)
    assert forwarded['p_target'] == target and forwarded['p_intake'] == intake
    assert forwarded['p_workspace'] == W and forwarded['p_preparation_hash'] == 'a'*64
    count = len(state['requests'])
    assert client.post(base+'/identity-reviews', headers=headers, json={**body, 'actor_id': U}).status_code == 422
    assert client.post(base+'/identity-reviews', headers=headers, json={**body, 'property_basis': 'phone_match'}).status_code == 422
    assert len(state['requests']) == count
    assert client.get(base+'/identity-reviews?before=8&limit=3', headers=headers).status_code == 200
    params = state['requests'][-1].url.params
    assert params['workspace_id'] == 'eq.'+W and params['intake_id'] == 'eq.'+intake
    assert params['sequence'] == 'lt.8' and params['order'] == 'sequence.desc' and params['limit'] == '3'


def test_intake_queue_and_detail_are_scoped_and_bounded(api):
    client, state = api
    intake = '70000000-0000-4000-8000-000000000001'
    other = '70000000-0000-4000-8000-000000000002'
    base = f'/api/acquisition/workspaces/{W}/intakes'
    headers = {'Authorization': 'Bearer test-jwt'}
    state['body'] = [{'id': intake}, {'id': other}]
    result = client.get(base+'?limit=1', headers=headers)
    assert result.json() == {'items': [{'id': intake}], 'next_after': intake}
    params = state['requests'][-1].url.params
    assert params['workspace_id'] == 'eq.'+W and params['limit'] == '2' and params['order'] == 'id'
    state['body'] = []
    assert client.get(base+'?after='+intake, headers=headers).json()['next_after'] is None
    assert state['requests'][-1].url.params['id'] == 'gt.'+intake
    assert client.get(base+'/'+intake, headers=headers).status_code == 404
    state['body'] = [{'id': intake, 'prepared_answers': {'answers': {}}}]
    assert client.get(base+'/'+intake, headers=headers).json()['id'] == intake
    params = state['requests'][-1].url.params
    assert params['id'] == 'eq.'+intake and params['workspace_id'] == 'eq.'+W and params['limit'] == '1'


def test_intake_assessment_is_server_derived_and_scoped(api):
    client, state = api
    intake = '70000000-0000-4000-8000-000000000001'
    base = f'/api/acquisition/workspaces/{W}/intakes/{intake}'
    headers = {'Authorization': 'Bearer test-jwt'}
    assert client.get(base+'/qualification-state', headers=headers).status_code == 200
    assert json.loads(state['requests'][-1].content) == {'p_workspace': W, 'p_intake': intake}
    body = {'id': intake, 'expected_sequence': 0, 'evidence_hash': 'a'*64}
    assert client.post(base+'/assessments', headers=headers, json=body).status_code == 200
    request = state['requests'][-1]
    assert request.url.path.endswith('/rpc/record_acquisition_intake_assessment')
    assert request.headers['authorization'] == 'Bearer test-jwt'
    assert json.loads(request.content) == {'p_id': intake, 'p_workspace': W, 'p_intake': intake, 'p_expected_sequence': 0, 'p_evidence_hash': 'a'*64}
    count = len(state['requests'])
    for extra in ({'classification': 'qualified'}, {'actor_id': U}, {'evidence_hash': 'invalid'}):
        assert client.post(base+'/assessments', headers=headers, json={**body, **extra}).status_code == 422
    assert len(state['requests']) == count
    assert client.get(base+'/assessments?before=4&limit=2', headers=headers).status_code == 200
    params = state['requests'][-1].url.params
    assert params['workspace_id'] == 'eq.'+W and params['intake_id'] == 'eq.'+intake
    assert params['sequence'] == 'lt.4' and params['limit'] == '2'


def test_intake_underwriting_uses_server_canonical_identity_and_fresh_context(api, monkeypatch):
    client, state = api
    monkeypatch.delenv('ACQUISITION_CALCULATOR_ENABLED', raising=False)
    intake = '70000000-0000-4000-8000-000000000001'
    canonical = '20000000-0000-4000-8000-000000000001'
    path = f'/api/acquisition/workspaces/{W}/intakes/{intake}/underwriting/scenarios'
    body = {'id': U, 'evidence_hash': 'a'*64, 'inputs': {'cases': {name: {'strategy': 'fix_and_flip'} for name in ['base', 'downside', 'upside']}}}
    state['responses'] = [
        {'id': U, 'workspace_id': W, 'intake_id': intake, 'lead_id': canonical, 'status': 'pending'},
        [{'id': U, 'workspace_id': W, 'lead_id': canonical, 'acquisition_status': 'pending'}],
        {'analysis_id': U, 'intake_id': intake, 'has_intake': True, 'qualification_current': False},
    ]
    response = client.post(path, headers={'Authorization': 'Bearer user-token'}, json=body)
    assert response.status_code == 200
    assert response.json()['analysis']['lead_id'] == canonical
    assert response.json()['intake_context']['qualification_current'] is False
    assert response.json()['calculation']['reason'] == 'CALCULATOR_NOT_ENABLED'
    request = state['requests'][0]
    assert request.url.path.endswith('/rpc/reserve_acquisition_intake_analysis')
    assert json.loads(request.content)['p_intake'] == intake
    assert 'p_lead' not in json.loads(request.content)
    assert state['requests'][1].url.params['lead_id'] == 'eq.'+canonical
    assert all(request.headers['authorization'] == 'Bearer user-token' for request in state['requests'])
    assert client.post(path, headers={'Authorization': 'Bearer user-token'}, json={**body, 'target_lead_id': canonical}).status_code == 422


def test_saved_analysis_provenance_is_user_scoped_and_preserves_stale_evidence(api):
    client, state = api
    context = {'analysis_id': U, 'intake_id': W, 'assessment_id': U, 'has_intake': True, 'qualification_current': False}
    state['responses'] = [context, [{'analysis_id': U, 'intake_id': W, 'assessment_id': U, 'evidence_hash': 'a'*64}]]
    response = client.get(f'/api/acquisition/workspaces/{W}/underwriting/scenarios/{U}/intake-context', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 200 and response.json() == {**context, 'evidence_hash': 'a'*64}
    assert state['requests'][1].url.params['workspace_id'] == 'eq.'+W
    assert state['requests'][1].url.params['analysis_id'] == 'eq.'+U
    assert all(r.headers['authorization'] == 'Bearer user-token' for r in state['requests'])


@pytest.mark.parametrize('row', [[], [{'analysis_id': W, 'intake_id': W, 'assessment_id': U, 'evidence_hash': 'a'*64}],
                               [{'analysis_id': U, 'intake_id': W, 'assessment_id': U, 'evidence_hash': 'invalid'}]])
def test_saved_analysis_provenance_rejects_missing_or_mismatched_source(api, row):
    client, state = api
    state['responses'] = [{'analysis_id': U, 'intake_id': W, 'assessment_id': U, 'has_intake': True, 'qualification_current': True}, row]
    assert client.get(f'/api/acquisition/workspaces/{W}/underwriting/scenarios/{U}/intake-context', headers={'Authorization': 'Bearer user-token'}).status_code == 503


def test_manual_analysis_provenance_needs_no_intake_read(api):
    client, state = api
    state['body'] = {'analysis_id': U, 'has_intake': False, 'intake_id': None, 'assessment_id': None, 'qualification_current': True}
    response = client.get(f'/api/acquisition/workspaces/{W}/underwriting/scenarios/{U}/intake-context', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 200 and response.json()['evidence_hash'] is None
    assert len(state['requests']) == 1


def test_intake_attribution_returns_metadata_only_through_user_scope(api):
    from tools.acquisition_intake import prepare_facebook_intake
    client, state = api
    state['body'] = [{'id': U, 'lead_id': W, 'prepared_answers': prepare_facebook_intake(leadgen_id='1',provider_data={
        'id':'1','form_id':'2','campaign_id':'3','field_data':[{'name':'phone','values':['2145550101']}],
    })}]
    path=f'/api/acquisition/workspaces/{W}/intakes/{U}/attribution'
    response=client.get(path,headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200
    assert response.json()['attribution']['campaign_id']=='3'
    assert response.json()['attribution']['spend_cents'] is None
    assert '2145550101' not in response.text
    request=state['requests'][0]
    assert request.url.params['workspace_id']=='eq.'+W and request.url.params['id']=='eq.'+U
    assert request.headers['authorization']=='Bearer user-token'
    state['body']=[]
    assert client.get(path,headers={'Authorization':'Bearer user-token'}).status_code==404


def test_campaign_draft_uses_controlled_rpc_and_scoped_list(api):
    client,state=api
    path=f'/api/acquisition/workspaces/{W}/campaigns'
    body={'id':U,'name':'Facebook draft','channel':'facebook','budget_cents':50000,'currency':'USD'}
    state['body']={'id':U,'status':'draft','execution_authorized':False}
    response=client.post(path,headers={'Authorization':'Bearer user-token'},json=body)
    assert response.status_code==200 and response.json()['execution_authorized'] is False
    sent=json.loads(state['requests'][-1].content)
    assert sent=={'p_id':U,'p_workspace':W,'p_name':'Facebook draft','p_channel':'facebook','p_budget_cents':50000,'p_currency':'USD'}
    assert state['requests'][-1].headers['authorization']=='Bearer user-token'
    for changes in ({'status':'active'},{'approved_by':U},{'budget_cents':True},{'budget_cents':1.5},{'currency':'EUR'}):
        assert client.post(path,headers={'Authorization':'Bearer user-token'},json={**body,**changes}).status_code==422
    state['body']=[{'id':U},{'id':W}]
    response=client.get(path+'?limit=1&after='+U,headers={'Authorization':'Bearer user-token'})
    assert response.json()=={'items':[{'id':U}],'next_after':U}
    params=state['requests'][-1].url.params
    assert params['workspace_id']=='eq.'+W and params['id']=='gt.'+U and params['limit']=='2'


def test_campaign_link_review_binds_scope_identity_and_rejects_authority_overrides(api):
    client,state=api
    base=f'/api/acquisition/workspaces/{W}/intakes/{U}'
    state['body']={'sequence':0,'link_current':False,'execution_authorized':False}
    response=client.get(base+'/campaign-link-state',headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200
    assert json.loads(state['requests'][-1].content)=={'p_workspace':W,'p_intake':U}
    body={'id':U,'expected_sequence':0,'preparation_hash':'a'*64,'action':'link','campaign_id':W,
          'ad_account_id':'123','evidence_ref':'Reviewed account evidence','review_note':'Reviewed account and campaign ownership.'}
    state['body']={'review_id':U,'sequence':1,'duplicate':False,'execution_authorized':False}
    assert client.post(base+'/campaign-link-reviews',headers={'Authorization':'Bearer user-token'},json=body).status_code==200
    request=state['requests'][-1]
    assert request.headers['authorization']=='Bearer user-token'
    sent=json.loads(request.content)
    assert sent['p_workspace']==W and sent['p_intake']==U and sent['p_ad_account']=='123'
    assert 'actor_id' not in sent
    count=len(state['requests'])
    for changes in ({'actor_id':U},{'integration_id':U},{'external_campaign_id':'123'},{'expected_sequence':True},
                    {'action':'revoke'},{'campaign_id':None},{'ad_account_id':None},{'ad_account_id':'act_123'}):
        assert client.post(base+'/campaign-link-reviews',headers={'Authorization':'Bearer user-token'},json={**body,**changes}).status_code==422
    assert len(state['requests'])==count
    assert client.post(base+'/campaign-link-reviews',headers={'Authorization':'Bearer user-token'},json={**body,'action':'revoke','campaign_id':None,'ad_account_id':None}).status_code==200


def test_campaign_history_resolves_scope_server_side_and_bounds_pages(api):
    client,state=api
    state['responses']=[{'integration_id':U,'external_campaign_id':'123'},[]]
    response=client.get(f'/api/acquisition/workspaces/{W}/intakes/{U}/campaign-link-reviews?before=5&limit=10',headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200 and response.json()==[]
    first,last=state['requests']
    assert json.loads(first.content)=={'p_workspace':W,'p_intake':U}
    assert last.url.params['workspace_id']=='eq.'+W and last.url.params['integration_id']=='eq.'+U
    assert last.url.params['external_campaign_id']=='eq.123' and last.url.params['sequence']=='lt.5' and last.url.params['limit']=='10'
    assert last.headers['authorization']=='Bearer user-token'


def test_source_capture_and_read_are_scoped_versioned_and_non_executing(api):
    client,state=api
    base=f'/api/acquisition/workspaces/{W}'
    path=base+f'/intakes/{U}/source-campaign-reviews'
    state['body']={'id':U,'source_id':U,'link_review_id':W,'execution_authorized':False}
    response=client.post(path,headers={'Authorization':'Bearer user-token'},json={'id':U,'link_review_id':W})
    assert response.status_code==200
    assert json.loads(state['requests'][-1].content)=={'p_id':U,'p_workspace':W,'p_source':U,'p_link_review':W}
    assert client.post(path,headers={'Authorization':'Bearer user-token'},json={'id':U,'link_review_id':W,'campaign_id':W}).status_code==422
    state['body']=[{'id':U},{'id':W}]
    response=client.get(base+f'/leads/{U}/sources?limit=1&after={U}',headers={'Authorization':'Bearer user-token'})
    assert response.json()['next_after']==U
    params=state['requests'][-1].url.params
    assert params['workspace_id']=='eq.'+W and params['lead_id']=='eq.'+U and params['id']=='gt.'+U
    state['responses']=[[{'id':U,'link_review_id':W}],{'latest_review':{'id':W},'link_current':True,'preparation_hash':'a'*64,'internal_campaign_id':W},[{'id':U,'link_review_id':W}]]
    response=client.get(path,headers={'Authorization':'Bearer user-token'})
    assert response.json()['items'][0]['attribution_current'] is True and response.json()['execution_authorized'] is False
    assert state['requests'][-1].url.params['source_id']=='eq.'+U
    assert state['requests'][-1].url.params['link_review_id']=='eq.'+W
    assert response.json()['current_capture']['id']==U
    state['responses']=[[{'id':U,'link_review_id':W}],{'latest_review':{'id':W},'link_current':False,'preparation_hash':'a'*64}]
    assert client.get(path,headers={'Authorization':'Bearer user-token'}).json()['items'][0]['attribution_current'] is False


def test_current_source_snapshot_lookup_is_independent_of_history_cursor(api):
    client,state=api
    state['responses']=[[],{'latest_review':{'id':W},'link_current':True,'preparation_hash':'a'*64,'internal_campaign_id':W},[{'id':U,'link_review_id':W}]]
    response=client.get(f'/api/acquisition/workspaces/{W}/intakes/{U}/source-campaign-reviews?after={W}',headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200
    assert response.json()['items']==[] and response.json()['current_capture']['id']==U
    assert state['requests'][0].url.params['id']=='gt.'+W
    assert 'id' not in state['requests'][-1].url.params
    assert state['requests'][-1].url.params['link_review_id']=='eq.'+W
