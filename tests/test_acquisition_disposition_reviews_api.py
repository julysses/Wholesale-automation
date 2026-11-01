"""Mounted exact disposition-review transport; SQL remains the authority."""
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from schemas.acquisition_disposition_review import DispositionReviewRequest
from tests.test_acquisition_disposition_review import request, ID as UID, OTHER as REVIEW_ID

OTHER='af000000-0000-4000-8000-000000000002'
BASE=f'/api/acquisition/workspaces/{UID}/contracts/{UID}/versions/2/disposition-review'


def receipt():
    return dict(workspace_id=UID,contract_id=UID,contract_version=2,kind='disposition_findings',review_id=REVIEW_ID,
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
    assert args['p_findings']==DispositionReviewRequest.model_validate(body).findings.model_dump(mode='json')
    assert args['p_note']==body['note'] and args['p_id']==REVIEW_ID
    assert store.request.await_args.args==('POST','rpc/record_disposition_review')


def test_withdrawal_does_not_replace_findings(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|{'status':'withdrawn','sequence':2}
    response=client.post(BASE,json=request()|{'status':'withdrawn','expected_sequence':1,'original_review_id':UID,'personally_reviewed':False,'expires_at':None,'findings':None})
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
    response=client.post(BASE,json=request()|{'expected_version':3})
    assert response.status_code==409 and response.headers['x-acquisition-disposition-review-rejected']=='true'
    assert response.headers['cache-control']=='no-store'
    store.request.assert_not_awaited()


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':3},{'review_id':UID},
    {'sequence':2},{'sequence':True},{'kind':'contract_review'},{'status':'withdrawn'},
    {'review_recorded':False},{'approval_current':True},{'execution_authorized':True},{'duplicate':'true'},
    {'private':'secret-marker'}])
def test_receipt_mismatch_is_uncertain_and_does_not_retry(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=request())
    assert response.status_code==503 and 'same request' in response.text and 'secret-marker' not in response.text
    assert 'x-acquisition-disposition-review-rejected' not in response.headers
    store.request.assert_awaited_once()


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_only_definite_write_rejection_has_marker(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.post(BASE,json=request())
    assert response.status_code==status
    assert (response.headers.get('x-acquisition-disposition-review-rejected')=='true')==(status in {401,403,409})
    store.request.assert_awaited_once()


def state():
    from datetime import datetime, timedelta, timezone
    now=datetime.now(timezone.utc)
    return {key:value for key,value in receipt().items() if key not in {'duplicate','review_recorded'}}|{
        'approval_current':True,'expires_at':(now+timedelta(minutes=5)).isoformat(),'checked_at':now.isoformat()}


@pytest.mark.parametrize('status',['approved','requires_resolution','requires_review','withdrawn','not_reviewed'])
def test_current_execution_state_holds_and_history(endpoint,status):
    client,store=endpoint;value=state()|{'status':status,'approval_current':status=='approved'}
    if status!='approved':value['expires_at']=None
    if status=='not_reviewed':value.update(review_id=None,sequence=0)
    store.request.return_value=value
    response=client.get(BASE)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['status']==status and not response.json()['execution_authorized']
    store.request.assert_awaited_once_with('POST','rpc/disposition_review_state',body={
        'p_workspace':UID,'p_contract':UID,'p_version':2})


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':3},
    {'kind':'contract_review'},{'checked_at':'2020-01-01T00:00:00Z'},{'checked_at':0},
    {'expires_at':'2020-01-01T00:00:00Z'},{'expires_at':None},{'approval_current':False},
    {'execution_authorized':True},{'review_id':None},{'sequence':0},{'sequence':True},{'private':'secret-marker'}])
def test_current_execution_state_rejects_stale_mixed_or_false_authority(endpoint,change):
    client,store=endpoint;store.request.return_value=state()|change
    response=client.get(BASE)
    assert response.status_code==503 and 'secret-marker' not in response.text
    assert 'x-acquisition-disposition-review-rejected' not in response.headers


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_read_errors_cannot_clear_saved_review_request(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.get(BASE)
    assert response.status_code==status and 'x-acquisition-disposition-review-rejected' not in response.headers



def test_explicit_resolution_hold_preserves_required_action_without_expiry(endpoint):
    client,store=endpoint;body=request();body.update(status='requires_resolution',expires_at=None)
    body['findings']['remaining_obligations'].update(finding='unknown',sources=[],required_action='Obtain the original payoff statement and reconcile the lien.')
    store.request.return_value=receipt()|{'status':'requires_resolution'}
    response=client.post(BASE,json=body)
    assert response.status_code==200 and response.json()['status']=='requires_resolution'
    args=store.request.await_args.kwargs['body']
    assert args['p_expires'] is None and args['p_findings']['remaining_obligations']['required_action']==body['findings']['remaining_obligations']['required_action']


@pytest.mark.parametrize('offset,expected',[(-31,503),(-30,200),(5,200),(6,503)])
def test_disposition_state_request_time_boundaries(endpoint,monkeypatch,offset,expected):
    from datetime import datetime,timedelta,timezone
    from web.api import acquisition_disposition_reviews_api as api
    now=datetime(2026,11,1,12,tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(api,'datetime',Clock)
    client,store=endpoint
    store.request.return_value=state()|dict(checked_at=(now+timedelta(seconds=offset)).isoformat(),expires_at=(now+timedelta(minutes=5)).isoformat())
    result=client.get(BASE)
    assert result.status_code==expected and 'x-acquisition-disposition-review-rejected' not in result.headers


def test_assignment_request_preserves_original_plan_and_all_legal_findings(endpoint):
    client,store=endpoint;body=request(True);store.request.return_value=receipt()
    assert client.post(BASE,json=body).status_code==200
    sent=store.request.await_args.kwargs['body']
    assert sent['p_plan']==body['plan_id'] and sent['p_original_review'] is None
    assert sent['p_findings']==body['findings']
    assert not {'p_execution','p_title','p_actor','p_legal_source'} & sent.keys()


def test_original_withdrawal_selector_is_retained(endpoint):
    client,store=endpoint;store.request.return_value=receipt()|dict(sequence=2,status='withdrawn')
    body=request()|dict(status='withdrawn',expected_sequence=1,original_review_id=UID,personally_reviewed=False,expires_at=None,findings=None)
    assert client.post(BASE,json=body).status_code==200
    sent=store.request.await_args.kwargs['body']
    assert sent['p_original_review']==UID and sent['p_plan']==body['plan_id']
    assert sent['p_expires'] is None and sent['p_findings'] is None
