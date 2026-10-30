"""Current scan status cannot confer approval or leak unscoped observations."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tools.acquisition_store import acquisition_store
from web.api.acquisition_api import router

W='10000000-0000-4000-8000-000000000001'
C='20000000-0000-4000-8000-000000000001'
A='30000000-0000-4000-8000-000000000001'
O='40000000-0000-4000-8000-000000000001'


def response(change):
    body=dict(workspace_id=W,campaign_id=C,artifact_id=A,status='no_detection_observed',
              quarantined=False,observation_id=O,preview_authorized=False,content_approved=False,
              execution_authorized=False,checked_at=datetime.now(timezone.utc).isoformat())|change
    class Store:
        async def request(self,method,path,**kwargs):
            assert method=='POST' and path=='rpc/acquisition_evidence_scan_state'
            assert kwargs['body']==dict(p_workspace=W,p_campaign=C,p_artifact=A)
            return body
    app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=Store
    with TestClient(app) as client:
        return client.get(f'/api/acquisition/workspaces/{W}/campaigns/{C}/evidence/{A}/scan-state')


@pytest.mark.parametrize('change',[
    {'workspace_id':C},{'campaign_id':W},{'artifact_id':C},
    {'preview_authorized':True},{'content_approved':True},{'execution_authorized':True},
    {'quarantined':True},{'status':'quarantined','quarantined':False,'observation_id':None},
    {'observation_id':None},{'status':'approved'},{'signature':'private'},
    {'checked_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()},
])
def test_untrusted_or_stale_scan_receipt_fails_closed(change):
    result=response(change)
    assert result.status_code==503
    assert result.headers['cache-control']=='no-store'
    assert 'private' not in result.text


def test_scan_status_is_read_only_and_quarantine_survives_revocation():
    result=response({'status':'revoked','quarantined':True,'observation_id':None})
    assert result.status_code==200
    assert result.headers['cache-control']=='no-store'
    assert result.json()['quarantined'] is True
    assert result.json()['execution_authorized'] is False
