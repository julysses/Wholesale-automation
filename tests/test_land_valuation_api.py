from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_offer_review_api import setup,OPERATOR
from web.api import land_valuation_api as api
HEADERS={'Authorization':'Bearer test'}

@pytest.fixture
def client_db(setup,monkeypatch):
    client,db,rows=setup;monkeypatch.setattr(api,'get_supabase_client',lambda:db);return client,db,rows

def payload():
    return {'direct_comp_details':[],'avg_house_arv':None,'house_comp_count':None,'tav':0,
            'tav_source':'manual','tav_assessment_date':None,'comp_notes':'Synthetic valuation'}

def body():
    return {'request_id':str(uuid4()),'expected_hash':'a'*64,'payload':payload()}

def test_read_requires_session_and_correlated_record(client_db):
    client,db,_=client_db;land=str(uuid4());url=f'/api/land-underwriting/valuations/{land}'
    assert client.get(url).status_code==401
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'land_lead_id':land,'snapshot_hash':'a'*64,'record_count':0,'comp':None,'outreach_authorized':False})
    result=client.get(url,headers=HEADERS);assert result.status_code==200 and result.headers['cache-control']=='no-store'
    db.rpc.assert_called_with('read_land_valuation',{'p_land':land,'p_operator':OPERATOR})
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'blocked':'land_missing'})
    assert client.get(url,headers=HEADERS).status_code==404


def test_save_uses_approved_actor_raw_inputs_and_exact_receipt(client_db):
    client,db,rows=client_db;rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    land=str(uuid4());comp=str(uuid4());request=body()
    saved={'id':request['request_id'],'land_lead_id':land,'comp_id':comp,'operator_id':OPERATOR,
           'expected_hash':request['expected_hash'],'payload':request['payload'],
           'saved_snapshot':{'land_lead_id':land,'comp':{'id':comp,'land_lead_id':land}}}
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'event':saved,'outreach_authorized':False})
    url=f'/api/land-underwriting/valuations/{land}'
    assert client.post(url,headers=HEADERS,json=request).status_code==200
    assert db.rpc.call_args.args[1]['p_payload']['tav']==0
    assert db.rpc.call_args.args[1]['p_operator']==OPERATOR
    saved['payload']={**request['payload'],'tav':100}
    assert client.post(url,headers=HEADERS,json=request).status_code==503
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'blocked':'valuation_changed'})
    assert client.post(url,headers=HEADERS,json=request).status_code==409


@pytest.mark.parametrize('change',[{'tav':-1},{'tav':True},{'tav':1.001},{'avg_house_arv':100000},
 {'house_comp_count':1.5},{'tav_assessment_date':'2999-01-01'},{'offer_price':10000},
 {'direct_comp_details':[{'address':' ','price':100}]},{'direct_comp_details':[{'address':'Example','price':0}]},
 {'direct_comp_details':[{'address':'Example','price':100,'date':'2026-02-30'}]},
 {'direct_comp_details':[{'address':'Example','price':100,'sqft':0}]},
 {'direct_comp_details':[{'address':'Example','price':100,'source_url':'javascript:alert(1)'}]},
 {'direct_comp_details':[],'tav':None}])
def test_invalid_inputs_rejected_before_database(client_db,change):
    client,db,_=client_db;request=body();request['payload'].update(change)
    assert client.post(f'/api/land-underwriting/valuations/{uuid4()}',headers=HEADERS,json=request).status_code==422
    db.rpc.assert_not_called()


def test_unknowns_remain_null_and_zero_distance_is_valid():
    value=api.ValuationInput.model_validate({**payload(),'direct_comp_details':[{'address':'Example','price':100,'distance_mi':0}]})
    row=value.model_dump(mode='json')['direct_comp_details'][0]
    assert row['sqft'] is None and row['date'] is None and row['source_url'] is None and row['distance_mi']==0
