"""Mounted deadline-review transport retains exact historical recovery context."""
from uuid import UUID
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from schemas.acquisition_deadline_resolution import DeadlineResolutionReviewRequest
from tests.test_acquisition_deadline_resolution import review_body

WORKSPACE=str(UUID(int=10));CONTRACT=str(UUID(int=11));OTHER=str(UUID(int=12))
BASE=f'/api/acquisition/workspaces/{WORKSPACE}/contracts/{CONTRACT}/versions/2/deadline-reviews'


def receipt(body=None):
    body=review_body() if body is None else body
    return dict(workspace_id=WORKSPACE,contract_id=CONTRACT,contract_version=2,kind='deadline_resolution',
        review_id=body['id'],sequence=body['expected_sequence']+1,status=body['status'],duplicate=False,
        review_recorded=True,approval_current=False,execution_authorized=False,term=body['term'],
        interpretation_review_id=body['original_review_id'] or body['id'])


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_exact_historical_replay_preserves_interpretation_and_source(endpoint):
    client,store=endpoint;body=review_body();store.request.return_value=receipt()|{'duplicate':True}
    for _ in range(2):
        response=client.post(BASE,json=body)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['duplicate'] and not response.json()['approval_current']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    args=store.request.await_args.kwargs['body']
    assert args['p_resolution']==DeadlineResolutionReviewRequest.model_validate(body).resolution.model_dump(mode='json')
    assert args['p_workspace']==WORKSPACE and args['p_contract']==CONTRACT
    assert args['p_term']==body['term'] and args['p_original'] is None
    assert store.request.await_args.args==('POST','rpc/record_deadline_resolution_review')


def test_withdrawal_keeps_original_identity_after_other_term_reviews(endpoint):
    client,store=endpoint;original=review_body()['id']
    body=dict(review_body(),id=OTHER,expected_sequence=8,status='withdrawn',original_review_id=original,
        resolution=None,personally_reviewed=False,expires_at=None)
    store.request.return_value=receipt(body)
    response=client.post(BASE,json=body)
    assert response.status_code==200 and response.json()['interpretation_review_id']==original
    args=store.request.await_args.kwargs['body']
    assert args['p_original']==original and args['p_expected_sequence']==8 and args['p_resolution'] is None


@pytest.mark.parametrize('change',[
    {'workspace_id':OTHER},{'actor_id':OTHER},{'deadline_sources':[]},{'execution_authorized':True},
    {'expected_version':True},{'expected_sequence':True},{'resolution':None},
    {'personally_reviewed':False},{'expires_at':0},{'term':'effective'}, {'original_review_id':OTHER},
])
def test_client_authority_and_mixed_identity_rejected_before_store(endpoint,change):
    client,store=endpoint
    assert client.post(BASE,json=review_body()|change).status_code==422
    store.request.assert_not_awaited()


def test_path_version_mismatch_is_definite_without_store_access(endpoint):
    client,store=endpoint;response=client.post(BASE,json=review_body()|{'expected_version':3})
    assert response.status_code==409 and response.headers['x-acquisition-deadline-review-rejected']=='true'
    assert response.headers['cache-control']=='no-store'
    store.request.assert_not_awaited()


@pytest.mark.parametrize('change',[
    {'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':3},{'review_id':OTHER},
    {'sequence':5},{'sequence':True},{'kind':'executed_contract'},{'status':'withdrawn'},
    {'term':'effective'},{'interpretation_review_id':OTHER},{'review_recorded':False},
    {'approval_current':True},{'execution_authorized':True},{'duplicate':'true'},{'private':'secret-marker'},
])
def test_mismatched_receipt_is_uncertain_and_never_automatically_retried(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=review_body())
    assert response.status_code==503 and 'same request' in response.text and 'secret-marker' not in response.text
    assert 'x-acquisition-deadline-review-rejected' not in response.headers
    store.request.assert_awaited_once()


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_only_definite_rejection_may_clear_a_saved_request(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.post(BASE,json=review_body())
    assert response.status_code==status
    assert (response.headers.get('x-acquisition-deadline-review-rejected')=='true')==(status in {401,403,409})
    store.request.assert_awaited_once()


def test_withdrawal_receipt_cannot_redirect_to_another_original(endpoint):
    client,store=endpoint;body=dict(review_body(),id=OTHER,status='withdrawn',original_review_id=review_body()['id'],
        resolution=None,personally_reviewed=False,expires_at=None)
    store.request.return_value=receipt(body)|{'interpretation_review_id':WORKSPACE}
    response=client.post(BASE,json=body)
    assert response.status_code==503 and 'x-acquisition-deadline-review-rejected' not in response.headers


@pytest.mark.parametrize('status',['approved','requires_review','withdrawn','not_reviewed'])
def test_current_term_state_keeps_shared_and_selected_sequences_distinct(endpoint,status):
    from tests.test_acquisition_deadline_resolution import deadline_state
    client,store=endpoint;value=deadline_state()|dict(status=status,approval_current=status=='approved')
    if status!='approved':value['expires_at']=None
    if status=='withdrawn':value.update(review_id=OTHER,review_sequence=3)
    if status=='not_reviewed':value.update(review_id=None,review_sequence=None,interpretation_review_id=None,resolution=None)
    store.request.return_value=value
    result=client.get(BASE+'/closing_deadline')
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert result.json()['sequence']==3 and result.json()['status']==status
    store.request.assert_awaited_once_with('POST','rpc/deadline_review_state',body={
        'p_workspace':WORKSPACE,'p_contract':CONTRACT,'p_version':2,'p_term':'closing_deadline'})


@pytest.mark.parametrize('change',[
    {'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':1},{'term':'effective'},
    {'checked_at':'2020-01-01T00:00:00Z'},{'checked_at':'2099-01-01T00:00:00Z'},
    {'approval_current':False},{'review_sequence':4},{'private':'secret-marker'},
])
def test_stale_or_mixed_term_read_never_clears_saved_write(endpoint,change):
    from tests.test_acquisition_deadline_resolution import deadline_state
    client,store=endpoint;store.request.return_value=deadline_state()|change
    result=client.get(BASE+'/closing_deadline')
    assert result.status_code==503 and 'secret-marker' not in result.text
    assert 'x-acquisition-deadline-review-rejected' not in result.headers


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_read_error_does_not_authorize_discarding_pending_write(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    result=client.get(BASE+'/closing_deadline')
    assert result.status_code==status and 'x-acquisition-deadline-review-rejected' not in result.headers


def test_invalid_term_is_rejected_without_store_access(endpoint):
    client,store=endpoint
    assert client.get(BASE+'/purchase_price').status_code==422
    store.request.assert_not_awaited()


def candidate():
    from tests.test_acquisition_deadline_resolution import deadline_state
    state=deadline_state();source=state['resolution']['source']
    return dict(workspace_id=WORKSPACE,contract_id=CONTRACT,contract_version=2,term='closing_deadline',
        artifact_id=source['artifact_id'],status='ready_for_human_review',checked_at=state['checked_at'],
        execution_authorized=False,current_review=state,original_source=source|{'verification_id':OTHER},
        candidate=dict(artifact_id=source['artifact_id'],source_version=1,verification_id=OTHER,sha256=source['sha256'],
            policy_id=OTHER,max_expires_at=state['expires_at'],expected_sequence=state['sequence']),
        withdrawal=dict(review_id=state['review_id'],artifact_id=source['artifact_id'],source_version=1,
            verification_id=OTHER,policy_id=OTHER,expected_sequence=state['sequence']))


def candidate_path():return BASE+'/closing_deadline/documents/'+candidate()['artifact_id']+'/candidate'


def test_candidate_preserves_original_withdrawal_and_shared_sequence(endpoint):
    client,store=endpoint;value=candidate();store.request.return_value=value
    response=client.get(candidate_path())
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['withdrawal']['expected_sequence']==3
    assert response.json()['current_review']['review_sequence']==1
    assert response.json()['candidate']['expected_sequence']==3
    assert store.request.await_args.args==('POST','rpc/deadline_review_candidate')
    assert store.request.await_args.kwargs['body']['p_term']=='closing_deadline'


@pytest.mark.parametrize('status',['paused','contract_unavailable','history_limit_reached','prepared_terms_required',
    'original_date_required','original_evidence_review_required','reviewer_policy_required','evidence_review_required'])
def test_held_candidate_cannot_inherit_approval_from_withdrawal(endpoint,status):
    client,store=endpoint;store.request.return_value=candidate()|{'status':status,'candidate':None}
    result=client.get(candidate_path())
    assert result.status_code==200 and result.json()['candidate'] is None
    assert result.json()['withdrawal'] is not None and not result.json()['execution_authorized']


@pytest.mark.parametrize('field,change',[
    ('top',{'term':'effective'}),('top',{'workspace_id':OTHER}),('top',{'artifact_id':OTHER}),
    ('top',{'checked_at':'2020-01-01T00:00:00Z'}),('top',{'execution_authorized':True}),
    ('top',{'original_source':None}),('top',{'status':'paused'}),('top',{'private':'secret-marker'}),
    ('candidate',{'expected_sequence':1}),('candidate',{'source_version':3}),('candidate',{'artifact_id':OTHER}),
    ('candidate',{'max_expires_at':'2099-01-01T00:00:00Z'}),('candidate',{'max_expires_at':'2020-01-01T00:00:00Z'}),
    ('withdrawal',{'expected_sequence':1}),('withdrawal',{'review_id':OTHER}),('withdrawal',{'source_version':3}),('withdrawal',{'artifact_id':OTHER}),('withdrawal',{'source_version':2}),
    ('original_source',{'term':'effective'}),('original_source',{'artifact_version':2}),
    ('current_review',{'term':'effective'}),
])
def test_mixed_stale_or_unbounded_actions_remain_uncertain(endpoint,field,change):
    client,store=endpoint;value=candidate()
    if field=='top':value.update(change)
    else:value[field].update(change)
    store.request.return_value=value
    response=client.get(candidate_path())
    assert response.status_code==503 and 'secret-marker' not in response.text
    assert 'x-acquisition-deadline-review-rejected' not in response.headers


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_discovery_error_preserves_pending_save(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    result=client.get(candidate_path())
    assert result.status_code==status and 'x-acquisition-deadline-review-rejected' not in result.headers
