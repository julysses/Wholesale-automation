"""Mounted metadata API: exact scope, stale replies, no file or approval routes."""
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router

uid=lambda n:f'00000000-0000-4000-8000-{n:012d}'
W,C,A,P,R=[uid(n) for n in range(1,6)]
BASE=f'/api/acquisition/workspaces/{W}/contracts/{C}/versions/1/documents'
BODY={'id':A,'purpose':'purchase_contract','expected_sha256':'b'*64,'expected_byte_size':123,'media_type':'application/pdf',
      'retention_policy_id':P,'provenance_note':'Synthetic original contract document provenance.'}

def stamp(delta=0):return (datetime.now(timezone.utc)+timedelta(seconds=delta)).isoformat().replace('+00:00','Z')
def receipt():return {'artifact_id':A,'workspace_id':W,'contract_id':C,'contract_version':1,'retain_until':stamp(86400),
    'duplicate':False,'bytes_verified':False,'execution_authorized':False}
def state():return {'artifact_id':A,'workspace_id':W,'contract_id':C,'contract_version':1,'purpose':'purchase_contract',
    'expected_sha256':'b'*64,'expected_byte_size':123,'media_type':'application/pdf','created_at':stamp(-60),'retain_until':stamp(86400),
    'retention_policy_id':P,'revoked_at':None,'status':'pending_verification','bytes_verified':False,'legal_review_approved':False,
    'execution_authorized':False,'checked_at':stamp()}

@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_registration_derives_path_scope_and_never_accepts_actor_override(endpoint):
    client,store=endpoint;store.request.return_value=receipt()
    response=client.post(BASE,json=BODY)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['contract_id']==C and response.json()['execution_authorized'] is False
    store.request.assert_awaited_once_with('POST','rpc/register_contract_document',body={
        'p_id':A,'p_workspace':W,'p_contract':C,'p_version':1,'p_purpose':'purchase_contract','p_sha256':'b'*64,
        'p_byte_size':123,'p_media_type':'application/pdf','p_policy':P,'p_note':BODY['provenance_note']})

@pytest.mark.parametrize('change',[{'actor_id':R},{'workspace_id':R},{'contract_id':R},{'contract_version':2},
    {'campaign_id':R},{'execution_authorized':True},{'purpose':'mail_content'},{'purpose':'signed_and_approved'},
    {'expected_byte_size':True},{'expected_byte_size':0},{'expected_byte_size':10485761},{'expected_sha256':'A'*64},
    {'media_type':'text/html'},{'provenance_note':'too short'},{'object_url':'https://external.test/file'}])
def test_invalid_client_assertions_never_reach_registry(endpoint,change):
    client,store=endpoint
    assert client.post(BASE,json=BODY|change).status_code==422
    store.request.assert_not_awaited()

@pytest.mark.parametrize('version',['0','-1','2147483648','true','1.5'])
def test_invalid_version_path_is_rejected(endpoint,version):
    client,store=endpoint
    assert client.post(BASE.replace('/versions/1/','/versions/'+version+'/'),json=BODY).status_code==422
    store.request.assert_not_awaited()

@pytest.mark.parametrize('change',[{'artifact_id':R},{'workspace_id':R},{'contract_id':R},{'contract_version':2},
    {'contract_version':True},{'duplicate':'true'},{'bytes_verified':True},{'execution_authorized':True},
    {'retain_until':123},{'private':'secret-marker'}])
def test_unconfirmed_registration_preserves_request_and_redacts_bad_reply(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=BODY)
    assert response.status_code==503 and 'same request' in response.text and 'secret-marker' not in response.text
    assert response.headers['cache-control']=='no-store' and store.request.await_count==1


def test_historical_registration_retry_is_not_current_file_authority(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|{'duplicate':True,'retain_until':stamp(-60)}
    response=client.post(BASE,json=BODY)
    assert response.status_code==200 and response.json()['duplicate'] and not response.json()['bytes_verified']

@pytest.mark.parametrize('status',['pending_verification','revoked','expired','policy_review_required'])
def test_read_reports_unavailable_states_without_approval(endpoint,status):
    client,store=endpoint;value=state()|{'status':status}
    if status=='revoked':value['revoked_at']=stamp(-10)
    if status=='expired':value['retain_until']=stamp(-10)
    store.request.return_value=value
    response=client.get(BASE+'/'+A)
    assert response.status_code==200 and response.json()==value and response.headers['cache-control']=='no-store'
    store.request.assert_awaited_once_with('POST','rpc/contract_document_state',body={'p_workspace':W,'p_contract':C,'p_version':1,'p_artifact':A})

@pytest.mark.parametrize('change',[{'artifact_id':R},{'workspace_id':R},{'contract_id':R},{'contract_version':2},
    {'checked_at':stamp(-60)},{'checked_at':stamp(60)},{'bytes_verified':True},{'legal_review_approved':True},
    {'execution_authorized':True},{'status':'revoked'},{'status':'expired'},{'private':'secret-marker'}])
def test_changed_stale_or_false_authority_state_is_rejected(endpoint,change):
    client,store=endpoint;store.request.return_value=state()|change
    response=client.get(BASE+'/'+A)
    assert response.status_code==503 and 'secret-marker' not in response.text


def test_revocation_has_exact_scope_and_same_request_recovery(endpoint):
    client,store=endpoint
    result={'revocation_id':R,'artifact_id':A,'workspace_id':W,'duplicate':True,'execution_authorized':False}
    store.request.return_value=result
    response=client.post(BASE+'/'+A+'/revocations',json={'id':R,'reason':'Synthetic document withdrawn from review.'})
    assert response.status_code==200 and response.json()==result
    store.request.assert_awaited_once_with('POST','rpc/revoke_contract_document',body={'p_id':R,'p_workspace':W,'p_contract':C,'p_version':1,
        'p_artifact':A,'p_reason':'Synthetic document withdrawn from review.'})
    for key in ('revocation_id','artifact_id','workspace_id'):
        store.request.return_value=result|{key:P}
        response=client.post(BASE+'/'+A+'/revocations',json={'id':R,'reason':'Synthetic document withdrawn from review.'})
        assert response.status_code==503 and 'same request' in response.text

@pytest.mark.parametrize('status',[401,403,409,503])
def test_registry_errors_are_not_cached_or_retried(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Safe error')
    response=client.post(BASE,json=BODY)
    assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert store.request.await_count==1


def test_unimplemented_file_and_approval_paths_are_unavailable(endpoint):
    client,store=endpoint
    for suffix in ('bytes','download','approve','sign','verify'):
        assert client.post(BASE+'/'+A+'/'+suffix,json={}).status_code in (404,405)
    store.request.assert_not_awaited()


def test_disabled_acquisition_never_opens_document_store(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.post(BASE,json=BODY).status_code==404
        assert client.get(BASE+'/'+A).status_code==404
        assert client.post(BASE+'/'+A+'/revocations',json={'id':R,'reason':'Synthetic withdrawal reason for review.'}).status_code==404
