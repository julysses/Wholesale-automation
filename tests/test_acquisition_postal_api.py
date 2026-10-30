"""Postal receipt boundary rejects scope drift and false verification claims."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tools.acquisition_store import acquisition_store
from web.api.acquisition_postal_api import router

W='10000000-0000-4000-8000-000000000001'
R='20000000-0000-4000-8000-000000000001'
I='30000000-0000-4000-8000-000000000001'
BASE={'id':I,'workspace_id':W,'relationship_id':R,'raw_address':'77 Test Rd, Unit 2B',
      'verification_status':'unverified','recorded_at':'2026-10-30T04:00:00Z',
      'duplicate':False,'execution_authorized':False,'source_evidence':{'private':'hidden'}}


@pytest.mark.parametrize('change',[
    {'id':R},{'workspace_id':R},{'relationship_id':I},
    {'execution_authorized':True},{'execution_authorized':'false'},
    {'verification_status':'verified'},{'raw_address':' '},
    {'raw_address':'é'*2049},{'recorded_at':'2026-10-30T04:00:00'},
])
def test_invalid_receipt_requires_exact_retry(monkeypatch,change):
    monkeypatch.setenv('ACQUISITION_POSTAL_IMPORT_ENABLED','true')
    class Store:
        async def request(self,*args,**kwargs):return {**deepcopy(BASE),**change}
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[acquisition_store]=Store
    with TestClient(app) as client:
        response=client.post(f'/workspaces/{W}/owner-relationships/{R}/postal-observations',json={'id':I})
    assert response.status_code==503
    assert response.headers['cache-control']=='no-store'
    assert 'Retry the same saved request' in response.json()['detail']
    assert 'source_evidence' not in response.text
