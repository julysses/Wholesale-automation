"""Mounted renewal transport; disposable SQL tests separately verify authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router
from tests.test_acquisition_deadline_resolution import body as deadline_body


def uid(n):return str(UUID(f'af141000-0000-4000-8000-{n:012d}'))
BASE=f'/api/acquisition/workspaces/{uid(1)}/contracts/{uid(2)}/versions/2/review-renewals'
ROOT=uid(4)


def command():
    return dict(id=uid(3),expected_version=2,expected_sequence=1,kind='deadline_resolution',deadline_term='closing_deadline',
        root_review_id=ROOT,previous_review_id=ROOT,policy_id=uid(5),expected_snapshot_sha256='a'*64,
        expires_at='2026-01-01T00:00:00Z',personally_reviewed=True,note='  Personally re-reviewed this original agreement and supporting evidence.  ')


def receipt():
    return dict(workspace_id=uid(1),contract_id=uid(2),contract_version=2,kind='deadline_resolution',deadline_term='closing_deadline',
        review_id=uid(3),root_review_id=ROOT,previous_review_id=ROOT,sequence=2,duplicate=True,review_recorded=True,
        approval_current=False,execution_authorized=False)


def choice():
    now=datetime.now(timezone.utc);expiry=(now+timedelta(minutes=2)).isoformat()
    return dict(workspace_id=uid(1),contract_id=uid(2),contract_version=2,root_review_id=ROOT,kind='deadline_resolution',deadline_term='closing_deadline',
        status='ready_for_human_review',candidate=dict(expected_sequence=1,previous_review_id=ROOT,policy_id=uid(5),expected_snapshot_sha256='a'*64,
            max_expires_at=expiry,sources=[dict(artifact_id=uid(6),source_version=1,verification_id=uid(7),sha256='a'*64,purpose='purchase_contract',expires_at=expiry)]),
        original=dict(created_at=(now-timedelta(hours=2)).isoformat(),expires_at=(now-timedelta(hours=1)).isoformat(),findings=deadline_body()['resolution']),
        current_review=dict(review_id=ROOT,expires_at=(now-timedelta(hours=1)).isoformat(),approval_current=False),dependencies=[],checked_at=now.isoformat(),execution_authorized=False)


def index():
    c=choice()
    return {k:c[k] for k in ('workspace_id','contract_id','contract_version','checked_at','execution_authorized')}|dict(items=[{k:c[k] for k in ('root_review_id','kind','deadline_term','status','current_review')}])


@pytest.fixture
def endpoint():
    store=AsyncMock();app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=lambda:store
    with TestClient(app) as client:yield client,store


def test_exact_expired_request_can_recover_historical_receipt(endpoint):
    client,store=endpoint;store.request.return_value=receipt()
    for _ in range(2):
        result=client.post(BASE,json=command())
        assert result.status_code==200 and result.headers['cache-control']=='no-store'
        assert result.json()['duplicate'] and not result.json()['approval_current']
    assert store.request.await_args_list[0]==store.request.await_args_list[1]
    assert store.request.await_args.args==('POST','rpc/record_acquisition_review_renewal')
    assert store.request.await_args.kwargs['body']['p_note']==command()['note']
    assert store.request.await_args.kwargs['body']['p_root']==ROOT


@pytest.mark.parametrize('patch',[{'findings':{}},{'sources':[]},{'actor_id':uid(9)},{'workspace_id':uid(9)},
    {'personally_reviewed':False},{'expected_version':True},{'expected_sequence':True},{'expires_at':12345},{'expected_snapshot_sha256':'bad'}])
def test_invalid_inputs_never_reach_store(endpoint,patch):
    client,store=endpoint;assert client.post(BASE,json=command()|patch).status_code==422;store.request.assert_not_awaited()


def test_version_mismatch_is_definite_and_local(endpoint):
    client,store=endpoint;result=client.post(BASE,json=command()|dict(expected_version=3))
    assert result.status_code==409 and result.headers['x-acquisition-renewal-rejected']=='true';store.request.assert_not_awaited()


@pytest.mark.parametrize('patch',[{'workspace_id':uid(9)},{'contract_id':uid(9)},{'root_review_id':uid(9)},{'previous_review_id':uid(9)},
    {'review_id':uid(9)},{'sequence':3},{'kind':'title_findings'},{'approval_current':True},{'execution_authorized':True},{'duplicate':'true'},{'private':'secret-marker'}])
def test_mismatched_receipt_is_uncertain_without_retry_or_leak(endpoint,patch):
    client,store=endpoint;store.request.return_value=receipt()|patch;result=client.post(BASE,json=command())
    assert result.status_code==503 and 'same request' in result.text and 'secret-marker' not in result.text
    assert 'x-acquisition-renewal-rejected' not in result.headers;store.request.assert_awaited_once()


@pytest.mark.parametrize('code',[401,403,409,429,503])
def test_only_definite_rejections_mark_this_attempt(endpoint,code):
    client,store=endpoint;store.request.side_effect=HTTPException(code,'Unavailable');result=client.post(BASE,json=command())
    assert result.status_code==code and result.headers['cache-control']=='no-store'
    assert (result.headers.get('x-acquisition-renewal-rejected')=='true')==(code in {401,403,409})
    store.request.assert_awaited_once()


@pytest.mark.parametrize('suffix,payload,rpc',[('',index,'acquisition_review_renewal_index'),('/'+ROOT+'/candidate',choice,'acquisition_review_renewal_candidate')])
def test_scoped_read_choices_are_non_executing(endpoint,suffix,payload,rpc):
    client,store=endpoint;store.request.return_value=payload();result=client.get(BASE+suffix)
    assert result.status_code==200 and result.headers['cache-control']=='no-store' and not result.json()['execution_authorized']
    assert store.request.await_args.args==('POST','rpc/'+rpc)
    assert store.request.await_args.kwargs['body']['p_workspace']==uid(1)


@pytest.mark.parametrize('suffix,payload',[('',index),('/'+ROOT+'/candidate',choice)])
@pytest.mark.parametrize('change',['scope','stale','future','authority','extra'])
def test_invalid_discovery_stays_unavailable(endpoint,suffix,payload,change):
    client,store=endpoint;raw=payload()
    if change=='scope':raw['workspace_id']=uid(9)
    if change=='stale':raw['checked_at']=(datetime.now(timezone.utc)-timedelta(seconds=31)).isoformat()
    if change=='future':raw['checked_at']=(datetime.now(timezone.utc)+timedelta(seconds=6)).isoformat()
    if change=='authority':raw['execution_authorized']=True
    if change=='extra':raw['private']='secret-marker'
    store.request.return_value=raw;result=client.get(BASE+suffix)
    assert result.status_code==503 and 'secret-marker' not in result.text;store.request.assert_awaited_once()


def test_duplicate_index_and_expired_in_transit_candidate_are_held(endpoint):
    client,store=endpoint;raw=index();raw['items']*=2;store.request.return_value=raw
    assert client.get(BASE).status_code==503
    raw=choice();now=datetime.now(timezone.utc);raw['checked_at']=(now-timedelta(seconds=20)).isoformat()
    raw['candidate']['max_expires_at']=(now-timedelta(seconds=1)).isoformat();store.request.return_value=raw
    assert client.get(BASE+'/'+ROOT+'/candidate').status_code==503
