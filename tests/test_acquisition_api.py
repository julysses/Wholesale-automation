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
    assert {'source_type','inbound_integration_id','inbound_call_id','inbound_revision'} <= set(params['select'].split(','))
    state['body'] = []
    assert client.get(base+'?after='+intake, headers=headers).json()['next_after'] is None
    assert state['requests'][-1].url.params['id'] == 'gt.'+intake
    assert client.get(base+'/'+intake, headers=headers).status_code == 404
    state['body'] = [{'id': intake, 'prepared_answers': {'answers': {}}}]
    assert client.get(base+'/'+intake, headers=headers).json()['id'] == intake
    params = state['requests'][-1].url.params
    assert params['id'] == 'eq.'+intake and params['workspace_id'] == 'eq.'+W and params['limit'] == '1'
    assert {'source_type','inbound_integration_id','inbound_call_id','inbound_revision'} <= set(params['select'].split(','))


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


def test_property_source_touches_use_scoped_bounded_rpc(api):
    client,state=api
    state['body']={'items':[],'next_after':U,'scanned_count':1,'excluded_count':1,'totals_available':False,'execution_authorized':False}
    path=f'/api/acquisition/workspaces/{W}/leads/{U}/source-touches'
    response=client.get(path+f'?after={W}&limit=1',headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200 and response.json()['next_after']==U
    request=state['requests'][-1]
    assert request.headers['authorization']=='Bearer user-token'
    assert json.loads(request.content)=={'p_workspace':W,'p_lead':U,'p_after':W,'p_limit':1}
    count=len(state['requests'])
    for query in ('?limit=0','?limit=51','?after=not-a-uuid'):
        assert client.get(path+query,headers={'Authorization':'Bearer user-token'}).status_code==422
    assert len(state['requests'])==count


def cost_envelope():
    return dict(workspace_id=W,campaign_id=U,start_date='2026-10-24',end_date='2026-10-24',as_of='2026-10-25T06:00:00Z',
        reporting_timezone='America/Chicago',currency='USD',truncated=False,execution_authorized=False,
        items=[dict(id=U,workspace_id=W,campaign_id=U,date='2026-10-24',revision=1,amount_minor=12550,coverage='complete',
                    reporting_timezone='America/Chicago',currency='USD',observed_at='2026-10-25T06:00:00Z',
                    evidence_ref='persisted-cost-record:'+U,evidence_hash='a'*64,link_review_id=U,attribution_current=True,basis='reviewed_import')])


def cost_path():
    return f'/api/acquisition/workspaces/{W}/campaigns/{U}/cost-coverage?start_date=2026-10-24&end_date=2026-10-24&as_of=2026-10-25T06:00:00Z'


def test_cost_coverage_forwards_user_scope_and_preserves_exact_amount(api):
    client,state=api; state['body']=cost_envelope()
    response=client.get(cost_path(),headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200 and response.json()['total_cost_minor']=='12550'
    assert response.json()['days'][0]['attribution_current'] is True
    assert response.json()['cost_per_lead_minor'] is None
    assert state['requests'][-1].headers['authorization']=='Bearer user-token'
    assert json.loads(state['requests'][-1].content)['p_campaign']==U


@pytest.mark.parametrize('patch',[{'workspace_id':U},{'truncated':True},{'execution_authorized':True},{'currency':'CAD'},{'as_of':'2026-10-24T00:00:00Z'}])
def test_cost_coverage_rejects_mismatched_or_incomplete_envelope(api,patch):
    client,state=api; state['body']=cost_envelope()|patch
    assert client.get(cost_path(),headers={'Authorization':'Bearer user-token'}).status_code==502


def test_stale_attribution_suppresses_totals_and_empty_timezone_stays_unknown(api):
    client,state=api; state['body']=cost_envelope(); state['body']['items'][0]['attribution_current']=False
    value=client.get(cost_path(),headers={'Authorization':'Bearer user-token'}).json()
    assert value['total_cost_minor'] is None and value['observed_cost_minor'] is None
    assert 'COST_ATTRIBUTION_NOT_CURRENT' in value['reason_codes']
    state['body']=cost_envelope()|{'items':[],'reporting_timezone':None}
    value=client.get(cost_path(),headers={'Authorization':'Bearer user-token'}).json()
    assert value['status']=='unavailable' and value['reporting_timezone'] is None


def cost_import_body():
    return {'id':U,'link_review_id':U,'reviewed':True,'data':{
        'date':'2026-10-24','amount_minor':12550,'coverage':'complete','currency':'USD',
        'reporting_timezone':'America/Chicago','observed_at':'2026-10-25T06:00:00Z',
        'external_campaign_id':'987654','ad_account_id':'123456','evidence_ref':'private-reviewed-artifact',
        'evidence_hash':'a'*64,'expected_revision':0}}


def test_cost_import_uses_user_jwt_and_exact_reviewed_payload(api):
    client,state=api; state['body']={'id':U,'campaign_id':W,'revision':1,'duplicate':False,'execution_authorized':False}
    body=cost_import_body()
    response=client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=body)
    assert response.status_code==200 and response.json()==state['body']
    request=state['requests'][-1]; payload=json.loads(request.content)
    assert request.headers['authorization']=='Bearer user-token'
    assert payload=={'p_id':U,'p_workspace':W,'p_link_review':U,'p_data':body['data']}
    assert 'actor_id' not in payload


@pytest.mark.parametrize('patch',[
    {'amount_minor':True},{'amount_minor':'12550'},{'amount_minor':1.5},{'amount_minor':-1},{'amount_minor':10**15},
    {'amount_minor':None},{'coverage':'withdrawn'},{'currency':'CAD'}, {'expected_revision':True},
    {'expected_revision':-1},{'expected_revision':10**9},{'reporting_timezone':'invalid/zone'},
    {'observed_at':1792908000},{'observed_at':'2026-10-25T06:00:00'}, {'observed_at':'2026-10-24T06:00:00Z'},
    {'observed_at':'2999-01-01T00:00:00Z'},{'date':'2026-02-30'}, {'date':1792886400},
    {'external_campaign_id':123},{'ad_account_id':True},{'evidence_ref':' '*20},{'evidence_hash':'broken'}, {'actor_id':U}])
def test_cost_import_invalid_evidence_never_reaches_database(api,patch):
    client,state=api; body=cost_import_body(); body['data'].update(patch)
    assert client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=body).status_code==422
    assert state['requests']==[]


@pytest.mark.parametrize('reviewed',[False,1,'true',None])
def test_cost_import_requires_explicit_boolean_review(api,reviewed):
    client,state=api; body=cost_import_body(); body['reviewed']=reviewed
    assert client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=body).status_code==422
    assert not state['requests']


@pytest.mark.parametrize('patch',[{'id':W},{'revision':2},{'revision':True},{'campaign_id':'bad'},{'duplicate':1},{'execution_authorized':True}])
def test_unconfirmed_cost_reply_is_not_retried_or_reported_saved(api,patch):
    client,state=api; state['body']={'id':U,'campaign_id':W,'revision':1,'duplicate':False,'execution_authorized':False}|patch
    response=client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=cost_import_body())
    assert response.status_code==502 and len(state['requests'])==1


def test_cost_import_withdrawal_and_exact_retry_preserve_request(api):
    client,state=api; body=cost_import_body(); body['data'].update(coverage='withdrawn',amount_minor=None,expected_revision=2)
    state['body']={'id':U,'campaign_id':W,'revision':3,'duplicate':True,'execution_authorized':False}
    for _ in range(2):
        response=client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=body)
        assert response.status_code==200 and response.json()['duplicate'] is True
    assert state['requests'][0].content==state['requests'][1].content


def test_cost_import_disabled_or_unsigned_has_no_database_effect(api,monkeypatch):
    client,state=api; path=f'/api/acquisition/workspaces/{W}/cost-evidence'
    assert client.post(path,json=cost_import_body()).status_code==401
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert client.post(path,headers={'Authorization':'Bearer user-token'},json=cost_import_body()).status_code==404
    assert not state['requests']


@pytest.mark.parametrize('extra',[{'workspace_id':U},{'campaign_id':W},{'actor_id':U},{'execution_authorized':True}])
def test_cost_import_cannot_override_server_scope_or_authority(api,extra):
    client,state=api
    assert client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=cost_import_body()|extra).status_code==422
    assert not state['requests']

@pytest.mark.parametrize('status,code,expected', [(401,'PGRST301',401),(403,'42501',403),(400,'55000',409),(409,'40001',409),(409,'23505',409)])
def test_cost_import_marks_only_confirmed_rpc_rejection(api,status,code,expected):
    client,state=api
    state.update(status=status,body={'code':code})
    response=client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=cost_import_body())
    assert response.status_code==expected
    assert response.headers.get('X-Acquisition-Cost-Rejected')=='true'
    assert len(state['requests'])==1

@pytest.mark.parametrize('failure',['timeout','upstream','malformed'])
def test_cost_import_unknown_outcomes_never_claim_rejection(api,failure):
    client,state=api
    if failure=='timeout': state['timeout']=True
    elif failure=='upstream': state.update(status=500,body={'code':'XX000'})
    else: state['body']={'id':'unexpected'}
    response=client.post(f'/api/acquisition/workspaces/{W}/cost-evidence',headers={'Authorization':'Bearer user-token'},json=cost_import_body())
    assert response.status_code in {502,503}
    assert 'X-Acquisition-Cost-Rejected' not in response.headers


def test_lead_source_reads_include_call_revision_origin(api):
    client,state=api
    state['body']=[]
    response=client.get(f'/api/acquisition/workspaces/{W}/leads/{U}/sources',headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200
    params=state['requests'][-1].url.params
    assert params['workspace_id']=='eq.'+W and params['lead_id']=='eq.'+U
    assert {'source_type','external_lead_id','integration_id','inbound_event_id','inbound_revision'} <= set(params['select'].split(','))


def test_inbound_request_read_forwards_only_user_scope(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/inbound/integrations/{U}/calls/call_test/requests'
    response = client.get(path+f'?after={U}&limit=5', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 200
    request = state['requests'][0]
    assert request.url.path == '/rest/v1/rpc/acquisition_inbound_requests'
    assert request.headers['authorization'] == 'Bearer user-token'
    assert request.headers['apikey'] == 'public-test-key'
    assert json.loads(request.content) == {'p_workspace': W, 'p_integration': U, 'p_call': 'call_test', 'p_after': U, 'p_limit': 5}


@pytest.mark.parametrize('suffix', ['?limit=0', '?limit=51', '?after=bad'])
def test_inbound_request_read_rejects_invalid_bounds(api, suffix):
    client, state = api
    response = client.get(f'/api/acquisition/workspaces/{W}/inbound/integrations/{U}/calls/call_test/requests'+suffix, headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 422
    assert not state['requests']


def test_inbound_request_read_rejects_call_injection(api):
    client, state = api
    response = client.get(f'/api/acquisition/workspaces/{W}/inbound/integrations/{U}/calls/call.bad/requests', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 422
    assert not state['requests']


def test_inbound_request_read_denial_is_sanitized(api):
    client, state = api
    state.update(status=403, body={'code': '42501', 'message': 'private SQL details'})
    response = client.get(f'/api/acquisition/workspaces/{W}/inbound/integrations/{U}/calls/call_test/requests', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 403
    assert 'private SQL' not in response.text


def test_inbound_queue_read_uses_scoped_rpc(api):
    client, state = api
    response = client.get(f'/api/acquisition/workspaces/{W}/inbound/requests?limit=10&after={U}', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 200
    request = state['requests'][0]
    assert request.url.path == '/rest/v1/rpc/acquisition_inbound_request_queue_v2'
    assert request.headers['authorization'] == 'Bearer user-token'
    assert request.headers['apikey'] == 'public-test-key'
    assert json.loads(request.content) == {'p_workspace': W, 'p_after': U, 'p_limit': 10, 'p_status': 'all', 'p_assignment': 'all'}


@pytest.mark.parametrize('query', ['limit=0', 'limit=51', 'after=invalid'])
def test_inbound_queue_invalid_bounds_do_not_query_database(api, query):
    client, state = api
    response = client.get(f'/api/acquisition/workspaces/{W}/inbound/requests?'+query, headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 422
    assert not state['requests']


def test_inbound_review_api_scopes_state_history_and_write(api):
    client, state = api
    path = f'/api/acquisition/workspaces/{W}/inbound/requests/{U}'
    headers = {'Authorization': 'Bearer user-token'}
    assert client.get(path+'/state', headers=headers).status_code == 200
    assert json.loads(state['requests'][-1].content) == {'p_workspace': W, 'p_task': U}
    assert client.get(path+'/reviews?before=4&limit=5', headers=headers).status_code == 200
    params = state['requests'][-1].url.params
    assert params['workspace_id'] == 'eq.'+W and params['task_id'] == 'eq.'+U
    assert params['sequence'] == 'lt.4' and params['limit'] == '5'
    body = {'id': U, 'expected_sequence': 0, 'request_hash': 'a'*64, 'status': 'assigned',
            'assigned_user_id': U, 'review_note': 'Reviewed caller evidence and assigned follow-up.'}
    assert client.post(path+'/reviews', headers=headers, json=body).status_code == 200
    request = state['requests'][-1]
    assert request.url.path == '/rest/v1/rpc/review_acquisition_inbound_request'
    assert request.headers['authorization'] == 'Bearer user-token'
    assert json.loads(request.content) == {'p_id': U, 'p_workspace': W, 'p_task': U, 'p_expected_sequence': 0,
            'p_request_hash': 'a'*64, 'p_status': 'assigned', 'p_assignee': U, 'p_note': body['review_note']}


@pytest.mark.parametrize('change', [{'status':'call_completed'}, {'assigned_user_id':None}, {'status':'unassigned'},
    {'expected_sequence':-1}, {'request_hash':'invalid'}, {'actor_id':U}, {'review_note':'short'}])
def test_inbound_review_invalid_input_never_reaches_database(api, change):
    client, state = api
    body = {'id':U, 'expected_sequence':0, 'request_hash':'a'*64, 'status':'assigned', 'assigned_user_id':U,
            'review_note':'Reviewed caller evidence and assigned follow-up.'}
    body.update(change)
    response = client.post(f'/api/acquisition/workspaces/{W}/inbound/requests/{U}/reviews', headers={'Authorization':'Bearer user-token'}, json=body)
    assert response.status_code == 422
    assert not state['requests']


@pytest.mark.parametrize('query', ['status=sent', 'assignment=other-user'])
def test_inbound_queue_rejects_unrecognized_filters(api, query):
    client, state = api
    response=client.get(f'/api/acquisition/workspaces/{W}/inbound/requests?'+query,headers={'Authorization':'Bearer user-token'})
    assert response.status_code==422
    assert not state['requests']


def test_inbound_queue_forwards_personal_filter_without_client_actor(api):
    client, state = api
    response=client.get(f'/api/acquisition/workspaces/{W}/inbound/requests?status=on_hold&assignment=mine',headers={'Authorization':'Bearer user-token'})
    assert response.status_code==200
    assert json.loads(state['requests'][0].content)=={'p_workspace':W,'p_after':None,'p_limit':20,'p_status':'on_hold','p_assignment':'mine'}


MAIL_DRAFT={'id':U,'template_id':U,'expected_version':0,'name':'Mail draft','format':'letter',
            'tracking_mode':'phone','body':'Contact {{company_name}} at {{tracking_phone}}.'}
MAIL_PATH=f'/api/acquisition/workspaces/{W}/campaigns/{U}/mail-templates'
MAIL_RECEIPT={'id':U,'workspace_id':W,'template_id':U,'version':1,'status':'draft','duplicate':False,'execution_authorized':False}


def test_mail_draft_scoped_rpc_and_version_listing(api):
    client,state=api;state['body']=MAIL_RECEIPT
    response=client.post(MAIL_PATH,headers={'Authorization':'Bearer user-token'},json=MAIL_DRAFT)
    assert response.status_code==200 and response.json()==MAIL_RECEIPT
    request=state['requests'][-1]
    assert request.url.path=='/rest/v1/rpc/save_acquisition_mail_template'
    assert request.headers['authorization']=='Bearer user-token'
    assert request.headers['apikey']=='public-test-key'
    assert json.loads(request.content)=={'p_id':U,'p_workspace':W,'p_campaign':U,'p_template':U,
        'p_expected_version':0,'p_name':'Mail draft','p_format':'letter','p_tracking_mode':'phone','p_body':MAIL_DRAFT['body']}
    state['body']=[{'id':U},{'id':W}]
    result=client.get(MAIL_PATH+'?limit=1&after='+U+'&template_id='+U,headers={'Authorization':'Bearer user-token'})
    assert result.json()=={'items':[{'id':U}],'next_after':U}
    params=state['requests'][-1].url.params
    assert params['workspace_id']=='eq.'+W and params['campaign_id']=='eq.'+U
    assert params['acquisition_template_id']=='eq.'+U and params['id']=='gt.'+U and params['limit']=='2'


@pytest.mark.parametrize('change',[{'expected_version':True},{'expected_version':1.5},{'expected_version':-1},
    {'status':'approved'},{'approved_by':U},{'workspace_id':U},{'format':'email'},
    {'name':'  '},{'body':'No tracking'},{'body':'{{secret}} {{tracking_phone}}'},
    {'body':'{{tracking_phone}'},{'tracking_mode':'landing_page'}])
def test_mail_draft_rejects_unsupported_content_and_authority(api,change):
    client,state=api
    assert client.post(MAIL_PATH,headers={'Authorization':'Bearer user-token'},json=MAIL_DRAFT|change).status_code==422
    assert not state['requests']


@pytest.mark.parametrize('change',[{'workspace_id':U},{'version':True},{'version':2},{'duplicate':'false'},
    {'execution_authorized':0},{'execution_authorized':True},{'status':'approved'},{'extra':'private data'}])
def test_mail_draft_unconfirmed_receipt_is_not_success(api,change):
    client,state=api;state['body']=MAIL_RECEIPT|change
    response=client.post(MAIL_PATH,headers={'Authorization':'Bearer user-token'},json=MAIL_DRAFT)
    assert response.status_code==503 and 'private data' not in response.text
    assert len(state['requests'])==1


def test_mail_draft_timeout_no_retry_and_disabled_no_write(api,monkeypatch):
    client,state=api;state['timeout']=True
    assert client.post(MAIL_PATH,headers={'Authorization':'Bearer user-token'},json=MAIL_DRAFT).status_code==503
    assert len(state['requests'])==1
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert client.post(MAIL_PATH,headers={'Authorization':'Bearer user-token'},json=MAIL_DRAFT).status_code==404
    assert len(state['requests'])==1

DEST_PATH=f'/api/acquisition/workspaces/{W}/campaigns/{U}/mail-destinations/{U}'
DEST_REVIEW={'id':U,'expected_version':0,'action':'approved','mode':'phone','value':'+12145550100',
             'verification_ref':U,'verification_hash':'a'*64,'verified_at':'2026-01-01T00:00:00Z',
             'expires_at':'2099-01-01T00:00:00Z','note':'Synthetic controlled destination verification.'}
DEST_RECEIPT={'review_id':U,'workspace_id':W,'destination_id':U,'version':1,'duplicate':False,'execution_authorized':False}


def test_destination_review_scoped_user_rpc_and_withdrawal(api):
    client,state=api;state['body']=DEST_RECEIPT
    result=client.post(DEST_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=DEST_REVIEW)
    assert result.status_code==200 and result.json()==DEST_RECEIPT
    request=state['requests'][-1];payload=json.loads(request.content)
    assert request.url.path=='/rest/v1/rpc/review_acquisition_mail_destination'
    assert request.headers['authorization']=='Bearer user-token' and request.headers['apikey']=='public-test-key'
    assert payload['p_workspace']==W and payload['p_campaign']==U and payload['p_destination']==U
    assert payload['p_verification_hash']=='a'*64 and payload['p_action']=='approved'
    withdrawal={'id':U,'expected_version':0,'action':'withdrawn','note':'Synthetic destination withdrawal reason.'}
    assert client.post(DEST_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=withdrawal).status_code==200
    payload=json.loads(state['requests'][-1].content)
    assert all(payload[k] is None for k in ('p_mode','p_value','p_verification_ref','p_verification_hash','p_verified_at','p_expires_at'))


@pytest.mark.parametrize('change',[{'expected_version':True},{'expected_version':-1},{'actor_id':U},{'workspace_id':U},
    {'action':'sent'},{'mode':None},{'verification_ref':None},{'verification_hash':'bad'},
    {'verified_at':'2026-01-01T00:00:00'},{'expires_at':'2000-01-01T00:00:00Z'},{'note':' '*25},
    {'execution_authorized':True},{'action':'withdrawn'}])
def test_destination_review_rejects_bad_or_client_authority_fields(api,change):
    client,state=api
    assert client.post(DEST_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=DEST_REVIEW|change).status_code==422
    assert not state['requests']


@pytest.mark.parametrize('change',[{'workspace_id':U},{'version':True},{'duplicate':'false'},{'execution_authorized':0},
    {'execution_authorized':True},{'review_id':W},{'extra':'private data'}])
def test_destination_review_unconfirmed_receipts_are_held(api,change):
    client,state=api;state['body']=DEST_RECEIPT|change
    result=client.post(DEST_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=DEST_REVIEW)
    assert result.status_code==503 and 'private data' not in result.text and len(state['requests'])==1


def test_destination_state_rejects_wrong_scope_and_false_approval(api):
    client,state=api
    valid={'workspace_id':W,'campaign_id':U,'destination_id':U,'version':0,'latest_review':None,
           'status':'pending_review','review_current':False,'execution_authorized':False,'checked_at':'2026-10-28T12:00:00Z'}
    state['body']=valid
    assert client.get(DEST_PATH,headers={'Authorization':'Bearer user-token'}).json()==valid
    assert json.loads(state['requests'][-1].content)=={'p_workspace':W,'p_campaign':U,'p_destination':U}
    for change in ({'workspace_id':U},{'version':True},{'review_current':True},{'status':'approved'},
                   {'version':1},{'execution_authorized':True},{'extra':'unexpected evidence'}):
        state['body']=valid|change
        assert client.get(DEST_PATH,headers={'Authorization':'Bearer user-token'}).status_code==503


def test_destination_review_timeout_retains_single_attempt(api,monkeypatch):
    client,state=api;state['timeout']=True
    assert client.post(DEST_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=DEST_REVIEW).status_code==503
    assert len(state['requests'])==1
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert client.post(DEST_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=DEST_REVIEW).status_code==404
    assert len(state['requests'])==1


def test_destination_history_uses_fixed_scoped_projection_and_bounded_cursor(api):
    client,state=api;state['body']=[{'id':U},{'id':W}]
    response=client.get(DEST_PATH.rsplit('/',1)[0]+'?limit=1&after='+U,headers={'Authorization':'Bearer user-token'})
    assert response.json()=={'items':[{'id':U}],'next_after':U}
    request=state['requests'][-1]
    assert request.url.path=='/rest/v1/acquisition_mail_destination_reviews'
    assert dict(request.url.params)=={'select':'id,workspace_id,campaign_id,destination_id,version,action,mode,value,created_at',
        'workspace_id':'eq.'+W,'campaign_id':'eq.'+U,'order':'id','limit':'2','id':'gt.'+U}
    for query in ('limit=51','after=not-a-uuid'):
        assert client.get(DEST_PATH.rsplit('/',1)[0]+'?'+query,headers={'Authorization':'Bearer user-token'}).status_code==422
    assert len(state['requests'])==1


CONTENT_PATH=f'/api/acquisition/workspaces/{W}/campaigns/{U}/mail-content/prepare'
CONTENT_REQUEST={'creative_id':U,'destination_review_id':U,'company_name':'Hilltop Home Company'}
CONTENT_RESULT={'status':'content_prepared','execution_authorized':False,'content_approved':False,
    'preparation_hash':'a'*64,'checked_at':'2026-10-28T12:00:00Z','destination_valid_until':'2099-01-01T00:00:00Z',
    'snapshot':{'workspace_id':W,'campaign_id':U,'renderer_version':'acquisition-mail-render-v1','company_name':'Hilltop Home Company',
        'template':{'creative_id':U,'template_id':U,'version':1,'format':'letter','tracking_mode':'phone','body':'Contact {{company_name}} at {{tracking_phone}}.'},
        'destination':{'review_id':U,'destination_id':U,'version':1,'mode':'phone','value':'+12145550100',
            'verification_ref':U,'verification_hash':'b'*64,'verified_epoch':1767225600,'expires_epoch':4070908800,
            'reviewer_id':U,'reviewer_membership_epoch':1767225600}}}


def test_content_preparation_loads_only_identified_server_records(api):
    client,state=api;state['body']=CONTENT_RESULT
    response=client.post(CONTENT_PATH,headers={'Authorization':'Bearer user-token'},json=CONTENT_REQUEST)
    assert response.status_code==200 and response.json()==CONTENT_RESULT
    request=state['requests'][-1]
    assert request.url.path=='/rest/v1/rpc/prepare_acquisition_mail_content'
    assert request.headers['authorization']=='Bearer user-token'
    assert request.headers['apikey']=='public-test-key'
    assert json.loads(request.content)=={'p_workspace':W,'p_campaign':U,'p_creative':U,'p_destination_review':U,'p_company_name':'Hilltop Home Company'}


@pytest.mark.parametrize('change',[{'company_name':' '},{'company_name':'Bad\nIdentity'},{'company_name':'Bad\u202eIdentity'},
    {'company_name':'{{tracking_phone}}'},{'creative_id':'bad'},{'destination_review_id':None},
    {'content_approved':True},{'snapshot':{}},{'preparation_hash':'a'*64},{'workspace_id':W}])
def test_content_preparation_rejects_client_authority_and_invalid_identity(api,change):
    client,state=api
    assert client.post(CONTENT_PATH,headers={'Authorization':'Bearer user-token'},json=CONTENT_REQUEST|change).status_code==422
    assert not state['requests']


@pytest.mark.parametrize('where,change',[
    ('root',{'execution_authorized':0}),('root',{'execution_authorized':True}),('root',{'content_approved':True}),
    ('root',{'extra':'private evidence'}),('root',{'preparation_hash':'bad'}),('root',{'checked_at':'2099-01-01T00:00:00Z'}),
    ('root',{'destination_valid_until':'2098-01-01T00:00:00Z'}),('root',{'checked_at':'2026-10-28T12:00:00'}),
    ('snapshot',{'workspace_id':U}),('snapshot',{'campaign_id':W}),('snapshot',{'renderer_version':'unknown'}),
    ('snapshot',{'company_name':'Changed identity'}),('template',{'creative_id':W}),('template',{'version':True}),
    ('template',{'body':'{{unknown}} {{tracking_phone}}'}),('destination',{'review_id':W}),
    ('destination',{'value':'invalid number'}),('destination',{'verified_epoch':'NaN'}),
    ('destination',{'expires_epoch':'Infinity'}),('destination',{'verification_hash':'bad'}),
])
def test_content_preparation_rejects_unconfirmed_server_projection(api,where,change):
    import copy
    client,state=api;result=copy.deepcopy(CONTENT_RESULT)
    target=result if where=='root' else result['snapshot'] if where=='snapshot' else result['snapshot'][where]
    target.update(change);state['body']=result
    response=client.post(CONTENT_PATH,headers={'Authorization':'Bearer user-token'},json=CONTENT_REQUEST)
    assert response.status_code==503 and 'private evidence' not in response.text
    assert len(state['requests'])==1


def test_content_preparation_timeout_and_disabled_route(api,monkeypatch):
    client,state=api;state['timeout']=True
    assert client.post(CONTENT_PATH,headers={'Authorization':'Bearer user-token'},json=CONTENT_REQUEST).status_code==503
    assert len(state['requests'])==1
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert client.post(CONTENT_PATH,headers={'Authorization':'Bearer user-token'},json=CONTENT_REQUEST).status_code==404
    assert len(state['requests'])==1


CONTENT_REVIEW_PATH=f'/api/acquisition/workspaces/{W}/campaigns/{U}/mail-content/{U}'
CONTENT_REVIEW={'id':U,'expected_version':0,'action':'approved','creative_id':U,'destination_review_id':U,
    'company_name':'Hilltop Home Company','preparation_hash':'a'*64,'evidence_ref':U,'evidence_hash':'c'*64,
    'expires_at':'2098-01-01T00:00:00Z','note':'Reviewed exact content and retained evidence.'}
CONTENT_REVIEW_RECEIPT={'review_id':U,'workspace_id':W,'content_id':U,'version':1,'duplicate':False,'execution_authorized':False}
CONTENT_REVIEW_STATE={'workspace_id':W,'campaign_id':U,'content_id':U,'version':1,'review_current':True,
    'status':'approved','execution_authorized':False,'checked_at':CONTENT_RESULT['checked_at'],'preparation':CONTENT_RESULT,
    'latest_review':{'id':U,'workspace_id':W,'campaign_id':U,'content_id':U,'version':1,'action':'approved',
        'creative_id':U,'destination_review_id':U,'company_name':'Hilltop Home Company','renderer_version':'acquisition-mail-render-v1',
        'preparation_hash':'a'*64,'evidence_ref':U,'evidence_hash':'c'*64,'expires_at':CONTENT_REVIEW['expires_at'],
        'review_note':CONTENT_REVIEW['note'],'actor_id':U,'actor_membership_updated_at':'2026-01-01T00:00:00Z',
        'request_hash':'d'*64,'created_at':'2026-10-28T11:00:00Z'}}


def test_content_review_rpc_scope_bearer_and_withdrawal_preserves_evidence(api):
    client,state=api;state['body']=CONTENT_REVIEW_RECEIPT
    result=client.post(CONTENT_REVIEW_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=CONTENT_REVIEW)
    assert result.status_code==200 and result.json()==CONTENT_REVIEW_RECEIPT
    request=state['requests'][-1]
    assert request.url.path=='/rest/v1/rpc/review_acquisition_mail_content'
    assert request.headers['authorization']=='Bearer user-token' and request.headers['apikey']=='public-test-key'
    assert json.loads(request.content)=={'p_id':U,'p_workspace':W,'p_campaign':U,'p_content':U,'p_expected_version':0,
        'p_action':'approved','p_creative':U,'p_destination_review':U,'p_company_name':'Hilltop Home Company',
        'p_preparation_hash':'a'*64,'p_evidence_ref':U,'p_evidence_hash':'c'*64,'p_expires_at':'2098-01-01T00:00:00+00:00',
        'p_note':CONTENT_REVIEW['note']}
    withdrawal={'id':U,'expected_version':0,'action':'withdrawn','note':CONTENT_REVIEW['note']}
    assert client.post(CONTENT_REVIEW_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=withdrawal).status_code==200
    payload=json.loads(state['requests'][-1].content)
    assert all(payload[key] is None for key in ('p_creative','p_destination_review','p_company_name','p_preparation_hash','p_evidence_ref','p_evidence_hash','p_expires_at'))


@pytest.mark.parametrize('change',[{'action':'sent'},{'action':'withdrawn'},{'expected_version':True},{'expected_version':-1},
    {'creative_id':None},{'evidence_ref':None},{'evidence_hash':'bad'},{'preparation_hash':'bad'},
    {'expires_at':'2098-01-01T00:00:00'},{'note':' '*30},{'execution_authorized':True},{'actor_id':U},{'snapshot':{}}])
def test_content_review_rejects_missing_evidence_and_client_authority(api,change):
    client,state=api
    assert client.post(CONTENT_REVIEW_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=CONTENT_REVIEW|change).status_code==422
    assert not state['requests']


@pytest.mark.parametrize('change',[{'workspace_id':U},{'content_id':W},{'review_id':W},{'version':True},
    {'duplicate':'false'},{'execution_authorized':0},{'execution_authorized':True},{'extra':'private details'}])
def test_content_review_holds_unknown_receipts(api,change):
    client,state=api;state['body']=CONTENT_REVIEW_RECEIPT|change
    result=client.post(CONTENT_REVIEW_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=CONTENT_REVIEW)
    assert result.status_code==503 and 'private details' not in result.text and len(state['requests'])==1


def test_content_review_state_validates_current_and_historical_states(api):
    import copy
    client,state=api;state['body']=CONTENT_REVIEW_STATE
    result=client.get(CONTENT_REVIEW_PATH,headers={'Authorization':'Bearer user-token'})
    assert result.status_code==200 and result.json()==CONTENT_REVIEW_STATE
    assert json.loads(state['requests'][-1].content)=={'p_workspace':W,'p_campaign':U,'p_content':U}
    stale=copy.deepcopy(CONTENT_REVIEW_STATE);stale.update(status='requires_review',review_current=False,preparation=None)
    state['body']=stale
    assert client.get(CONTENT_REVIEW_PATH,headers={'Authorization':'Bearer user-token'}).status_code==200
    stale['status']='withdrawn';stale['latest_review']['action']='withdrawn'
    assert client.get(CONTENT_REVIEW_PATH,headers={'Authorization':'Bearer user-token'}).status_code==200
    state['body']={**stale,'status':'pending_review','version':0,'latest_review':None}
    assert client.get(CONTENT_REVIEW_PATH,headers={'Authorization':'Bearer user-token'}).status_code==200


@pytest.mark.parametrize('where,change',[('root',{'workspace_id':U}),('root',{'content_id':W}),('root',{'review_current':False}),
    ('root',{'execution_authorized':True}),('root',{'preparation':None}),('root',{'version':True}),
    ('root',{'status':'withdrawn'}),('root',{'checked_at':'2099-01-01T00:00:00Z'}),('root',{'extra':'unexpected'}),
    ('latest_review',{'version':2}),('latest_review',{'company_name':'Other company'}),('latest_review',{'content_id':W}),
    ('latest_review',{'creative_id':W}),('latest_review',{'destination_review_id':W}),('latest_review',{'preparation_hash':'f'*64}),
    ('latest_review',{'renderer_version':'old'}),('latest_review',{'expires_at':'2000-01-01T00:00:00Z'}),
    ('latest_review',{'created_at':'2090-01-01T00:00:00Z'}),('latest_review',{'action':'withdrawn'}),
    ('latest_review',{'expires_at':'2100-01-01T00:00:00Z'}),
    ('preparation',{'content_approved':True}),('preparation',{'execution_authorized':True})])
def test_content_review_state_rejects_mismatched_or_stale_approval(api,where,change):
    import copy
    client,state=api;result=copy.deepcopy(CONTENT_REVIEW_STATE)
    (result if where=='root' else result[where]).update(change);state['body']=result
    assert client.get(CONTENT_REVIEW_PATH,headers={'Authorization':'Bearer user-token'}).status_code==503


def test_content_review_timeout_keeps_one_attempt_and_disabled_gate(api,monkeypatch):
    client,state=api;state['timeout']=True
    assert client.post(CONTENT_REVIEW_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=CONTENT_REVIEW).status_code==503
    assert len(state['requests'])==1
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert client.post(CONTENT_REVIEW_PATH+'/reviews',headers={'Authorization':'Bearer user-token'},json=CONTENT_REVIEW).status_code==404
    assert len(state['requests'])==1


def api_proof_context():
    import copy
    from datetime import datetime, timezone
    checked=datetime.now(timezone.utc).isoformat()
    review=copy.deepcopy(CONTENT_REVIEW_STATE)
    review['checked_at']=checked;review['preparation']['checked_at']=checked
    return {'workspace_id':W,'campaign_id':U,'content_id':U,'lead_id':U,'review_state':review,
        'checked_at':checked,'execution_authorized':False,
        'property':{'property_id':U,'lead_id':U,'address_std':'123 Fixture St','unit':'2','city':'Dallas','state':'TX','zip':None}}


def test_proof_api_uses_one_scoped_read_and_never_client_source_material(api):
    client,state=api;state['body']=api_proof_context()
    result=client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U})
    assert result.status_code==200,result.text
    assert result.headers['cache-control']=='no-store'
    assert result.json()['proof_kind']=='internal_content_preview' and result.json()['execution_authorized'] is False
    assert len(state['requests'])==1
    request=state['requests'][0]
    assert request.url.path=='/rest/v1/rpc/acquisition_mail_proof_context'
    assert request.headers['authorization']=='Bearer user-token' and request.headers['apikey']=='public-test-key'
    assert json.loads(request.content)=={'p_workspace':W,'p_campaign':U,'p_content':U,'p_lead':U}


@pytest.mark.parametrize('extra',[{'property_address':'injected'},{'property_id':U},{'snapshot':{}},
    {'review_current':True},{'tracking_id':U},{'company_name':'Other company'},{'now':'2026-01-01'}])
def test_proof_api_rejects_client_evidence_and_identity_overrides(api,extra):
    client,state=api
    assert client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U}|extra).status_code==422
    assert not state['requests']


@pytest.mark.parametrize('scope',['workspace_id','campaign_id','content_id','lead_id'])
def test_proof_api_rejects_mismatched_database_context(api,scope):
    client,state=api;state['body']=api_proof_context();state['body'][scope]=U if scope=='workspace_id' else W
    result=client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U})
    assert result.status_code==503 and len(state['requests'])==1


def test_proof_api_requires_recent_current_approval(api):
    from datetime import datetime, timedelta, timezone
    client,state=api;raw=api_proof_context()
    checked=(datetime.now(timezone.utc)-timedelta(seconds=31)).isoformat()
    raw['checked_at']=checked;raw['review_state']['checked_at']=checked;raw['review_state']['preparation']['checked_at']=checked
    state['body']=raw
    assert client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U}).status_code==409
    raw=api_proof_context();raw['review_state'].update(review_current=False,status='requires_review',preparation=None);state['body']=raw
    assert client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U}).status_code==409


def test_proof_timeout_and_disabled_gate_never_retry_or_render(api,monkeypatch):
    client,state=api;state['timeout']=True
    assert client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U}).status_code==503
    assert len(state['requests'])==1
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    assert client.post(CONTENT_REVIEW_PATH+'/proof',headers={'Authorization':'Bearer user-token'},json={'lead_id':U}).status_code==404
    assert len(state['requests'])==1


def test_content_history_projection_pagination_and_scope(api):
    client,state=api;state['body']=[{'id':U},{'id':W}]
    path=CONTENT_REVIEW_PATH.rsplit('/',1)[0]
    result=client.get(path+'?limit=1&after='+U,headers={'Authorization':'Bearer user-token'})
    assert result.json()=={'items':[{'id':U}],'next_after':U}
    request=state['requests'][-1]
    assert request.url.path=='/rest/v1/acquisition_mail_content_reviews'
    assert dict(request.url.params)=={'select':'id,workspace_id,campaign_id,content_id,version,action,creative_id,destination_review_id,company_name,created_at',
        'workspace_id':'eq.'+W,'campaign_id':'eq.'+U,'order':'id','limit':'2','id':'gt.'+U}
    for query in ('limit=51','after=bad-id'):
        assert client.get(path+'?'+query,headers={'Authorization':'Bearer user-token'}).status_code==422
    assert len(state['requests'])==1
