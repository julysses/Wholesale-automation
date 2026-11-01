"""Reference discovery rejects wrong source, authority, freshness and page identity."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
W='10000000-0000-4000-8000-000000000001';C='20000000-0000-4000-8000-000000000001'
A='30000000-0000-4000-8000-000000000001';B='30000000-0000-4000-8000-000000000002'
PATH=f'/api/acquisition/workspaces/{W}/contracts/{C}/versions/2/references'
def stamp(seconds=0):return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
def page():
    now=stamp()
    return dict(workspace_id=W,contract_id=C,contract_version=2,purpose='purchase_contract',next_after=None,checked_at=now,execution_authorized=False,
        items=[dict(workspace_id=W,contract_id=C,contract_version=2,artifact_id=A,source_version=1,reference_type='term_source',link_id=None,
                    status='available_for_review',purpose='purchase_contract',sha256='a'*64,verification_id=B,source_created_at=stamp(-60),checked_at=now,
                    review_approved=False,execution_authorized=False)])
@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store

def test_original_source_page_is_scoped_noncacheable_and_bounded(endpoint):
    client,store=endpoint;value=page();store.request.return_value=value
    response=client.get(PATH,params={'purpose':'purchase_contract','limit':1})
    assert response.status_code==200 and response.json()['items'][0]['source_version']==1
    assert response.headers['cache-control']=='no-store' and not response.json()['execution_authorized']
    store.request.assert_awaited_once_with('POST','rpc/contract_reference_candidates',body={'p_workspace':W,'p_contract':C,'p_version':2,'p_purpose':'purchase_contract','p_after':None,'p_limit':1})
    value['next_after']=A;store.request.return_value=value
    assert client.get(PATH,params={'purpose':'purchase_contract','limit':1}).status_code==200
    assert client.get(PATH,params={'purpose':'purchase_contract','after':A}).status_code==503

@pytest.mark.parametrize('change',[{'workspace_id':B},{'contract_id':B},{'contract_version':1},{'source_version':3},
    {'reference_type':'native'},{'link_id':B},{'status':'reference_withdrawn'},{'verification_id':None},
    {'review_approved':True},{'execution_authorized':True},{'sha256':'invalid'},{'secret':'secret-marker'},{'checked_at':'2000-01-01T00:00:00Z'}])
def test_malformed_or_foreign_reference_is_not_exposed(endpoint,change):
    client,store=endpoint;value=page();value['items'][0].update(change);store.request.return_value=value
    response=client.get(PATH,params={'purpose':'purchase_contract'})
    assert response.status_code==503 and 'secret-marker' not in response.text and response.headers['cache-control']=='no-store'

@pytest.mark.parametrize('change',[lambda v:v.update(workspace_id=B),lambda v:v.update(purpose='title_report'),
    lambda v:v.update(execution_authorized=True),lambda v:v.update(next_after=B),
    lambda v:v.update(items=v['items']*2),lambda v:v.update(checked_at=stamp(-40)),
    lambda v:v.update(checked_at=stamp(10))])
def test_invalid_page_denied(endpoint,change):
    client,store=endpoint;value=page();change(value);store.request.return_value=value
    assert client.get(PATH,params={'purpose':'purchase_contract'}).status_code==503

@pytest.mark.parametrize('status',[401,403,409,503])
def test_database_error_noncacheable_without_retry(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Safe error')
    response=client.get(PATH,params={'purpose':'purchase_contract'})
    assert response.status_code==status and response.headers['cache-control']=='no-store';assert store.request.await_count==1

@pytest.mark.parametrize('params',[{}, {'purpose':'bogus'},{'purpose':'purchase_contract','limit':51},{'purpose':'purchase_contract','limit':0}])
def test_invalid_query_never_reaches_storage(endpoint,params):
    client,store=endpoint;assert client.get(PATH,params=params).status_code==422;store.request.assert_not_awaited()

def test_single_reference_and_withdrawn_history(endpoint):
    client,store=endpoint;row=page()['items'][0];row.pop('source_created_at');store.request.return_value=row
    assert client.get(PATH+'/'+A).status_code==200
    assert client.get(PATH+'/'+B).status_code==503
    store.request.return_value=row|{'reference_type':'linked','link_id':B,'status':'reference_withdrawn','verification_id':None}
    response=client.get(PATH+'/'+A)
    assert response.status_code==200 and not response.json()['review_approved']

def test_disabled_feature(endpoint,monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED','false');app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.get(PATH,params={'purpose':'purchase_contract'}).status_code==404
