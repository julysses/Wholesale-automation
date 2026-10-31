"""Draft API identity, bounded scope and uncertain-save recovery contract."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tools.acquisition_store import acquisition_store
from web.api.acquisition_contracts_api import ContractDraftRecord
from web.api.acquisition_api import router

W='10000000-0000-4000-8000-000000000001'
I='20000000-0000-4000-8000-000000000001'
J='20000000-0000-4000-8000-000000000002'
L='30000000-0000-4000-8000-000000000001'
BODY={'id':I,'offer_id':L,'offer_sequence':2,'owner_relationship_id':J,'name':'Draft review'}
RECEIPT={'deal_id':I,'version':1,'status':'draft','duplicate':False,'execution_authorized':False}
ROW={'id':I,'workspace_id':W,'lead_id':L,'deal_name':'Draft review','acquisition_status':'draft',
     'acquisition_version':1,'acquisition_property_id':J,'acquisition_owner_relationship_id':J,
     'acquisition_offer_id':L,'acquisition_offer_sequence':2,'created_by':L,'created_at':'2026-10-31T22:00:00Z'}
PATH=f'/api/acquisition/workspaces/{W}/contracts/drafts'


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router)
    app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_save_sends_exact_identity_not_client_authority(endpoint):
    client,store=endpoint;store.request.return_value=RECEIPT
    response=client.post(PATH,json=BODY)
    assert response.status_code==200 and response.json()==RECEIPT
    assert response.headers['cache-control']=='no-store'
    store.request.assert_awaited_once_with('POST','rpc/create_acquisition_contract_draft',body={
        'p_id':I,'p_workspace':W,'p_offer':L,'p_offer_sequence':2,'p_relationship':J,'p_name':'Draft review'})


@pytest.mark.parametrize('change',[{'workspace_id':J},{'approved_by':J},{'execution_authorized':True},
    {'offer_sequence':True},{'offer_sequence':0},{'offer_sequence':2147483648},{'name':'   '},{'name':'x\ncontrol'},
    {'contract_status':'executed'},{'buyer_id':J},{'contract_price':100},{'name':4}])
def test_invalid_assertions_never_reach_storage(endpoint,change):
    client,store=endpoint
    assert client.post(PATH,json=BODY|change).status_code==422
    store.request.assert_not_awaited()


@pytest.mark.parametrize('change',[{'deal_id':J},{'version':2},{'version':True},{'status':'executed'},
    {'duplicate':'false'},{'execution_authorized':True},{'execution_authorized':0},{'secret':'private-marker'}])
def test_uncertain_or_unexpected_receipt_requires_same_request(endpoint,change):
    client,store=endpoint;store.request.return_value=RECEIPT|change
    response=client.post(PATH,json=BODY)
    assert response.status_code==503 and 'same saved request' in response.text
    assert 'private-marker' not in response.text and response.headers['cache-control']=='no-store'
    assert store.request.await_count==1


def test_duplicate_receipt_is_recovery_not_execution(endpoint):
    client,store=endpoint;store.request.return_value=RECEIPT|{'duplicate':True}
    response=client.post(PATH,json=BODY)
    assert response.json()['duplicate'] is True and response.json()['execution_authorized'] is False


def test_list_filters_and_pagination(endpoint):
    client,store=endpoint;store.request.return_value=[ROW,ROW|{'id':J}]
    response=client.get(PATH,params={'lead_id':L,'limit':1})
    assert response.status_code==200 and response.json()['next_after']==I
    assert len(response.json()['items'])==1 and response.json()['execution_authorized'] is False
    assert store.request.call_args.kwargs['params']=={'select':','.join(ContractDraftRecord.model_fields),
        'workspace_id':'eq.'+W,'lead_id':'eq.'+L,'acquisition_status':'eq.draft','order':'id','limit':'2'}
    store.request.return_value=[ROW|{'id':J}]
    assert client.get(PATH,params={'after':I}).json()['next_after'] is None
    assert store.request.call_args.kwargs['params']['id']=='gt.'+I


@pytest.mark.parametrize('rows',[[ROW|{'workspace_id':J}],[ROW,ROW],[ROW|{'acquisition_version':True}],
    [ROW|{'acquisition_status':'executed'}],[ROW|{'secret':'private-marker'}],None,{'items':[]}])
def test_read_rejects_wrong_scope_or_malformed_page(endpoint,rows):
    client,store=endpoint;store.request.return_value=deepcopy(rows)
    response=client.get(PATH)
    assert response.status_code==503 and 'private-marker' not in response.text
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('status',[401,403,409,503])
def test_storage_errors_remain_private_noncacheable_and_not_retried(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Safe error')
    response=client.post(PATH,json=BODY)
    assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert store.request.await_count==1


def test_feature_disabled_without_opening_store(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED','false')
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.post(PATH,json=BODY).status_code==404
        assert client.get(PATH).status_code==404


SELLER={'id':I,'workspace_id':W,'lead_id':L,'property_id':J,'owner_id':L,
        'relationship':'reported_owner','verification_status':'unverified','seller':{'display_name':'Synthetic Seller'}}


def test_seller_choices_keep_property_scope_and_unverified_status(endpoint):
    client,store=endpoint;store.request.return_value=[SELLER]
    response=client.get(PATH+'/sellers',params={'lead_id':L,'property_id':J})
    assert response.status_code==200 and response.json()['items']==[SELLER]
    assert response.json()['ownership_verified'] is False
    assert response.json()['execution_authorized'] is False
    assert response.headers['cache-control']=='no-store'
    params=store.request.call_args.kwargs['params']
    assert params['workspace_id']=='eq.'+W and params['lead_id']=='eq.'+L and params['property_id']=='eq.'+J
    assert 'seller:acquisition_owners(display_name)' in params['select']
    assert 'source_evidence' not in params['select']


@pytest.mark.parametrize('change',[{'workspace_id':J},{'lead_id':J},{'property_id':I},
    {'seller':None},{'seller':{'display_name':' '}},{'seller':{'display_name':'Name','private_note':'secret'}},
    {'verification_status':'verified'},{'relationship':'legal_title_holder'}])
def test_seller_choices_reject_scope_drift_or_title_claim(endpoint,change):
    client,store=endpoint;store.request.return_value=[SELLER|change]
    response=client.get(PATH+'/sellers',params={'lead_id':L,'property_id':J})
    assert response.status_code==503 and 'secret' not in response.text


def test_seller_choices_require_property_and_bound_page(endpoint):
    client,store=endpoint
    assert client.get(PATH+'/sellers',params={'lead_id':L}).status_code==422
    assert client.get(PATH+'/sellers',params={'lead_id':L,'property_id':J,'limit':51}).status_code==422
    store.request.assert_not_awaited()
    store.request.return_value=[SELLER,SELLER|{'id':J}]
    response=client.get(PATH+'/sellers',params={'lead_id':L,'property_id':J,'limit':1})
    assert response.json()['next_after']==I and len(response.json()['items'])==1
    store.request.return_value=[]
    response=client.get(PATH+'/sellers',params={'lead_id':L,'property_id':J,'after':I})
    assert response.json()['items']==[] and response.json()['next_after'] is None
    assert store.request.call_args.kwargs['params']['id']=='gt.'+I
