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


def choice():
    from datetime import datetime,timedelta,timezone
    now=datetime.now(timezone.utc)
    return dict(workspace_id=W,contract_id=C,contract_version=2,current_version=2,current_status='draft',sequence=0,
        status='ready_for_human_review',candidate=dict(expected_version=2,expected_sequence=0,expected_status='draft',
        target_status='pending_signature',signature_review_id=R,expires_at=(now+timedelta(minutes=5)).isoformat()),
        checked_at=now.isoformat(),execution_authorized=False)


def test_choice_is_scoped_read_only_and_has_no_execution_authority(endpoint):
    client,store=endpoint;store.request.return_value=choice()
    response=client.get(PATH+'/candidate',params={'contract_version':2})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert not response.json()['execution_authorized']
    assert store.request.await_args.args==('POST','rpc/contract_transition_choice')
    assert store.request.await_args.kwargs['body']==dict(p_workspace=W,p_contract=C,p_version=2)


@pytest.mark.parametrize('change',[
    {'workspace_id':C},{'contract_id':W},{'contract_version':1},{'current_version':1},{'sequence':1},
    {'current_status':'pending_signature'},{'status':'paused'},{'candidate':None},{'execution_authorized':True},
    {'checked_at':'2020-01-01T00:00:00Z'},{'checked_at':'2099-01-01T00:00:00Z'},
    {'checked_at':12345},{'status':'awaiting_signature'},{'unexpected':'private-marker'}])
def test_choice_rejects_wrong_scope_staleness_and_contradictory_authority(endpoint,change):
    client,store=endpoint;store.request.return_value=choice()|change
    response=client.get(PATH+'/candidate',params={'contract_version':2})
    assert response.status_code==503 and 'private-marker' not in response.text
    assert response.headers['cache-control']=='no-store'


@pytest.mark.parametrize('field,value', [('expected_version',3),('expected_sequence',1),('expected_sequence',True),
    ('expires_at','2020-01-01T00:00:00Z'),('expires_at',12345),('expected_status','executed')])
def test_choice_rejects_inconsistent_nested_target_and_expiry(endpoint,field,value):
    client,store=endpoint;raw=choice();raw['candidate'][field]=value;store.request.return_value=raw
    assert client.get(PATH+'/candidate',params={'contract_version':2}).status_code==503


@pytest.mark.parametrize('status',['paused','signature_review_required','history_requires_review'])
def test_held_choice_has_no_available_transition(endpoint,status):
    client,store=endpoint;store.request.return_value=choice()|{'status':status,'candidate':None}
    assert client.get(PATH+'/candidate',params={'contract_version':2}).json()['candidate'] is None


def executed_choice():
    value=choice()
    expiry=value['candidate']['expires_at']
    return value|dict(current_status='pending_signature',sequence=1,candidate=dict(expected_version=2,
        expected_sequence=1,expected_status='pending_signature',target_status='executed',execution_review_id=R,expires_at=expiry))


def test_executed_choice_requires_exact_review_kind_and_current_lifecycle(endpoint):
    client,store=endpoint
    store.request.return_value=executed_choice()
    response=client.get(PATH+'/candidate',params={'contract_version':2})
    assert response.status_code==200
    assert response.json()['candidate']['execution_review_id']==R
    assert 'signature_review_id' not in response.json()['candidate']
    for patch in ({'expected_sequence':0},{'expected_status':'draft'},{'signature_review_id':R},{'target_status':'title_review'}):
        value=executed_choice();value['candidate'].update(patch);store.request.return_value=value
        assert client.get(PATH+'/candidate',params={'contract_version':2}).status_code==503


@pytest.mark.parametrize('status,current,sequence', [('execution_review_required','pending_signature',1),('execution_recorded','executed',2)])
def test_executed_holds_preserve_exact_status_without_new_action(endpoint,status,current,sequence):
    client,store=endpoint
    value=executed_choice()|dict(current_status=current,sequence=sequence,status=status,candidate=None)
    store.request.return_value=value
    assert client.get(PATH+'/candidate',params={'contract_version':2}).json()['candidate'] is None
    store.request.return_value=value|{'sequence':sequence+1}
    assert client.get(PATH+'/candidate',params={'contract_version':2}).status_code==503


def title_choice():
    value=executed_choice()
    return value|dict(current_status='executed',sequence=2,candidate=value['candidate']|dict(
        expected_sequence=2,expected_status='executed',target_status='title_review'))


def test_title_choice_retains_original_review_and_exact_lifecycle(endpoint):
    client,store=endpoint;store.request.return_value=title_choice()
    response=client.get(PATH+'/candidate',params={'contract_version':2})
    assert response.status_code==200 and response.json()['candidate']['execution_review_id']==R
    for patch in ({'expected_sequence':1},{'expected_status':'pending_signature'},{'signature_review_id':R},{'expected_version':1}):
        value=title_choice();value['candidate'].update(patch);store.request.return_value=value
        assert client.get(PATH+'/candidate',params={'contract_version':2}).status_code==503


@pytest.mark.parametrize('status,current,sequence',[('title_review_required','executed',2),('title_review_started','title_review',3)])
def test_title_holds_require_exact_current_status(endpoint,status,current,sequence):
    client,store=endpoint
    value=title_choice()|dict(status=status,current_status=current,sequence=sequence,candidate=None)
    store.request.return_value=value
    assert client.get(PATH+'/candidate',params={'contract_version':2}).status_code==200
    store.request.return_value=value|dict(sequence=sequence-1)
    assert client.get(PATH+'/candidate',params={'contract_version':2}).status_code==503
