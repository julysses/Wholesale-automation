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
