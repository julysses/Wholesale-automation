"""Mounted document linking preserves original identity and exact uncertain requests."""
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
W='10000000-0000-4000-8000-000000000001'; C='20000000-0000-4000-8000-000000000001'
I='30000000-0000-4000-8000-000000000001'; A='30000000-0000-4000-8000-000000000002'
V='30000000-0000-4000-8000-000000000003'; R='30000000-0000-4000-8000-000000000004'
PATH=f'/api/acquisition/workspaces/{W}/contracts/{C}/versions/2/document-links'
BODY=dict(id=I,source_version=1,artifact_id=A,verification_id=V,sha256='a'*64,note='Original title document supports this changed contract draft.')
RECEIPT=dict(link_id=I,workspace_id=W,contract_id=C,contract_version=2,source_version=1,artifact_id=A,duplicate=False,review_approved=False,execution_authorized=False)
WITHDRAW=dict(id=R,reason='Original document no longer supports this draft version.')
WITHDRAWAL=dict(revocation_id=R,workspace_id=W,contract_id=C,contract_version=2,link_id=I,duplicate=False,execution_authorized=False)
@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store

def test_link_maps_only_exact_original_identity(endpoint):
    client,store=endpoint;store.request.return_value=RECEIPT
    response=client.post(PATH,json=BODY)
    assert response.status_code==200 and response.json()==RECEIPT and response.headers['cache-control']=='no-store'
    store.request.assert_awaited_once_with('POST','rpc/link_contract_document',body=dict(p_id=I,p_workspace=W,p_contract=C,p_version=2,p_source_version=1,p_artifact=A,p_verification=V,p_sha256='a'*64,p_note=BODY['note']))
    store.request.return_value=RECEIPT|{'duplicate':True}
    assert client.post(PATH,json=BODY).json()['duplicate']

@pytest.mark.parametrize('change',[{'source_version':2},{'source_version':3},{'source_version':True},{'source_version':0},
    {'workspace_id':W},{'actor_id':A},{'execution_authorized':True},{'note':' '*20},{'note':'\x00'+'a'*30},{'sha256':'A'*64}])
def test_invalid_or_injected_link_never_reaches_store(endpoint,change):
    client,store=endpoint;assert client.post(PATH,json=BODY|change).status_code==422;store.request.assert_not_awaited()

@pytest.mark.parametrize('change',[{'workspace_id':A},{'contract_id':A},{'contract_version':3},{'source_version':2},{'artifact_id':V},
    {'link_id':A},{'duplicate':'true'},{'review_approved':True},{'execution_authorized':True},{'private':'secret-marker'}])
def test_uncertain_link_response_does_not_confirm_or_disclose(endpoint,change):
    client,store=endpoint;store.request.return_value=RECEIPT|change
    response=client.post(PATH,json=BODY)
    assert response.status_code==503 and 'same saved request' in response.text and 'secret-marker' not in response.text
    assert response.headers['cache-control']=='no-store' and 'X-Acquisition-Link-Rejected' not in response.headers;assert store.request.await_count==1

def test_withdrawal_is_scoped_and_nonexecuting(endpoint):
    client,store=endpoint;store.request.return_value=WITHDRAWAL
    response=client.post(PATH+'/'+I+'/withdrawals',json=WITHDRAW)
    assert response.status_code==200 and response.json()==WITHDRAWAL and response.headers['cache-control']=='no-store'
    store.request.assert_awaited_once_with('POST','rpc/revoke_contract_document_link',body=dict(p_id=R,p_workspace=W,p_contract=C,p_version=2,p_link=I,p_reason=WITHDRAW['reason']))

@pytest.mark.parametrize('change',[{'revocation_id':A},{'workspace_id':A},{'contract_id':A},{'contract_version':1},
    {'link_id':A},{'duplicate':1},{'execution_authorized':True},{'private':'secret-marker'}])
def test_withdrawal_confirmation_must_match_request(endpoint,change):
    client,store=endpoint;store.request.return_value=WITHDRAWAL|change
    response=client.post(PATH+'/'+I+'/withdrawals',json=WITHDRAW)
    assert response.status_code==503 and 'secret-marker' not in response.text and 'X-Acquisition-Link-Rejected' not in response.headers

@pytest.mark.parametrize('status',[401,403,409,503])
@pytest.mark.parametrize('withdraw',[False,True])
def test_only_definite_current_attempt_gets_rejection_marker(endpoint,status,withdraw):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Safe error')
    response=client.post(PATH+'/'+I+'/withdrawals' if withdraw else PATH,json=WITHDRAW if withdraw else BODY)
    assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert (response.headers.get('X-Acquisition-Link-Rejected')=='true')==(status in (401,403,409));assert store.request.await_count==1

def test_disabled_and_anonymous_routes_use_normal_auth_gate(monkeypatch):
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        monkeypatch.setenv('ACQUISITION_ENABLED','false');assert client.post(PATH,json=BODY).status_code==404
        monkeypatch.setenv('ACQUISITION_ENABLED','true');assert client.post(PATH,json=BODY).status_code==401

def test_first_version_and_invalid_withdrawal_never_mutate(endpoint):
    client,store=endpoint
    assert client.post(PATH.replace('/versions/2/','/versions/1/'),json=BODY).status_code==422
    assert client.post(PATH.replace('/versions/2/','/versions/1/')+'/'+I+'/withdrawals',json=WITHDRAW).status_code==422
    assert client.post(PATH+'/'+I+'/withdrawals',json=WITHDRAW|{'reason':' ' * 20}).status_code==422
    assert client.post(PATH+'/'+I+'/withdrawals',json=WITHDRAW|{'actor_id':A}).status_code==422
    store.request.assert_not_awaited()
