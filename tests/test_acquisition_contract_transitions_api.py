from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router

W,C,R=[f'00000000-0000-4000-8000-{n:012d}' for n in range(1,4)]
PATH=f'/api/acquisition/workspaces/{W}/contracts/{C}/transitions'
BODY=dict(id=R,expected_version=2,expected_sequence=0,expected_status='draft',target_status='pending_signature',
          reason='  Record the reviewed contract as awaiting signature.  ')
RECEIPT=dict(workspace_id=W,contract_id=C,request_id=R,contract_version=2,sequence=1,previous_status='draft',
             recorded_status='pending_signature',duplicate=False,transition_recorded=True,execution_authorized=False)

@pytest.fixture
def endpoint():
    app=FastAPI();app.include_router(router);store=AsyncMock()
    app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_mounted_exact_historical_retry_and_user_scoped_rpc(endpoint):
    client,store=endpoint;store.request.return_value=RECEIPT|{'duplicate':True}
    for _ in range(2):
        response=client.post(PATH,json=BODY)
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert response.json()['duplicate'] and not response.json()['execution_authorized']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    assert store.request.await_args.kwargs['body']==dict(p_id=R,p_workspace=W,p_contract=C,
        p_expected_version=2,p_expected_sequence=0,p_expected_status='draft',p_target_status='pending_signature',p_reason=BODY['reason'])

@pytest.mark.parametrize('change',[{'workspace_id':C},{'contract_id':W},{'request_id':C},{'contract_version':1},
    {'sequence':2},{'previous_status':'executed'},{'recorded_status':'executed'},{'duplicate':'false'},
    {'execution_authorized':True},{'transition_recorded':False},{'secret':'private-marker'}])
def test_wrong_or_unsafe_receipt_keeps_request_uncertain(endpoint,change):
    client,store=endpoint;store.request.return_value=RECEIPT|change
    response=client.post(PATH,json=BODY)
    assert response.status_code==503 and 'same request' in response.text and 'private-marker' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert response.headers.get('X-Acquisition-Transition-Rejected') is None
    assert store.request.await_count==1

@pytest.mark.parametrize('field',['actor_id','workspace_id','signature_review_id','evidence','policy_id','execution_authorized'])
def test_request_cannot_assert_authority_or_evidence(endpoint,field):
    client,store=endpoint
    assert client.post(PATH,json=BODY|{field:True}).status_code==422
    store.request.assert_not_awaited()

@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_definitive_rejection_marker_is_distinct_from_uncertainty(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Safe failure')
    response=client.post(PATH,json=BODY)
    assert response.status_code==status
    assert (response.headers.get('X-Acquisition-Transition-Rejected')=='true') == (status in {401,403,409})
    assert response.headers['cache-control']=='no-store'
    assert store.request.await_count==1
