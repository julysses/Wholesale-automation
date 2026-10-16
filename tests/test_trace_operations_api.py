from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.list_api_fixtures import setup,OPERATOR
from web.api import list_pipeline_api as lists

@pytest.fixture
def client_db(setup,monkeypatch):
    client,db,rows=setup
    monkeypatch.setattr(lists,'get_supabase_client',lambda:db)
    return client,db,rows

def receipt(event,trace):
    return {'event':{'id':event,'request_id':trace,'operator_id':OPERATOR,'action':'cancel_reserved',
        'result':{'request':{'id':trace,'state':'failed','actual_cents':0,'provider_job_id':'not_submitted'}}},'replayed':False}

def test_cancel_checks_exact_receipt_and_uses_authenticated_actor(client_db):
    client,db,_=client_db;trace,event=str(uuid4()),str(uuid4())
    db.rpc.return_value.execute.return_value=SimpleNamespace(data=receipt(event,trace))
    r=client.post(f'/api/operations/lists/tracing/{trace}/cancel',json={'event_id':event},headers={'Authorization':'Bearer test'})
    assert r.status_code==200
    db.rpc.assert_called_once_with('cancel_list_trace_as_operator',{'p_id':event,'p_request':trace,'p_operator':OPERATOR})

@pytest.mark.parametrize('result,status',[(None,503),({'blocked':'already_claimed'},409),({'event':{}},503)])
def test_unconfirmed_cancellation_not_success(client_db,result,status):
    client,db,_=client_db
    db.rpc.return_value.execute.return_value=SimpleNamespace(data=result)
    assert client.post(f'/api/operations/lists/tracing/{uuid4()}/cancel',json={'event_id':str(uuid4())},headers={'Authorization':'Bearer test'}).status_code==status

def test_unauthorized_operations_and_actor_spoofing_denied(client_db):
    client,db,rows=client_db
    assert client.get('/api/operations/lists/tracing').status_code==401
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists/tracing',headers={'Authorization':'Bearer test'}).status_code==403
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'admin'}])
    assert client.post(f'/api/operations/lists/tracing/{uuid4()}/cancel',json={'event_id':str(uuid4()),'operator_id':OPERATOR},headers={'Authorization':'Bearer test'}).status_code==422
    db.rpc.assert_not_called()
