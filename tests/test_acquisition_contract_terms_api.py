"""Mounted sourced terms API scope, exact receipt and bounded immutable history."""
from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from schemas.acquisition_contract_terms import ContractTermsDraft
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from web.api.acquisition_contract_terms_api import ContractVersionRecord

W='10000000-0000-4000-8000-000000000001'
C='20000000-0000-4000-8000-000000000001'
I='20000000-0000-4000-8000-000000000002'
J='20000000-0000-4000-8000-000000000003'
PATH=f'/api/acquisition/workspaces/{W}/contracts/{C}'
TERMS={'purchase_price_cents':None,'earnest_money_cents':0,'assignment_allowed':None,'assignment_provisions':None,
       'effective':{'precision':'date','calendar_date':'2026-11-01'},'inspection_deadline':{'precision':'unknown'},
       'closing_deadline':{'precision':'unknown'}, 'note':'Synthetic clauses prepared for human review.',
       'sources':[{'term':name,'artifact_id':J,'artifact_version':1,'sha256':'a'*64,'locator':'Clause 1'} for name in ('earnest_money','effective')]}
BODY={'id':I,'expected_version':1,'terms':TERMS}
RECEIPT={'request_id':I,'workspace_id':W,'contract_id':C,'version':2,'status':'draft','duplicate':False,'execution_authorized':False}
ROW={'id':I,'workspace_id':W,'deal_id':C,'version':2,'status':'draft','previous_version':1,
     'terms':ContractTermsDraft.model_validate(TERMS).model_dump(mode='json'),'actor_id':J,'created_at':'2026-11-01T00:00:00Z'}
FIRST=ROW|{'id':C,'version':1,'previous_version':None,'terms':None}

@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_save_preserves_null_zero_date_precision_and_exact_scope(endpoint):
    client,store=endpoint;store.request.return_value=RECEIPT
    result=client.post(PATH+'/terms',json=BODY)
    assert result.status_code==200 and result.json()==RECEIPT and result.headers['cache-control']=='no-store'
    store.request.assert_awaited_once_with('POST','rpc/save_contract_terms',body={'p_id':I,'p_workspace':W,'p_contract':C,
        'p_expected_version':1,'p_terms':ROW['terms']})
    store.request.return_value=RECEIPT|{'duplicate':True}
    assert client.post(PATH+'/terms',json=BODY).json()['duplicate']

@pytest.mark.parametrize('change',[{'workspace_id':J},{'approved_by':J},{'expected_version':True},{'expected_version':0},
    {'expected_version':2147483647},{'execution_authorized':True},{'terms':TERMS|{'purchase_price_cents':0}},
    {'terms':TERMS|{'sources':[]}},{'terms':TERMS|{'effective':{'precision':'date','calendar_date':'2026-02-30'}}}])
def test_invalid_write_never_reaches_store(endpoint,change):
    client,store=endpoint;assert client.post(PATH+'/terms',json=BODY|change).status_code==422
    store.request.assert_not_awaited()

@pytest.mark.parametrize('change',[{'request_id':J},{'workspace_id':J},{'contract_id':J},{'version':1},{'version':3},
    {'version':True},{'status':'executed'},{'duplicate':'true'},{'execution_authorized':True},{'private':'secret-marker'}])
def test_uncertain_receipt_keeps_original_request(endpoint,change):
    client,store=endpoint;store.request.return_value=RECEIPT|change
    result=client.post(PATH+'/terms',json=BODY)
    assert result.status_code==503 and 'same saved request' in result.text and 'secret-marker' not in result.text
    assert result.headers['cache-control']=='no-store' and 'X-Acquisition-Terms-Rejected' not in result.headers
    assert store.request.await_count==1

@pytest.mark.parametrize('status',[401,403,409,503])
def test_rejection_marker_only_definite_write_failure(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Safe rejection')
    result=client.post(PATH+'/terms',json=BODY)
    assert result.status_code==status and result.headers['cache-control']=='no-store'
    assert (result.headers.get('X-Acquisition-Terms-Rejected')=='true') == (status in (401,403,409))
    store.request.side_effect=HTTPException(status,'Safe rejection')
    read=client.get(PATH+'/versions')
    assert read.status_code==status and 'X-Acquisition-Terms-Rejected' not in read.headers


def test_history_is_scoped_bounded_and_excludes_requests_sessions(endpoint):
    client,store=endpoint;store.request.return_value=[FIRST,ROW]
    result=client.get(PATH+'/versions',params={'limit':1})
    assert result.status_code==200 and result.json()=={'workspace_id':W,'contract_id':C,'items':[FIRST],'next_after':1,'execution_authorized':False}
    assert result.headers['cache-control']=='no-store'
    params=store.request.call_args.kwargs['params']
    assert params=={'select':','.join(ContractVersionRecord.model_fields),'workspace_id':'eq.'+W,'deal_id':'eq.'+C,'order':'version','limit':'2'}
    assert 'session_id' not in params['select'] and 'request' not in params['select']
    store.request.return_value=[ROW]
    result=client.get(PATH+'/versions',params={'after':1})
    assert result.json()['items']==[ROW] and result.json()['next_after'] is None
    assert store.request.call_args.kwargs['params']['version']=='gt.1'

@pytest.mark.parametrize('rows',[None,{},[ROW,ROW],[ROW,FIRST],[ROW|{'workspace_id':J}],
    [ROW|{'deal_id':J}],[ROW|{'previous_version':None}],[ROW|{'terms':None}],
    [FIRST|{'terms':TERMS}],[ROW|{'status':'executed'}],[ROW|{'private':'secret-marker'}]])
def test_unconfirmed_history_is_not_exposed(endpoint,rows):
    client,store=endpoint;store.request.return_value=deepcopy(rows)
    result=client.get(PATH+'/versions')
    assert result.status_code==503 and 'secret-marker' not in result.text and result.headers['cache-control']=='no-store'

@pytest.mark.parametrize('query',[{'after':0},{'after':2147483648},{'limit':0},{'limit':51}])
def test_history_bounds(endpoint,query):
    client,store=endpoint;assert client.get(PATH+'/versions',params=query).status_code==422;store.request.assert_not_awaited()


def test_history_cursor_and_source_version_must_match(endpoint):
    client,store=endpoint;store.request.return_value=[ROW]
    assert client.get(PATH+'/versions',params={'after':2}).status_code==503
    row=deepcopy(ROW);row['terms']['sources'][0]['artifact_version']=2;store.request.return_value=[row]
    assert client.get(PATH+'/versions').status_code==503


def test_disabled_feature_remains_unavailable(monkeypatch):
    monkeypatch.setenv('ACQUISITION_ENABLED','false');app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        assert client.post(PATH+'/terms',json=BODY).status_code==404
        assert client.get(PATH+'/versions').status_code==404
