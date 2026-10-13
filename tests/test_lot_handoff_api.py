from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_offer_review_api import setup,OPERATOR
from web.api import list_pipeline_api as lists

@pytest.fixture
def client_db(setup,monkeypatch):
    client,db,rows=setup;monkeypatch.setattr(lists,'get_supabase_client',lambda:db);return client,db,rows
HEADERS={'Authorization':'Bearer test'}
def review_body():
    return {'request_id':str(uuid4()),'lead_id':str(uuid4()),'input_hash':'a'*64,'is_vacant_lot':True,'evidence_url':'https://example.invalid/parcel','notes':'Verified county classification'}

def test_review_uses_authenticated_actor_and_exact_saved_evidence(client_db):
    client,db,_=client_db;body=review_body()
    saved={key:value for key,value in body.items() if key!='request_id'};saved.update(id=body['request_id'],operator_id=OPERATOR)
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'review':saved})
    assert client.post('/api/operations/lists/lots/review',headers=HEADERS,json=body).status_code==200
    assert db.rpc.call_args.args[1]['p_operator']==OPERATOR
    saved['evidence_url']='https://example.invalid/other'
    assert client.post('/api/operations/lists/lots/review',headers=HEADERS,json=body).status_code==503

@pytest.mark.parametrize('change',[{'operator_id':OPERATOR},{'is_vacant_lot':'true'},{'evidence_url':'javascript:alert(1)'},{'input_hash':'bad'}])
def test_invalid_review_rejected_without_database(client_db,change):
    client,db,_=client_db
    assert client.post('/api/operations/lists/lots/review',headers=HEADERS,json={**review_body(),**change}).status_code==422;db.rpc.assert_not_called()

def test_handoff_requires_destination_task_and_correlated_receipt(client_db):
    client,db,_=client_db;body={'request_id':str(uuid4()),'evaluation_id':str(uuid4()),'assigned_to':str(uuid4())}
    saved={'id':body['request_id'],'evaluation_id':body['evaluation_id'],'assigned_to':body['assigned_to'],'operator_id':OPERATOR,'land_lead_id':str(uuid4()),'task_id':str(uuid4())}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'handoff':saved,'outreach_authorized':False})
    assert client.post('/api/operations/lists/lots/handoff',headers=HEADERS,json=body).status_code==200
    saved['task_id']=None
    assert client.post('/api/operations/lists/lots/handoff',headers=HEADERS,json=body).status_code==503
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'blocked':'stale_score'})
    assert client.post('/api/operations/lists/lots/handoff',headers=HEADERS,json=body).status_code==409

def test_receiving_operator_uses_separate_authenticated_route(client_db):
    client,db,rows=client_db;handoff=str(uuid4())
    assert client.get('/api/land-underwriting/handoffs').status_code==401
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'handoff':{'id':handoff,'acknowledged_by':OPERATOR,'acknowledged_at':'2026-10-12T00:00:00Z'},'outreach_authorized':False})
    assert client.post(f'/api/land-underwriting/handoffs/{handoff}/acknowledge',headers=HEADERS).status_code==200
    db.rpc.assert_called_with('acknowledge_list_lot',{'p_id':handoff,'p_operator':OPERATOR})
    assert client.post('/api/operations/lists/lots/review',headers=HEADERS,json=review_body()).status_code==403
