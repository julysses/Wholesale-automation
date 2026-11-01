"""Mounted buyer projection/recovery contracts; SQL probes verify real authority."""
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
from uuid import UUID
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from tests.test_acquisition_buyer_models import details
from schemas.acquisition_buyers import AcquisitionBuyerDetails


def uid(n):return str(UUID(f'af153000-0000-4000-8000-{n:012d}'))
BASE=f'/api/acquisition/workspaces/{uid(1)}/buyers'


def command():return dict(id=uid(2),buyer_id=uid(3),expected_revision=1,details=AcquisitionBuyerDetails.model_validate(details()).model_dump(mode='json'))
def receipt():return dict(request_id=uid(2),workspace_id=uid(1),buyer_id=uid(3),revision=2,details=command()['details'],duplicate=True,profile_recorded=True,buyer_verified=False,contact_authorized=False,execution_authorized=False)
def projection():return dict(workspace_id=uid(1),checked_at=datetime.now(timezone.utc).isoformat(),can_save=True,contact_authorized=False,execution_authorized=False)
def page():return projection()|dict(items=[dict(buyer_id=uid(3),revision=2,first_name='Example',last_name='Buyer',company=None,active=True,buyer_verified=False)],next_cursor=None)
def profile():return projection()|dict(buyer_id=uid(3),revision=2,details=command()['details'],buyer_verified=False)


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_exact_historical_buyer_receipt_and_retry(endpoint):
    client,store=endpoint;store.request.return_value=receipt()
    for _ in range(2):
        response=client.post(BASE,json=command());assert response.status_code==200
        assert response.headers['cache-control']=='no-store' and response.json()['duplicate']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    assert store.request.await_args.args==('POST','rpc/record_acquisition_buyer')
    assert store.request.await_args.kwargs['body']['p_details']['min_price_cents'] is None


@pytest.mark.parametrize('patch',[{'workspace_id':uid(8)},{'buyer_id':uid(8)},{'revision':3},{'buyer_verified':True},{'contact_authorized':True},{'execution_authorized':True},{'details':command()['details']|{'company':'Changed'}}])
def test_wrong_receipt_remains_uncertain(endpoint,patch):
    client,store=endpoint;store.request.return_value=receipt()|patch
    response=client.post(BASE,json=command());assert response.status_code==503
    assert 'x-acquisition-buyer-rejected' not in response.headers


@pytest.mark.parametrize('status',[401,403,409,422,500,503])
def test_only_definite_denials_have_rejection_marker(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Synthetic failure')
    response=client.post(BASE,json=command());assert response.status_code==status
    assert (response.headers.get('x-acquisition-buyer-rejected')=='true')==(status in (401,403,409))


def test_injected_verification_rejected_before_rpc(endpoint):
    client,store=endpoint;body=command();body['details']['pof_verified']=True
    assert client.post(BASE,json=body).status_code==422;store.request.assert_not_awaited()


def test_index_and_profile_bound_scope_and_no_store(endpoint):
    client,store=endpoint;store.request.return_value=page()
    response=client.get(BASE);assert response.status_code==200 and response.headers['cache-control']=='no-store'
    store.request.return_value=profile();response=client.get(BASE+'/'+uid(3));assert response.status_code==200
    store.request.return_value=None;assert client.get(BASE+'/'+uid(3)).status_code==404


@pytest.mark.parametrize('patch',[{'workspace_id':uid(8)},{'checked_at':(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()},{'contact_authorized':True},{'next_cursor':uid(8)}])
def test_bad_index_projection_is_not_displayed(endpoint,patch):
    client,store=endpoint;store.request.return_value=page()|patch
    assert client.get(BASE).status_code==503


def test_page_rejects_duplicate_before_cursor_and_size_mismatch(endpoint):
    client,store=endpoint;value=page();store.request.return_value=value|dict(items=value['items']*2)
    assert client.get(BASE).status_code==503
    store.request.return_value=value
    assert client.get(BASE,params={'after':uid(3)}).status_code==503
    store.request.return_value=value|dict(next_cursor=uid(3))
    assert client.get(BASE,params={'limit':2}).status_code==503


def test_wrong_profile_identity_is_not_displayed(endpoint):
    client,store=endpoint;store.request.return_value=profile()|dict(buyer_id=uid(8))
    assert client.get(BASE+'/'+uid(3)).status_code==503
