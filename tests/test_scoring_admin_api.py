from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_offer_review_api import setup,OPERATOR
from web.api import list_pipeline_api as lists

@pytest.fixture
def client_db(setup,monkeypatch):
    client,db,rows=setup
    monkeypatch.setattr(lists,'get_supabase_client',lambda:db)
    return client,db,rows

HEADERS={'Authorization':'Bearer test'}
def test_action_actor_is_server_derived_and_exact_receipt_required(client_db):
    client,db,_=client_db;event=str(uuid4());payload={'expected_version':1,'score_threshold':65}
    saved={'event':{'id':event,'operator_id':OPERATOR,'action':'threshold','payload':payload,'result':{'score_threshold':65,'version':2}}}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data=saved)
    body={'event_id':event,'action':'threshold',**payload}
    assert client.post('/api/operations/lists/scoring/actions',json=body,headers=HEADERS).status_code==200
    db.rpc.assert_called_with('apply_list_scoring_operation',{'p_id':event,'p_operator':OPERATOR,'p_action':'threshold','p_payload':payload})
    saved['event']['result']['version']=99
    assert client.post('/api/operations/lists/scoring/actions',json=body,headers=HEADERS).status_code==503

@pytest.mark.parametrize('extra',[{'score_threshold':True},{'score_threshold':101},{'job_id':str(uuid4())},{'operator_id':OPERATOR}])
def test_malformed_or_spoofed_threshold_never_reaches_database(client_db,extra):
    client,db,_=client_db
    body={'event_id':str(uuid4()),'action':'threshold','expected_version':1,'score_threshold':65,**extra}
    assert client.post('/api/operations/lists/scoring/actions',json=body,headers=HEADERS).status_code==422
    db.rpc.assert_not_called()

def test_scoring_admin_access_denied(client_db):
    client,db,rows=client_db
    assert client.get('/api/operations/lists/scoring').status_code==401
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists/scoring',headers=HEADERS).status_code==403
    db.rpc.assert_not_called()
