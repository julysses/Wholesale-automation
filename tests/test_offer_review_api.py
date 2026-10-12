"""Offer review access, exact acknowledgement and recovery contracts."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from web.app import app
from web import auth
from web.api import offer_review_api as offers

OPERATOR='00000000-0000-4000-8000-000000000001'
LEAD=str(uuid4())
@pytest.fixture
def setup(monkeypatch):
    db=MagicMock()
    db.auth.get_user.return_value=SimpleNamespace(user=SimpleNamespace(id=OPERATOR))
    rows=db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'admin'}])
    monkeypatch.setattr(auth,'get_supabase_client',lambda:db)
    monkeypatch.setattr(offers,'get_supabase_client',lambda:db)
    return TestClient(app),db,rows

def payload():
    identity=str(uuid4())
    return {'request_id':identity,'revision_id':identity,'action':'draft','expected_version':0,
            'terms':{'price':'125000.00','closing_date':'2099-12-31','expires_at':'2099-10-01T00:00:00Z',
                     'recipient':'test@example.invalid','channel':'email','conditions':'Reviewed terms'}}

def test_access_denied_before_rpc(setup):
    client,db,rows=setup
    assert client.get('/api/operations/offers/'+LEAD).status_code==401
    rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.post('/api/operations/offers/'+LEAD,json=payload(),headers={'Authorization':'Bearer test'}).status_code==403
    db.rpc.assert_not_called()

def test_operator_identity_and_exact_receipt(setup):
    client,db,_=setup
    def response(name,params):
        assert params['p_operator']==OPERATOR
        return SimpleNamespace(execute=lambda:SimpleNamespace(data={
          'event':{'id':params['p_id'],'lead_id':LEAD,'operator_id':OPERATOR,'action':params['p_action'],
                   'revision_id':params['p_revision'],'expected_version':params['p_expected'],'terms':params['p_terms']},
          'current':{'lead_id':LEAD,'version':1,'outbound_enabled':False},'replayed':False}))
    db.rpc.side_effect=response
    result=client.post('/api/operations/offers/'+LEAD,json=payload(),headers={'Authorization':'Bearer test'})
    assert result.status_code==200
    assert result.json()['current']['outbound_enabled'] is False

@pytest.mark.parametrize('result,status',[(None,503),({},503),({'conflict':True},409),({'expired':True},422),({'invalid':True},422),({'missing':True},404)])
def test_unconfirmed_or_rejected_write_not_success(setup,result,status):
    client,db,_=setup
    db.rpc.return_value.execute.return_value=SimpleNamespace(data=result)
    assert client.post('/api/operations/offers/'+LEAD,json=payload(),headers={'Authorization':'Bearer test'}).status_code==status

@pytest.mark.parametrize('change',[{'operator_id':OPERATOR},{'approved':True},{'action':'approve'}, {'terms':None}])
def test_request_cannot_claim_identity_approval_or_replace_decision_terms(setup,change):
    client,db,_=setup
    assert client.post('/api/operations/offers/'+LEAD,json={**payload(),**change},headers={'Authorization':'Bearer test'}).status_code==422
    db.rpc.assert_not_called()

@pytest.mark.parametrize('result,status',[
 ({'lead_id':LEAD,'events':[],'next_before':None},200),
 ({'lead_id':str(uuid4()),'events':[],'next_before':None},503),
 ({'lead_id':LEAD,'events':[{'lead_id':LEAD,'expected_version':5}],'next_before':None},503),
 ({'lead_id':LEAD,'events':[],'next_before':0},503),
])
def test_history_identity_cursor_and_derived_operator(setup,result,status):
    client,db,_=setup
    db.rpc.return_value.execute.return_value=SimpleNamespace(data=result)
    response=client.get('/api/operations/offers/'+LEAD+'/history?before=5',headers={'Authorization':'Bearer test'})
    assert response.status_code==status
    db.rpc.assert_called_once_with('offer_review_history',{'p_lead':LEAD,'p_before':5,'p_operator':OPERATOR})
