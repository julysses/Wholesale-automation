"""Mounted choices are fresh, exact, non-executing and independent of withdrawal."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from tests.test_acquisition_disposition_review import ID,OTHER

BASE=f'/api/acquisition/workspaces/{ID}/contracts/{ID}/versions/2/disposition-review/candidate'


def choice(assignment=True):
    now=datetime.now(timezone.utc);expiry=(now+timedelta(minutes=5)).isoformat()
    source=dict(artifact_id=ID,source_version=1,verification_id=OTHER,sha256='a'*64,purpose='purchase_contract',expires_at=expiry)
    resolution=dict(plan_id=OTHER,exit_type='wholesale_assignment' if assignment else 'principal_acquisition',policy_id=ID,
        execution_transition_id=ID,title_entry_id=OTHER,title_review_id=ID,title_status='approved',expected_sequence=0,
        available_until=expiry,executed_source=source,legal_source=deepcopy(source) if assignment else None)
    state=dict(workspace_id=ID,contract_id=ID,contract_version=2,kind='disposition_findings',sequence=0,review_id=None,status='not_reviewed',
        approval_current=False,expires_at=None,checked_at=now.isoformat(),execution_authorized=False)
    return dict(workspace_id=ID,contract_id=ID,contract_version=2,status='ready_for_human_review',candidate=resolution|dict(max_expires_at=expiry),
        resolution=deepcopy(resolution),withdrawal=None,current_review=state,checked_at=now.isoformat(),execution_authorized=False)


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


@pytest.mark.parametrize('assignment',[True,False])
def test_current_exact_source_and_policy_choices_are_non_executing(endpoint,assignment):
    client,store=endpoint;store.request.return_value=choice(assignment)
    response=client.get(BASE)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    result=response.json();assert not result['execution_authorized'] and result['candidate']['executed_source']['source_version']==1
    store.request.assert_awaited_once_with('POST','rpc/disposition_review_candidate',body={'p_workspace':ID,'p_contract':ID,'p_version':2})


@pytest.mark.parametrize('status',['paused','contract_unavailable','history_limit_reached','proposal_required','title_findings_required','reviewer_policy_required','evidence_review_required','execution_review_required','title_review_required','legal_evidence_required'])
def test_explicit_holds_and_original_withdrawal_are_independent(endpoint,status):
    client,store=endpoint;value=choice();value.update(status=status,candidate=None)
    if status not in {'execution_review_required','title_review_required','legal_evidence_required'}:value['resolution']=None
    if value['resolution']:value['resolution']['expected_sequence']=1
    value['current_review'].update(review_id=OTHER,sequence=1,status='requires_review')
    value['withdrawal']=dict(review_id=OTHER,plan_id=ID,exit_type='principal_acquisition',policy_id=OTHER,expected_sequence=1,original_status='approved')
    if status=='legal_evidence_required':value['resolution']['legal_source']=None
    if status=='history_limit_reached':value['current_review']['sequence']=2147483647;value['withdrawal']=None
    store.request.return_value=value
    response=client.get(BASE)
    assert response.status_code==200 and response.json()['candidate'] is None
    if status!='history_limit_reached':assert response.json()['withdrawal']['plan_id']==ID


@pytest.mark.parametrize('change',['workspace','contract','version','kind','execution','scope_time','future_time','stale_time','sequence','root_version','root_purpose','root_expired','root_mismatch','candidate_policy','candidate_without_resolution','approval_without_legal','held_title_approval','expired_max','overlong_max','unknown_status','hold_with_approval','withdrawal_id','withdrawal_status','withdrawal_sequence','history_limit','false_legal_hold','secret'])
def test_mixed_stale_or_contradictory_choices_are_unavailable(endpoint,change):
    client,store=endpoint;value=choice();now=datetime.now(timezone.utc)
    if change=='workspace':value['workspace_id']=OTHER
    if change=='contract':value['contract_id']=OTHER
    if change=='version':value['contract_version']=1
    if change=='kind':value['current_review']['kind']='title_findings'
    if change=='execution':value['execution_authorized']=True
    if change=='scope_time':value['current_review']['checked_at']=(now-timedelta(seconds=1)).isoformat()
    if change in {'future_time','stale_time'}:
        value['checked_at']=value['current_review']['checked_at']=(now+timedelta(seconds=120 if change=='future_time' else -120)).isoformat()
    if change=='sequence':value['resolution']['expected_sequence']=2
    if change=='root_version':value['resolution']['executed_source']['source_version']=3
    if change=='root_purpose':value['resolution']['executed_source']['purpose']='title_report'
    if change=='root_expired':value['resolution']['executed_source']['expires_at']=(now-timedelta(seconds=1)).isoformat()
    if change=='root_mismatch':value['resolution']['legal_source']['sha256']='b'*64
    if change=='candidate_policy':value['candidate']['policy_id']=OTHER
    if change=='candidate_without_resolution':value['resolution']=None
    if change=='approval_without_legal':value['candidate']['legal_source']=None
    if change=='held_title_approval':value['candidate']['title_status']='requires_resolution'
    if change=='expired_max':value['candidate']['max_expires_at']=(now-timedelta(seconds=1)).isoformat()
    if change=='overlong_max':value['candidate']['max_expires_at']=(now+timedelta(days=2)).isoformat()
    if change=='unknown_status':value['status']='approved'
    if change=='hold_with_approval':value['status']='title_review_required'
    if change.startswith('withdrawal'):
        value['withdrawal']=dict(review_id=OTHER,plan_id=ID,exit_type='principal_acquisition',policy_id=OTHER,expected_sequence=1,original_status='approved')
        value['current_review'].update(review_id=OTHER,sequence=1,status='requires_review')
        value['resolution']['expected_sequence']=value['candidate']['expected_sequence']=1
        if change=='withdrawal_id':value['withdrawal']['review_id']=ID
        if change=='withdrawal_status':value['withdrawal']['original_status']='requires_resolution'
        if change=='withdrawal_sequence':value['withdrawal']['expected_sequence']=2
    if change=='history_limit':value.update(status='history_limit_reached',candidate=None,resolution=None)
    if change=='false_legal_hold':value.update(status='legal_evidence_required',candidate=None)
    if change=='secret':value['private']='secret-marker'
    store.request.return_value=value;response=client.get(BASE)
    assert response.status_code==503 and 'secret-marker' not in response.text
    assert 'x-acquisition-disposition-review-rejected' not in response.headers


@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_choice_error_never_clears_a_saved_request(endpoint,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.get(BASE)
    assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert 'x-acquisition-disposition-review-rejected' not in response.headers


@pytest.mark.parametrize('offset,expected',[(-31,503),(-30,200),(5,200),(6,503)])
def test_choice_freshness_uses_fixed_request_clock(endpoint,monkeypatch,offset,expected):
    from web.api import acquisition_disposition_reviews_api as api
    now=datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now.astimezone(tz) if tz else now.replace(tzinfo=None)
    monkeypatch.setattr(api,'datetime',Clock)
    value=choice();value['checked_at']=value['current_review']['checked_at']=(now+timedelta(seconds=offset)).isoformat()
    client,store=endpoint;store.request.return_value=value
    assert client.get(BASE).status_code==expected
