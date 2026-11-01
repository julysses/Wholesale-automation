"""Mounted exact execution-review transport; SQL remains the authority."""
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from schemas.acquisition_execution_review import ExecutionReviewRequest
from tests.test_acquisition_execution_review import request, UID

OTHER='af000000-0000-4000-8000-000000000002'
BASE=f'/api/acquisition/workspaces/{UID}/contracts/{UID}/versions/1/execution-review'


def receipt():
    return dict(workspace_id=UID,contract_id=UID,contract_version=1,kind='executed_contract',review_id=UID,
                sequence=1,status='approved',duplicate=False,review_recorded=True,approval_current=False,execution_authorized=False)


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_exact_historical_retry_preserves_all_findings(endpoint):
    client,store=endpoint;body=request();store.request.return_value=receipt()|{'duplicate':True}
    for _ in range(2):
        response=client.post(BASE,json=body)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['duplicate'] and not response.json()['approval_current']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    args=store.request.await_args.kwargs['body']
    assert args['p_findings']==ExecutionReviewRequest.model_validate(body).findings.model_dump(mode='json')
    assert args['p_note']==body['note'] and args['p_id']==UID
    assert store.request.await_args.args==('POST','rpc/record_execution_review')


def test_withdrawal_does_not_replace_findings(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|{'status':'withdrawn'}
    response=client.post(BASE,json=request()|{'status':'withdrawn','personally_reviewed':False,'expires_at':None,'findings':None})
    assert response.status_code==200
    assert store.request.await_args.kwargs['body']['p_findings'] is None


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'actor_id':OTHER},{'execution_sources':[]},
    {'execution_authorized':True},{'expected_version':True},{'expected_sequence':True},{'findings':None},
    {'personally_reviewed':False},{'expires_at':0}])
def test_rejects_client_authority_overrides_and_missing_findings(endpoint,change):
    client,store=endpoint
    assert client.post(BASE,json=request()|change).status_code==422
    store.request.assert_not_awaited()


def test_version_mismatch_is_definite_without_store_access(endpoint):
    client,store=endpoint
    response=client.post(BASE,json=request()|{'expected_version':2})
    assert response.status_code==409 and response.headers['x-acquisition-execution-review-rejected']=='true'
    store.request.assert_not_awaited()


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':2},{'review_id':OTHER},
    {'sequence':2},{'sequence':True},{'kind':'contract_review'},{'status':'withdrawn'},
    {'review_recorded':False},{'approval_current':True},{'execution_authorized':True},{'duplicate':'true'},
    {'private':'secret-marker'}])
def test_receipt_mismatch_is_uncertain_and_does_not_retry(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=request())
    assert response.status_code==503 and 'same request' in response.text and 'secret-marker' not in response.text
    assert 'x-acquisition-execution-review-rejected' not in response.headers
    store.request.assert_awaited_once()


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_only_definite_write_rejection_has_marker(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.post(BASE,json=request())
    assert response.status_code==status
    assert (response.headers.get('x-acquisition-execution-review-rejected')=='true')==(status in {401,403,409})
    store.request.assert_awaited_once()


def state():
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    return {key:value for key,value in receipt().items() if key not in {'duplicate','review_recorded'}}|{
        'approval_current':True,'expires_at':(now+timedelta(minutes=5)).isoformat(),'checked_at':now.isoformat()}


@pytest.mark.parametrize('status',['approved','requires_review','withdrawn','not_reviewed'])
def test_current_execution_state_holds_and_history(endpoint,status):
    client,store=endpoint;value=state()|{'status':status,'approval_current':status=='approved'}
    if status!='approved':value['expires_at']=None
    if status=='not_reviewed':value.update(review_id=None,sequence=0)
    store.request.return_value=value
    response=client.get(BASE)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['status']==status and not response.json()['execution_authorized']
    store.request.assert_awaited_once_with('POST','rpc/execution_review_state',body={
        'p_workspace':UID,'p_contract':UID,'p_version':1})


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':2},
    {'kind':'contract_review'},{'checked_at':'2020-01-01T00:00:00Z'},{'checked_at':0},
    {'expires_at':'2020-01-01T00:00:00Z'},{'expires_at':None},{'approval_current':False},
    {'execution_authorized':True},{'review_id':None},{'sequence':0},{'sequence':True},{'private':'secret-marker'}])
def test_current_execution_state_rejects_stale_mixed_or_false_authority(endpoint,change):
    client,store=endpoint;store.request.return_value=state()|change
    response=client.get(BASE)
    assert response.status_code==503 and 'secret-marker' not in response.text
    assert 'x-acquisition-execution-review-rejected' not in response.headers


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_read_errors_cannot_clear_saved_review_request(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.get(BASE)
    assert response.status_code==status and 'x-acquisition-execution-review-rejected' not in response.headers


def candidate():
    current=state()|{'status':'not_reviewed','sequence':0,'review_id':None,'approval_current':False,'expires_at':None}
    from datetime import datetime,timedelta,timezone
    return {'workspace_id':UID,'contract_id':UID,'contract_version':1,'artifact_id':UID,
        'status':'ready_for_human_review','candidate':{'artifact_id':UID,'source_version':1,'verification_id':UID,
        'sha256':'a'*64,'policy_id':UID,'expected_sequence':0,'max_expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()},
        'withdrawal':None,'prepared_terms':request()['findings']['terms'],'current_review':current,
        'checked_at':current['checked_at'],'execution_authorized':False}


CHOICE=BASE+'/documents/'+UID+'/candidate'


def test_execution_choices_exact_read_without_provisioning(endpoint):
    client,store=endpoint;store.request.return_value=candidate()
    response=client.get(CHOICE)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['candidate']['source_version']==1
    store.request.assert_awaited_once_with('POST','rpc/execution_review_candidate',body={
        'p_workspace':UID,'p_contract':UID,'p_version':1,'p_artifact':UID})
    assert client.post(CHOICE,json=request()).status_code==405


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':2},{'artifact_id':OTHER},
    {'checked_at':'2020-01-01T00:00:00Z'},{'checked_at':0},{'execution_authorized':True},
    {'status':'paused'},{'candidate':None},{'prepared_terms':None},{'private':'secret-marker'}])
def test_execution_choices_reject_wrong_scope_or_inconsistent_hold(endpoint,change):
    client,store=endpoint;store.request.return_value=candidate()|change
    response=client.get(CHOICE)
    assert response.status_code==503 and 'secret-marker' not in response.text
    assert 'x-acquisition-execution-review-rejected' not in response.headers


@pytest.mark.parametrize('change',[{'artifact_id':OTHER},{'source_version':2},{'source_version':True},
    {'expected_sequence':1},{'expected_sequence':True},{'max_expires_at':'2020-01-01T00:00:00Z'},
    {'max_expires_at':0},{'sha256':'A'*64}])
def test_execution_choices_reject_inconsistent_source_or_expiry(endpoint,change):
    client,store=endpoint;value=candidate();value['candidate'].update(change);store.request.return_value=value
    assert client.get(CHOICE).status_code==503


@pytest.mark.parametrize('status',['paused','contract_unavailable','history_limit_reached','prepared_terms_required','reviewer_policy_required','evidence_review_required'])
def test_execution_choice_hold_preserves_original_withdrawal_for_other_selected_file(endpoint,status):
    client,store=endpoint;value=candidate()
    value['current_review']=state()|{'approval_current':False,'status':'requires_review','expires_at':None,'checked_at':value['checked_at']}
    value.update(status=status,candidate=None,withdrawal={'review_id':UID,'artifact_id':OTHER,'source_version':1,
        'verification_id':OTHER,'policy_id':OTHER,'expected_sequence':1})
    store.request.return_value=value
    response=client.get(CHOICE)
    assert response.status_code==200 and response.json()['withdrawal']['artifact_id']==OTHER
    value['withdrawal']['review_id']=OTHER
    assert client.get(CHOICE).status_code==503
