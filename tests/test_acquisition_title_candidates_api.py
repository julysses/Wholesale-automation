"""Typed title choices never turn a resolution-only state into approval."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from tests.test_acquisition_title_reviews_api import endpoint,state,UID,REVIEW_ID,OTHER,BASE
CHOICE=BASE+'/candidate'


def candidate():
    current=state()|dict(status='not_reviewed',sequence=0,review_id=None,approval_current=False,expires_at=None)
    resolution=dict(artifact_id=UID,source_version=2,verification_id=UID,sha256='a'*64,policy_id=UID,
        expected_sequence=0,available_until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat())
    approval=resolution|dict(max_expires_at=resolution['available_until'],report_policy=dict(max_age_seconds=86400,max_age_days=1,timezone='UTC'))
    return dict(workspace_id=UID,contract_id=UID,contract_version=2,artifact_id=UID,status='ready_for_human_review',candidate=approval,
        resolution=resolution,withdrawal=None,current_review=current,checked_at=current['checked_at'],execution_authorized=False)


def test_scoped_selected_report_choices_are_read_only(endpoint):
    client,store=endpoint;store.request.return_value=candidate()
    response=client.get(CHOICE,params={'artifact_id':UID})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['candidate']['report_policy']['max_age_days']==1
    store.request.assert_awaited_once_with('POST','rpc/title_review_candidate',body=dict(p_workspace=UID,p_contract=UID,p_version=2,p_artifact=UID))
    assert client.post(CHOICE,json={}).status_code==405


@pytest.mark.parametrize('status',['execution_review_required','report_freshness_policy_required'])
def test_resolution_only_retains_source_without_offering_approval(endpoint,status):
    client,store=endpoint;store.request.return_value=candidate()|dict(status=status,candidate=None)
    response=client.get(CHOICE,params={'artifact_id':UID})
    assert response.status_code==200 and response.json()['candidate'] is None and response.json()['resolution']


def test_original_held_withdrawal_needs_no_selected_document(endpoint):
    client,store=endpoint;value=candidate()
    value.update(artifact_id=None,status='paused',candidate=None,resolution=None)
    value['current_review'].update(status='requires_resolution',sequence=1,review_id=REVIEW_ID)
    value['withdrawal']=dict(review_id=REVIEW_ID,artifact_id=OTHER,source_version=1,verification_id=UID,policy_id=UID,expected_sequence=1,original_status='requires_resolution')
    store.request.return_value=value
    response=client.get(CHOICE)
    assert response.status_code==200 and response.json()['withdrawal']['artifact_id']==OTHER
    assert store.request.await_args.kwargs['body']['p_artifact'] is None


@pytest.mark.parametrize('change',[{'workspace_id':OTHER},{'contract_id':OTHER},{'contract_version':1},{'artifact_id':None},
    {'checked_at':'2020-01-01T00:00:00Z'},{'checked_at':0},{'execution_authorized':True},{'status':'paused'},
    {'candidate':None},{'resolution':None},{'secret':'secret-marker'}])
def test_invalid_scope_or_false_ready_response_remains_unavailable(endpoint,change):
    client,store=endpoint;store.request.return_value=candidate()|change
    response=client.get(CHOICE,params={'artifact_id':UID})
    assert response.status_code==503 and 'secret-marker' not in response.text
    assert 'x-acquisition-title-review-rejected' not in response.headers


@pytest.mark.parametrize('change',[{'source_version':3},{'source_version':True},{'artifact_id':OTHER},{'expected_sequence':1},
    {'available_until':'2020-01-01T00:00:00Z'},{'available_until':0},{'sha256':'A'*64}])
def test_resolution_source_must_match_scope_and_current_cursor(endpoint,change):
    client,store=endpoint;value=candidate();value['resolution'].update(change);value['candidate'].update(change);store.request.return_value=value
    assert client.get(CHOICE,params={'artifact_id':UID}).status_code==503


@pytest.mark.parametrize('change',[{'policy_id':OTHER},{'max_expires_at':'2020-01-01T00:00:00Z'},
    {'report_policy':{'max_age_seconds':None,'max_age_days':None,'timezone':None}},
    {'report_policy':{'max_age_seconds':True,'max_age_days':1,'timezone':'UTC'}},
    {'report_policy':{'max_age_seconds':None,'max_age_days':1,'timezone':None}},
    {'report_policy':{'max_age_seconds':None,'max_age_days':1,'timezone':'Invalid/Zone'}}])
def test_approval_requires_same_original_and_explicit_supported_precision(endpoint,change):
    client,store=endpoint;value=candidate();value['candidate'].update(change);store.request.return_value=value
    assert client.get(CHOICE,params={'artifact_id':UID}).status_code==503


def test_wrong_original_status_cannot_offer_withdrawal(endpoint):
    client,store=endpoint;value=candidate()
    value['current_review'].update(status='requires_resolution',sequence=1,review_id=REVIEW_ID)
    value.update(status='paused',candidate=None,resolution=None)
    value['withdrawal']=dict(review_id=REVIEW_ID,artifact_id=UID,source_version=2,verification_id=UID,policy_id=UID,expected_sequence=1,original_status='approved')
    store.request.return_value=value
    assert client.get(CHOICE,params={'artifact_id':UID}).status_code==503


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_choice_errors_do_not_clear_pending_mutation(endpoint,status):
    from fastapi import HTTPException
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.get(CHOICE,params={'artifact_id':UID})
    assert response.status_code==status and 'x-acquisition-title-review-rejected' not in response.headers
