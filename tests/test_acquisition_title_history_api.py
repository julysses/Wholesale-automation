"""Historical title evidence stays exact, bounded, scoped and non-authorizing."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from schemas.acquisition_title_history import TitleHistorySummary
from tests.test_acquisition_title_review import ID, OTHER, findings

BASE=f'/api/acquisition/workspaces/{ID}/contracts/{ID}/versions/2/title-review'


def state():
    return dict(workspace_id=ID,contract_id=ID,contract_version=2,kind='title_findings',review_id=OTHER,
                sequence=4,status='requires_resolution',approval_current=False,expires_at=None,
                checked_at=datetime.now(timezone.utc).isoformat(),execution_authorized=False)


def detail(sequence=4, status='approved'):
    created=datetime.now(timezone.utc)-timedelta(days=2)
    row=dict(id=f'af960000-0000-4000-8000-{sequence:012d}',workspace_id=ID,contract_id=ID,contract_version=2,
        kind='title_findings',sequence=sequence,status=status,artifact_id=ID,source_version=2,actor_id=ID,
        note='Original synthetic title decision remains preserved in history.',
        expires_at=(created+timedelta(hours=1)).isoformat() if status=='approved' else None,created_at=created.isoformat(),
        title_original_review_id=OTHER if status=='withdrawn' else None,title_original_status='requires_resolution' if status=='withdrawn' else None,
        verification_id=ID,sha256='a'*64,personally_reviewed=status!='withdrawn',title_findings=None if status=='withdrawn' else findings(),
        title_sources=None if status=='withdrawn' else [dict(artifact_id=ID,source_version=2,verification_id=ID,sha256='a'*64,purpose='title_report',expires_at=(created+timedelta(hours=2)).isoformat())],title_execution_transition_id=OTHER)
    if status=='requires_resolution':
        row['title_findings']['ownership'].update(finding='unknown',sources=[],required_action='Obtain the missing recorded deed from title counsel.')
    return row


def summary(sequence=4, status='approved'):
    return {key:value for key,value in detail(sequence,status).items() if key in TitleHistorySummary.model_fields}


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_history_uses_user_store_exact_scope_and_bounded_descending_cursor(endpoint):
    client,store=endpoint;store.request.side_effect=[state(),[summary(4),summary(3,'requires_resolution'),summary(2,'withdrawn')]]
    response=client.get(BASE+'/history?limit=2&before=5')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    result=response.json();assert result['next_before']==3 and [r['sequence'] for r in result['items']]==[4,3]
    assert result['history_only'] and not result['approval_current'] and not result['execution_authorized']
    first,second=store.request.await_args_list
    assert first.args==('POST','rpc/title_review_state')
    assert second.args==('GET','acquisition_contract_reviews')
    assert second.kwargs['params']==dict(select=','.join(TitleHistorySummary.model_fields),workspace_id='eq.'+ID,
        contract_id='eq.'+ID,contract_version='eq.2',kind='eq.title_findings',order='sequence.desc',limit='3',sequence='lt.5')
    assert 'title_findings' not in result['items'][0] and 'session_id' not in str(second.kwargs)


@pytest.mark.parametrize('status',['approved','requires_resolution','withdrawn'])
def test_detail_preserves_expired_originals_actions_and_withdrawal_identity(endpoint,status):
    client,store=endpoint;row=detail(status=status);store.request.side_effect=[state(),[row]]
    response=client.get(BASE+'/history/'+row['id'])
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    result=response.json();assert not result['approval_current'] and not result['execution_authorized'] and result['history_only']
    assert result['record']['status']==status
    if status=='requires_resolution':assert result['record']['title_findings']['ownership']['required_action'].startswith('Obtain')
    if status=='withdrawn':assert result['record']['title_original_review_id']==OTHER and result['record']['title_findings'] is None
    if status=='approved':assert datetime.fromisoformat(result['record']['expires_at'].replace('Z','+00:00'))<datetime.now(timezone.utc)
    params=store.request.await_args.kwargs['params'];assert params['id']=='eq.'+row['id'] and params['kind']=='eq.title_findings' and params['limit']=='2'
    assert 'session_id' not in params['select'] and 'request_hash' not in params['select'] and 'title_policy_snapshot' not in params['select']


@pytest.mark.parametrize('route',['/history','/history/'+OTHER])
@pytest.mark.parametrize('status',[401,403,409,429,503])
def test_access_failure_stops_before_any_history_select_and_never_clears_saved_mutations(endpoint,route,status):
    client,store=endpoint;store.request.side_effect=HTTPException(status,'Unavailable')
    response=client.get(BASE+route);assert response.status_code==status and response.headers['cache-control']=='no-store'
    assert 'x-acquisition-title-review-rejected' not in response.headers;store.request.assert_awaited_once()


@pytest.mark.parametrize('query',['limit=0','limit=21','before=0','before=2147483648','before=abc'])
def test_invalid_pagination_never_reaches_store(endpoint,query):
    client,store=endpoint;assert client.get(BASE+'/history?'+query).status_code==422;store.request.assert_not_awaited()


@pytest.mark.parametrize('rows',[[summary(3),summary(4)], [summary(4),summary(4)], [summary(4)|{'workspace_id':OTHER}],
    [summary(4)|{'contract_id':OTHER}], [summary(4)|{'contract_version':1}], [summary(4)|{'kind':'title_review'}],
    [summary(4)|{'source_version':3}], [summary(4)|{'note':' '*20}], [summary(4)|{'created_at':0}],
    [summary(4)|{'approval_current':True}], [summary(4)|{'secret':'sensitive-marker'}], {}, None, [summary(4)]*22])
def test_mixed_malformed_unordered_history_is_unavailable_without_payload_leak(endpoint,rows):
    client,store=endpoint;store.request.side_effect=[state(),deepcopy(rows)]
    response=client.get(BASE+'/history');assert response.status_code==503 and 'sensitive-marker' not in response.text
    assert 'x-acquisition-title-review-rejected' not in response.headers


@pytest.mark.parametrize('change',['report_hash','source_hash','source_version','source_duplicate','source_missing','findings_missing','future_citation','cutoff_source','unresolved_approved','withdrawn_findings','wrong_id','duplicate_rows'])
def test_detail_rejects_contradictory_original_evidence(endpoint,change):
    client,store=endpoint;row=detail();target=row['id']
    if change=='report_hash':row['sha256']='b'*64
    if change=='source_hash':row['title_sources'][0]['sha256']='b'*64
    if change=='source_version':row['title_sources'][0]['source_version']=1
    if change=='source_duplicate':row['title_sources']*=2
    if change=='source_missing':row['title_sources']=[]
    if change=='findings_missing':row['title_findings']=None
    if change=='future_citation':row['title_findings']['ownership']['sources'][0]['artifact_version']=3
    if change=='cutoff_source':row['title_findings']['report_as_of_source']['artifact_id']=OTHER
    if change=='unresolved_approved':row['title_findings']['ownership'].update(finding='unknown',sources=[],required_action='Resolve the missing ownership evidence before approval.')
    if change=='withdrawn_findings':row.update(status='withdrawn',expires_at=None,personally_reviewed=False,title_original_review_id=OTHER,title_original_status='approved')
    if change=='wrong_id':row['id']=OTHER
    store.request.side_effect=[state(),[row,row] if change=='duplicate_rows' else [row]]
    response=client.get(BASE+'/history/'+target);assert response.status_code==503 and 'x-acquisition-title-review-rejected' not in response.headers


def test_empty_history_and_missing_detail_are_distinct(endpoint):
    client,store=endpoint;store.request.side_effect=[state(),[],state(),[]]
    page=client.get(BASE+'/history');assert page.status_code==200 and page.json()['items']==[] and page.json()['next_before'] is None
    missing=client.get(BASE+'/history/'+OTHER);assert missing.status_code==404 and missing.headers['cache-control']=='no-store'


def test_history_read_error_is_not_a_definite_write_rejection(endpoint):
    client,store=endpoint;store.request.side_effect=[state(),HTTPException(403,'Unavailable')]
    response=client.get(BASE+'/history');assert response.status_code==403 and response.headers['cache-control']=='no-store'
    assert 'x-acquisition-title-review-rejected' not in response.headers
