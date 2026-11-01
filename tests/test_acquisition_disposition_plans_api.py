"""Purchase-path intent cannot imply disposition authority or lose recovery."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router

ID='af103000-0000-4000-8000-000000000001'
OTHER='af103000-0000-4000-8000-000000000002'
BASE=f'/api/acquisition/workspaces/{ID}/contracts/{ID}/versions/2/disposition-plan'
MARKER='X-Acquisition-Disposition-Plan-Rejected'


def body():
    return dict(id=ID,expected_version=2,expected_sequence=0,status='proposed',exit_type='principal_acquisition',
        note='Propose a principal purchase for internal review only.',original_plan_id=None)


def receipt():
    return dict(plan_id=ID,workspace_id=ID,contract_id=ID,contract_version=2,sequence=1,status='proposed',
        exit_type='principal_acquisition',original_plan_id=None,duplicate=False,plan_recorded=True,
        disposition_approved=False,execution_authorized=False)


def state():
    return dict(workspace_id=ID,contract_id=ID,contract_version=2,current_version=2,current_status='title_review',
        sequence=0,readiness='ready_for_planning',latest=None,withdrawal=None,
        checked_at=datetime.now(timezone.utc).isoformat(),disposition_approved=False,execution_authorized=False)


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


@pytest.mark.parametrize('duplicate',[False,True])
def test_exact_save_and_recovery(endpoint,duplicate):
    client,store=endpoint;store.request.return_value=receipt()|dict(duplicate=duplicate)
    response=client.post(BASE,json=body())
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()==receipt()|dict(duplicate=duplicate)
    assert store.request.await_args.args==('POST','rpc/record_disposition_plan')
    assert store.request.await_args.kwargs['body']==dict(p_id=ID,p_workspace=ID,p_contract=ID,p_version=2,
        p_expected_sequence=0,p_status='proposed',p_exit_type='principal_acquisition',p_note=body()['note'],p_original_plan=None)


@pytest.mark.parametrize('change',[
    {'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':1},{'plan_id':OTHER},
    {'sequence':2},{'status':'withdrawn'},{'exit_type':'wholesale_assignment'},{'original_plan_id':OTHER},
    {'disposition_approved':True},{'execution_authorized':True},{'plan_recorded':False},{'duplicate':'true'},
    {'sequence':True},{'unexpected':'authority'},
])
def test_malformed_or_different_receipt_preserves_uncertainty(endpoint,change):
    client,store=endpoint;store.request.return_value=receipt()|change
    response=client.post(BASE,json=body())
    assert response.status_code==503 and MARKER not in response.headers
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('change',[
    {'expected_sequence':True},{'expected_sequence':-1},{'expected_sequence':2147483647},
    {'expected_version':'2'},{'note':' '*30},{'note':'x'*20+'\x00'},
    {'actor_id':ID},{'disposition_approved':True},{'buyer_id':OTHER},
    {'original_plan_id':OTHER},{'exit_type':'assignment'},{'status':'approved'},
    {'status':'withdrawn','original_plan_id':ID},{'status':'withdrawn','original_plan_id':OTHER},
])
def test_client_cannot_supply_authority_or_invalid_intent(endpoint,change):
    client,store=endpoint;response=client.post(BASE,json=body()|change)
    assert response.status_code==422
    store.request.assert_not_awaited()


def test_wrong_version_rejected_before_save(endpoint):
    client,store=endpoint;response=client.post(BASE,json=body()|dict(expected_version=1))
    assert response.status_code==409 and response.headers[MARKER]=='true'
    assert response.headers['cache-control']=='no-store';store.request.assert_not_awaited()


@pytest.mark.parametrize('status',[401,403,409,429,500,503])
def test_only_definite_write_rejection_marks_current_attempt(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Synthetic rejection')
    write=client.post(BASE,json=body())
    assert write.status_code==status
    assert (write.headers.get(MARKER)=='true')==(status in {401,403,409})
    # Use independent errors: a shared mutable HTTPException would carry POST headers.
    store.request.side_effect=HTTPException(status,'Synthetic read rejection')
    read=client.get(BASE)
    assert MARKER not in read.headers and read.headers['cache-control']=='no-store'


def test_read_and_original_withdrawal_after_pause(endpoint):
    client,store=endpoint;data=state()
    data.update(sequence=1,readiness='paused',latest=dict(plan_id=ID,sequence=1,status='proposed',exit_type='principal_acquisition',
        note=body()['note'],original_plan_id=None,created_at=data['checked_at']),
        withdrawal=dict(plan_id=ID,exit_type='principal_acquisition',expected_sequence=1))
    store.request.return_value=data
    response=client.get(BASE)
    assert response.status_code==200 and response.json()['withdrawal']==data['withdrawal']
    payload=body()|dict(id=OTHER,expected_sequence=1,status='withdrawn',original_plan_id=ID)
    store.request.return_value=receipt()|dict(plan_id=OTHER,sequence=2,status='withdrawn',original_plan_id=ID)
    response=client.post(BASE,json=payload)
    assert response.status_code==200 and not response.json()['disposition_approved']


@pytest.mark.parametrize('change',[
    {'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':1},{'current_version':1},
    {'sequence':1},{'current_status':'draft'},{'readiness':'history_limit_reached'},
    {'execution_authorized':True},{'disposition_approved':True},{'checked_at':12345},
    {'checked_at':(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()},
    {'checked_at':(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()},
    {'withdrawal':dict(plan_id=ID,exit_type='principal_acquisition',expected_sequence=1)},
])
def test_inconsistent_state_is_unavailable(endpoint,change):
    client,store=endpoint;store.request.return_value=state()|change
    response=client.get(BASE)
    assert response.status_code==503 and MARKER not in response.headers
