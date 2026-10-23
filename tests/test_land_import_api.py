from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_offer_review_api import setup,OPERATOR
from web.api import land_import_api as api
HEADERS={'Authorization':'Bearer test'}

@pytest.fixture
def client_db(setup,monkeypatch):
    client,db,rows=setup
    monkeypatch.setattr(api,'get_supabase_client',lambda:db)
    return client,db,rows

def body():
    return {'request_id':str(uuid4()),'rows':[{'owner_name':'Synthetic Owner','property_address':'1 Test St','city':'Dallas','tav':0}]}

def receipt(request):
    rows=[{**row,'state':'TX'} for row in request['rows']]
    return {'receipt':{'id':request['request_id'],'operator_id':OPERATOR,'payload':rows,
        'result':{'imported':1,'existing':0,'rows':[{'land_lead_id':str(uuid4()),'task_id':str(uuid4()),'created':True}]}},
        'outreach_authorized':False,'replayed':False}

def test_requires_session_and_correlated_receipt(client_db):
    client,db,_=client_db;request=body()
    assert client.post('/api/land/imports',json=request).status_code==401
    expected=receipt(request);db.rpc.return_value.execute.return_value=SimpleNamespace(data=expected)
    response=client.post('/api/land/imports',json=request,headers=HEADERS)
    assert response.status_code==200
    db.rpc.assert_called_with('import_manual_land_leads',{'p_id':request['request_id'],'p_operator':OPERATOR,'p_rows':expected['receipt']['payload']})

@pytest.mark.parametrize('change',['request','operator','payload','counts','mapping','task','authorization'])
def test_unconfirmed_receipt_never_reports_success(client_db,change):
    client,db,_=client_db;request=body();saved=deepcopy(receipt(request));r=saved['receipt']
    if change=='request':r['id']=str(uuid4())
    if change=='operator':r['operator_id']=str(uuid4())
    if change=='payload':r['payload'][0]['city']='Austin'
    if change=='counts':r['result']['imported']=True
    if change=='mapping':r['result']['rows']=[]
    if change=='task':r['result']['rows'][0]['task_id']=None
    if change=='authorization':saved['outreach_authorized']=True
    db.rpc.return_value.execute.return_value=SimpleNamespace(data=saved)
    assert client.post('/api/land/imports',json=request,headers=HEADERS).status_code==503

@pytest.mark.parametrize('extra',[{'dnc':False},{'status':'new'},{'assigned_to':str(uuid4())},{'sms_sequence_active':True},
 {'owner_name':' '},{'city':' '},{'tav':-1},{'tav':True},{'lot_size_acres':0},{'state':'Texas'}])
def test_input_cannot_authorize_outreach_or_overwrite_work(client_db,extra):
    client,db,_=client_db;request=body();request['rows'][0].update(extra)
    assert client.post('/api/land/imports',json=request,headers=HEADERS).status_code==422
    db.rpc.assert_not_called()

def test_storage_conflict_and_uncertainty_do_not_replay(client_db):
    client,db,_=client_db;request=body();error=RuntimeError('ambiguous fixture');error.code='22023'
    db.rpc.return_value.execute.side_effect=error
    assert client.post('/api/land/imports',json=request,headers=HEADERS).status_code==409
    db.rpc.return_value.execute.side_effect=RuntimeError('lost response')
    assert client.post('/api/land/imports',json=request,headers=HEADERS).status_code==503
    assert db.rpc.call_count==2
