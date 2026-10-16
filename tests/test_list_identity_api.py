from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_trace_operations_api import client_db
from tests.list_api_fixtures import setup, OPERATOR

def payload():
    return {'run_id':str(uuid4()),'batch_index':0,'ordinal':0,'county':'Dallas',
        'evidence_url':'https://www.dallascad.org/synthetic','review':{
        'source_fingerprint':'a'*32,'notes':'Official situs and account match.',
        'identity':{'property_address':'1 Synthetic Site','city':'Dallas','state':'TX','zip':'75201','parcel_id':None,'unit':None}}}

def test_identity_uses_session_actor_and_defaults_signal_inactive(client_db):
    client,db,_=client_db;body=payload()
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={
        'property_id':str(uuid4()),'lead_id':str(uuid4()),'outreach_authorized':False,
        **{k:body[k] for k in ['run_id','batch_index','ordinal','review']}})
    assert client.post('/api/operations/lists/resolve',json=body,headers={'Authorization':'Bearer test'}).status_code==200
    name,params=db.rpc.call_args.args
    assert name=='resolve_reviewed_list_record' and params['p_operator']==OPERATOR
    assert params['p_active'] is False and params['p_review']==body['review']

@pytest.mark.parametrize('change',[{'operator_id':OPERATOR},{'review':None},{'active_signal':'true'}, {'review':{'identity':{}}}])
def test_malformed_or_spoofed_identity_denied(client_db,change):
    client,db,_=client_db
    assert client.post('/api/operations/lists/resolve',json={**payload(),**change},headers={'Authorization':'Bearer test'}).status_code==422
    db.rpc.assert_not_called()

def test_identity_unconfirmed_ack_not_success_and_nonadmin_denied(client_db):
    client,db,rows=client_db
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'property_id':str(uuid4()),'lead_id':str(uuid4()),'outreach_authorized':False})
    assert client.post('/api/operations/lists/resolve',json=payload(),headers={'Authorization':'Bearer test'}).status_code==503
    db.rpc.reset_mock();rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.post('/api/operations/lists/resolve',json=payload(),headers={'Authorization':'Bearer test'}).status_code==403
    db.rpc.assert_not_called()

def test_foreclosure_actions_validates_filters_and_admin_access(client_db):
    client,db,rows=client_db
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'total':1,'items':[]})
    headers={'Authorization':'Bearer test'}
    assert client.get('/api/operations/lists/foreclosures?county=Collin&offset=50',headers=headers).status_code==200
    name,params=db.rpc.call_args.args
    assert name=='foreclosure_daily_actions' and params['p_county']=='Collin' and params['p_offset']==50
    db.rpc.reset_mock()
    assert client.get('/api/operations/lists/foreclosures?county=Other',headers=headers).status_code==422
    db.rpc.assert_not_called()
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists/foreclosures',headers=headers).status_code==403
    db.rpc.assert_not_called()

def test_review_source_filter_preserves_offset_and_admin_access(client_db):
    client,db,rows=client_db
    headers={'Authorization':'Bearer test'}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'reviews':[], 'review_count':3, 'total_review_count':108})
    response=client.get('/api/operations/lists?source_key=tx-dallas-tax_delinquent&offset=100',headers=headers)
    assert response.status_code==200 and response.json()['total_review_count']==108
    name,params=db.rpc.call_args.args
    assert name=='list_pipeline_snapshot_filtered' and params['p_source_key']=='tx-dallas-tax_delinquent' and params['p_offset']==100
    assert client.get('/api/operations/lists',headers=headers).status_code==200
    assert db.rpc.call_args.args[1]['p_source_key'] is None
    db.rpc.reset_mock()
    for suffix in ['source_key=not-a-source','offset=-1']:
        assert client.get('/api/operations/lists?'+suffix,headers=headers).status_code==422
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists?source_key=tx-collin-tax_delinquent',headers=headers).status_code==403
    db.rpc.assert_not_called()

def test_propstream_action_validates_actor_and_matching_ack(client_db):
    client,db,rows=client_db;headers={'Authorization':'Bearer test'}
    event,request,lead=str(uuid4()),str(uuid4()),str(uuid4())
    body={'event_id':event,'request_id':request,'lead_id':lead,'action':'start','payload':{'input_hash':'a'*64}}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={**{k:body[k] for k in ['event_id','request_id','lead_id','action']},'operator_id':OPERATOR,'outreach_authorized':False})
    assert client.post('/api/operations/lists/propstream/actions',json=body,headers=headers).status_code==200
    name,params=db.rpc.call_args.args
    assert name=='propstream_handoff_action' and params['p_operator']==OPERATOR
    db.rpc.reset_mock()
    assert client.post('/api/operations/lists/propstream/actions',json={**body,'payload':{'input_hash':'a'*64,'send':True}},headers=headers).status_code==422
    db.rpc.assert_not_called()
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists/propstream',headers=headers).status_code==403
    db.rpc.assert_not_called()

def test_bulk_handoff_session_actor_and_limit(client_db):
    client,db,_=client_db;headers={'Authorization':'Bearer test'}
    item={'event_id':str(uuid4()),'request_id':str(uuid4()),'lead_id':str(uuid4()),'action':'start','payload':{'input_hash':'a'*64}}
    body={'batch_id':str(uuid4()),'items':[item]}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'batch_id':body['batch_id'],'operator_id':OPERATOR,'count':1,'outreach_authorized':False})
    assert client.post('/api/operations/lists/propstream/batches',json=body,headers=headers).status_code==200
    assert db.rpc.call_args.args[1]['p_operator']==OPERATOR
    db.rpc.reset_mock()
    assert client.post('/api/operations/lists/propstream/batches',json={**body,'items':[]},headers=headers).status_code==422
    db.rpc.assert_not_called()

def test_capture_status_uses_session_actor_and_denies_nonadmin(client_db):
    client,db,rows=client_db;headers={'Authorization':'Bearer test'}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'counties':[],'verification_granted':False})
    assert client.get('/api/operations/lists/captures',headers=headers).status_code==200
    assert db.rpc.call_args.args==('foreclosure_capture_status',{'p_operator':OPERATOR})
    db.rpc.reset_mock();rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists/captures',headers=headers).status_code==403
    db.rpc.assert_not_called()
