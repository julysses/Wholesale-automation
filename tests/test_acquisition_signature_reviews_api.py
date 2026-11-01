"""Mounted signature-review route preserves exact requests and denies false authority."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router

W,C,R,B,P=[f'00000000-0000-4000-8000-{n:012d}' for n in range(1,6)]
BASE=f'/api/acquisition/workspaces/{W}/contracts/{C}/versions/2/signature-review'
def stamp(seconds=0):return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
def body():return dict(id=R,expected_sequence=0,status='approved',basis_review_id=B,policy_id=P,
    expires_at=stamp(300),personally_reviewed=True,note='  Personally reviewed this exact synthetic contract for release.  ')
def receipt():return dict(workspace_id=W,contract_id=C,contract_version=2,review_id=R,sequence=1,
    status='approved',duplicate=False,review_recorded=True,approval_current=False,execution_authorized=False)
def state():return {k:v for k,v in receipt().items() if k not in {'duplicate','review_recorded'}} | dict(
    basis_review_id=B,approval_current=True,expires_at=stamp(300),checked_at=stamp())

@pytest.fixture
def endpoint():
    store=AsyncMock(); app=FastAPI(); app.include_router(router)
    app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_exact_expired_historical_retry_preserves_note_and_basis(endpoint):
    client,store=endpoint; request=body()|{'expires_at':stamp(-60)}
    store.request.return_value=receipt()|{'duplicate':True}
    for _ in range(2):
        response=client.post(BASE,json=request)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['duplicate'] and not response.json()['approval_current']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    assert store.request.await_args.kwargs['body']==dict(p_id=R,p_workspace=W,p_contract=C,p_version=2,
        p_expected_sequence=0,p_status='approved',p_basis=B,p_policy=P,p_expires=request['expires_at'],
        p_personally_reviewed=True,p_note=request['note'])


def test_withdrawal_never_renews_approval(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|{'status':'withdrawn'}
    response=client.post(BASE,json=body()|dict(status='withdrawn',expires_at=None,personally_reviewed=False))
    assert response.status_code==200 and not response.json()['approval_current']


@pytest.mark.parametrize('change',[{'workspace_id':P},{'actor_id':P},{'execution_authorized':True},
    {'artifact_id':B},{'expected_sequence':True},{'expected_sequence':2147483647},{'expected_sequence':-1},
    {'personally_reviewed':False},{'personally_reviewed':'true'},{'expires_at':None},{'expires_at':123},
    {'expires_at':'2026-10-31T12:00:00'},{'expires_at':'1790000000'},{'note':' '*40},{'note':'Long enough note with NUL\x00'},
    {'status':'executed'},{'status':'withdrawn'},{'basis_review_id':'invalid'}])
def test_untrusted_assertions_rejected_before_database(endpoint,change):
    client,store=endpoint
    assert client.post(BASE,json=body()|change).status_code==422
    store.request.assert_not_awaited()


@pytest.mark.parametrize('change',[{'workspace_id':P},{'contract_id':P},{'contract_version':1},
    {'review_id':P},{'sequence':2},{'sequence':True},{'status':'withdrawn'},
    {'review_recorded':False},{'approval_current':True},{'execution_authorized':True},
    {'duplicate':'true'},{'private':'secret-marker'}])
def test_malformed_save_receipt_stays_uncertain_without_retry(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=body())
    assert response.status_code==503 and response.headers['cache-control']=='no-store'
    assert 'same request' in response.text and 'secret-marker' not in response.text
    assert 'X-Acquisition-Signature-Rejected' not in response.headers
    store.request.assert_awaited_once()


@pytest.mark.parametrize('status',['not_reviewed','approved','withdrawn','requires_review'])
def test_current_state_preserves_exact_underlying_review(endpoint,status):
    client,store=endpoint;value=state()|dict(status=status,approval_current=status=='approved')
    if status!='approved':value['expires_at']=None
    if status=='not_reviewed':value.update(review_id=None,basis_review_id=None,sequence=0)
    store.request.return_value=value;response=client.get(BASE)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['basis_review_id']==value['basis_review_id']
    store.request.assert_awaited_once_with('POST','rpc/signature_review_state',body=dict(p_workspace=W,p_contract=C,p_version=2))


@pytest.mark.parametrize('change',[{'workspace_id':P},{'contract_id':P},{'contract_version':1},
    {'checked_at':lambda:stamp(-60)},{'checked_at':lambda:stamp(60)},{'checked_at':123},{'checked_at':'1790000000'},
    {'expires_at':lambda:stamp(-1)},{'expires_at':None},{'basis_review_id':None},
    {'review_id':None},{'sequence':0},{'approval_current':False},{'status':'withdrawn'},
    {'execution_authorized':True},{'private':'secret-marker'}])
def test_stale_or_inconsistent_read_hidden(endpoint,change):
    client,store=endpoint
    store.request.return_value=state()|{k:v() if callable(v) else v for k,v in change.items()}
    response=client.get(BASE)
    assert response.status_code==503 and 'secret-marker' not in response.text


@pytest.mark.parametrize('status',[401,403,409,429,503])
@pytest.mark.parametrize('method',['get','post'])
def test_only_definitive_write_denial_receives_rejection_marker(endpoint,status,method):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=getattr(client,method)(BASE,**({'json':body()} if method=='post' else {}))
    assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert (response.headers.get('X-Acquisition-Signature-Rejected')=='true')==(method=='post' and status in {401,403,409})
    store.request.assert_awaited_once()


@pytest.mark.parametrize('path',[BASE.replace('/versions/2/','/versions/0/'),
    BASE.replace('/versions/2/','/versions/2147483648/'), BASE.replace(W,'invalid')])
def test_invalid_scope_never_calls_database(endpoint,path):
    client,store=endpoint
    assert client.get(path).status_code==422
    store.request.assert_not_awaited()
