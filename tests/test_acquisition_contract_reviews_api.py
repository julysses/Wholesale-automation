"""Mounted review transport rejects wrong scope/false authority and preserves exact retries."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router

uid=lambda n:f'00000000-0000-4000-8000-{n:012d}'
W,C,R,A,V,P=[uid(n) for n in range(1,7)]
BASE=f'/api/acquisition/workspaces/{W}/contracts/{C}/versions/1/reviews/contract_review'
def stamp(seconds=0): return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()
def body(): return {'id':R,'expected_sequence':0,'status':'approved','artifact_id':A,'verification_id':V,
    'policy_id':P,'expires_at':stamp(300),'personally_reviewed':True,'note':'Personally reviewed this exact synthetic document.'}
def receipt(): return {'workspace_id':W,'contract_id':C,'contract_version':1,'kind':'contract_review','review_id':R,
    'sequence':1,'status':'approved','duplicate':False,'review_recorded':True,'approval_current':False,'execution_authorized':False}
def state(): return {k:v for k,v in receipt().items() if k not in {'duplicate','review_recorded'}}|{'approval_current':True,'expires_at':stamp(300),'checked_at':stamp()}

@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_save_exact_input_and_historical_retry(endpoint):
    client,store=endpoint;request=body()|{'expires_at':stamp(-60)}
    store.request.return_value=receipt()|{'duplicate':True}
    for _ in range(2):
        response=client.post(BASE,json=request)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['duplicate'] and not response.json()['approval_current']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    args=store.request.await_args.kwargs['body']
    assert args=={'p_id':R,'p_workspace':W,'p_contract':C,'p_version':1,'p_kind':'contract_review',
        'p_expected_sequence':0,'p_status':'approved','p_artifact':A,'p_verification':V,'p_policy':P,
        'p_expires':request['expires_at'],'p_personally_reviewed':True,'p_note':request['note']}


def test_withdrawal_does_not_renew_authority(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|{'status':'withdrawn'}
    response=client.post(BASE,json=body()|{'status':'withdrawn','personally_reviewed':False,'expires_at':None})
    assert response.status_code==200 and not response.json()['approval_current']

@pytest.mark.parametrize('change',[{'workspace_id':P},{'actor_id':P},{'execution_authorized':True},
    {'expected_sequence':True},{'expected_sequence':-1},{'expected_sequence':2147483647},
    {'personally_reviewed':False},{'personally_reviewed':'true'},{'expires_at':None},{'expires_at':123},
    {'note':' '*30},{'status':'executed'},{'status':'withdrawn'}])
def test_client_assertions_fail_before_database(endpoint,change):
    client,store=endpoint
    assert client.post(BASE,json=body()|change).status_code==422
    store.request.assert_not_awaited()

@pytest.mark.parametrize('change',[{'workspace_id':P},{'contract_id':P},{'contract_version':2},{'kind':'title_review'},
    {'review_id':P},{'sequence':2},{'sequence':True},{'status':'withdrawn'},{'review_recorded':False},
    {'approval_current':True},{'execution_authorized':True},{'duplicate':'true'},{'private':'secret-marker'}])
def test_bad_receipt_is_uncertain_and_not_retried(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=body())
    assert response.status_code==503 and response.headers['cache-control']=='no-store'
    assert 'same request' in response.text and 'secret-marker' not in response.text
    assert store.request.await_count==1

@pytest.mark.parametrize('status',['approved','requires_review','withdrawn','not_reviewed'])
def test_current_state_and_historical_holds(endpoint,status):
    client,store=endpoint;value=state()|{'status':status,'approval_current':status=='approved'}
    if status!='approved':value['expires_at']=None
    if status=='not_reviewed':value.update(review_id=None,sequence=0)
    store.request.return_value=value
    response=client.get(BASE)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['approval_current']==(status=='approved')
    store.request.assert_awaited_once_with('POST','rpc/contract_review_state',body={
        'p_workspace':W,'p_contract':C,'p_version':1,'p_kind':'contract_review'})

@pytest.mark.parametrize('change',[{'workspace_id':P},{'contract_id':P},{'contract_version':2},{'kind':'title_review'},
    {'checked_at':stamp(-60)},{'checked_at':stamp(60)},{'checked_at':0},{'expires_at':stamp(-1)},
    {'expires_at':None},{'approval_current':False},{'execution_authorized':True},{'review_id':None},
    {'sequence':0},{'sequence':True},{'status':'withdrawn'},{'private':'secret-marker'}])
def test_stale_or_inconsistent_current_state_is_hidden(endpoint,change):
    client,store=endpoint;store.request.return_value=state()|change
    response=client.get(BASE)
    assert response.status_code==503 and 'secret-marker' not in response.text

@pytest.mark.parametrize('status',[401,403,409,429,503])
@pytest.mark.parametrize('method',['get','post'])
def test_authorization_and_unavailable_errors_preserved(endpoint,status,method):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=getattr(client,method)(BASE,**({'json':body()} if method=='post' else {}))
    assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert store.request.await_count==1

@pytest.mark.parametrize('path',[BASE.replace('/versions/1/','/versions/0/'),BASE.replace('contract_review','approved')])
def test_invalid_scope_never_calls_database(endpoint,path):
    client,store=endpoint
    assert client.get(path).status_code==422
    store.request.assert_not_awaited()


def candidate():
    current=state()|{'status':'not_reviewed','sequence':0,'review_id':None,'approval_current':False,'expires_at':None}
    return {'workspace_id':W,'contract_id':C,'contract_version':1,'kind':'contract_review','artifact_id':A,'purpose':'purchase_contract',
        'status':'ready_for_human_review','candidate':{'artifact_id':A,'verification_id':V,'sha256':'a'*64,'policy_id':P,'expected_sequence':0,'max_expires_at':stamp(300)},
        'withdrawal':None,'current_review':current,'checked_at':current['checked_at'],'execution_authorized':False}


def test_candidate_exact_path_and_no_mutation(endpoint):
    client,store=endpoint;store.request.return_value=candidate()
    response=client.get(BASE+'/documents/'+A+'/candidate')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['candidate']['artifact_id']==A and not response.json()['execution_authorized']
    store.request.assert_awaited_once_with('POST','rpc/contract_review_candidate',body={'p_workspace':W,'p_contract':C,'p_version':1,'p_kind':'contract_review','p_artifact':A})
    assert client.post(BASE+'/documents/'+A+'/candidate',json=body()).status_code==405

@pytest.mark.parametrize('change',[{'workspace_id':P},{'contract_id':P},{'contract_version':2},{'kind':'title_review'},
    {'artifact_id':P},{'purpose':'title_report'},{'status':'paused'},{'candidate':None},{'execution_authorized':True},
    {'checked_at':stamp(-60)},{'checked_at':stamp(60)},{'private':'secret-marker'}])
def test_candidate_rejects_mixed_stale_or_unexpected_data(endpoint,change):
    client,store=endpoint;store.request.return_value=candidate()|change
    response=client.get(BASE+'/documents/'+A+'/candidate')
    assert response.status_code==503 and 'secret-marker' not in response.text

@pytest.mark.parametrize('change',[{'artifact_id':P},{'expected_sequence':1},{'expected_sequence':True},
    {'max_expires_at':stamp(-1)},{'max_expires_at':stamp(86410)},{'max_expires_at':123},{'sha256':'B'*64}])
def test_candidate_rejects_invalid_approval_choice(endpoint,change):
    client,store=endpoint;value=candidate();value['candidate'].update(change);store.request.return_value=value
    assert client.get(BASE+'/documents/'+A+'/candidate').status_code==503

@pytest.mark.parametrize('status',['paused','contract_unavailable','reviewer_policy_required','evidence_review_required'])
def test_candidate_preserves_holds_and_exact_withdrawal(endpoint,status):
    client,store=endpoint;value=candidate();current=state()|{'status':'requires_review','approval_current':False,'expires_at':None,'checked_at':value['checked_at']}
    value.update(status=status,candidate=None,current_review=current,withdrawal={'review_id':R,'artifact_id':A,'verification_id':V,'policy_id':P,'expected_sequence':1})
    store.request.return_value=value
    response=client.get(BASE+'/documents/'+A+'/candidate')
    assert response.status_code==200 and response.json()['withdrawal']['review_id']==R
    value['withdrawal']['review_id']=P
    assert client.get(BASE+'/documents/'+A+'/candidate').status_code==503

@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_review_rejection_marker_only_reports_definitive_attempt(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.post(BASE,json=body())
    assert (response.headers.get('x-acquisition-review-rejected')=='true') == (status in {401,403,409})


def test_invalid_receipt_is_never_marked_as_rejected(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|{'approval_current':True}
    response=client.post(BASE,json=body())
    assert response.status_code==503 and 'x-acquisition-review-rejected' not in response.headers
