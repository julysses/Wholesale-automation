"""HTTP receipt validation and provider parsing. Persistence uses the real-SQL harness."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import Request
from fastapi.testclient import TestClient
import pytest

from web.app import app
from web.auth import require_operator
from web import api
from web.api import csv_import

OWNER='00000000-0000-4000-8000-000000000777'


@pytest.fixture
def setup(monkeypatch):
    calls=[]
    def receipt(params):
        rows=params['p_rows']; options=params['p_options']; n=len(rows)
        return {'receipt':{'id':params['p_id'],'operator_id':params['p_operator'],'payload':rows,'options':options,
            'result':{'imported':n,'existing':0,'owner_review':0,'intake_owner_id':OWNER,
                'scored':n if options['score_on_import'] and options['engine']=='rules' else 0,'scoring_eligible':n,
                'scoring_state':'disabled' if not options['score_on_import'] else 'completed' if options['engine']=='rules' else 'pending',
                'list_id':str(uuid4()) if options['list_name'] else None,
                'rows':[{'lead_id':str(uuid4()),'task_id':str(uuid4()),'created':True} for _ in rows]}},
            'replayed':False,'outreach_authorized':False}
    outcome=Mock(side_effect=receipt)
    def rpc(name,params):
        calls.append((name,params))
        return SimpleNamespace(execute=lambda:SimpleNamespace(data=outcome(params)))
    db=SimpleNamespace(rpc=rpc)
    monkeypatch.setattr(csv_import,'get_supabase_client',lambda:db)
    def approved(request:Request):request.state.user_id=OWNER
    app.dependency_overrides[require_operator]=approved
    yield SimpleNamespace(client=TestClient(app),calls=calls,outcome=outcome,receipt=receipt,db=db)
    app.dependency_overrides.pop(require_operator,None)


def body(**overrides):
    return {'request_id':str(uuid4()),'rows':[{'property_address':'123 Main St','city':'Dallas'}],**overrides}


def test_verified_actor_and_normalized_consolidation_reach_one_rpc(setup):
    payload=body(rows=[{'property_address':'123 Main Street','city':'Dallas','sources':['tax'],'owner_phone_1':'(214) 555-0100','asking_price':'$0.00'},
        {'property_address':'123 Main St.','city':'DALLAS','sources':['vacant'],'owner_email':'owner@example.test'},
        {'property_address':'Missing city'}])
    response=setup.client.post('/api/ai/import-master-list',json=payload)
    assert response.status_code==200,response.text
    assert response.json()['consolidated_rows']==1 and response.json()['skipped']==1
    assert len(setup.calls)==1 and setup.calls[0][0]=='import_csv_leads'
    params=setup.calls[0][1]
    assert params['p_operator']==OWNER and params['p_id']==payload['request_id']
    assert params['p_rows'][0]['source']=='tax | vacant'
    assert params['p_rows'][0]['owner_phone_1']=='2145550100' and params['p_rows'][0]['asking_price']==0
    assert params['p_options']['engine']=='rules'


def test_missing_actor_refuses_before_any_rpc(setup):
    app.dependency_overrides[require_operator]=lambda:None
    assert setup.client.post('/api/ai/import-master-list',json=body()).status_code==401
    assert not setup.calls


def test_legacy_same_normalized_payload_has_stable_reference(setup):
    payload=body();payload.pop('request_id')
    first=setup.client.post('/api/ai/import-master-list',json=payload)
    second=setup.client.post('/api/ai/import-master-list',json=payload)
    assert first.status_code==second.status_code==200
    assert setup.calls[0][1]['p_id']==setup.calls[1][1]['p_id']


@pytest.mark.parametrize('value',[-1,'-$200','(200)','1.2.3','1,23','NaN','Infinity',True])
def test_bad_price_never_reaches_database(setup,value):
    assert setup.client.post('/api/ai/import-master-list',json=body(rows=[{'property_address':'1 Test','city':'Dallas','asking_price':value}])).status_code==422
    assert not setup.calls


@pytest.mark.parametrize(('field','value'),[('bedrooms',1.5),('sqft','2,147,483,648'),('bathrooms','100'),('bathrooms','1.55'),('asking_price','1.001'),('state','Texas')])
def test_invalid_range_precision_or_state_refuses_before_database(setup,field,value):
    assert setup.client.post('/api/ai/import-master-list',json=body(rows=[{'property_address':'1 Test','city':'Dallas',field:value}])).status_code==422
    assert not setup.calls


def test_unknown_engine_never_selects_paid_provider(setup):
    assert setup.client.post('/api/ai/import-master-list',json=body(engine='not-a-real-engine')).status_code==422
    assert not setup.calls


@pytest.mark.parametrize('fault',['reference','operator','payload','options','count','boolean_count','owner','task','created','outreach','replayed','scoring','duplicate_ids'])
def test_uncorrelated_or_incomplete_receipt_is_not_success(setup,fault):
    def corrupted(params):
        value=setup.receipt(params);receipt=value['receipt'];result=receipt['result']
        if fault=='reference':receipt['id']=str(uuid4())
        elif fault=='operator':receipt['operator_id']=str(uuid4())
        elif fault=='payload':receipt['payload']=[]
        elif fault=='options':receipt['options']={}
        elif fault=='count':result['imported']=0
        elif fault=='boolean_count':result['imported']=True
        elif fault=='owner':result['intake_owner_id']='not-an-owner'
        elif fault=='task':result['rows'][0]['task_id']=None
        elif fault=='created':result['rows'][0]['created']='true'
        elif fault=='outreach':value['outreach_authorized']=True
        elif fault=='replayed':value['replayed']='true'
        elif fault=='scoring':result['scoring_state']='pending'
        else:result['rows'].append(deepcopy(result['rows'][0]))
        return value
    setup.outcome.side_effect=corrupted
    assert setup.client.post('/api/ai/import-master-list',json=body()).status_code==503
    assert len(setup.calls)==1


@pytest.mark.parametrize(('code','expected'),[('22023',409),('22P02',422),('22003',422),('23514',422),('PGRST202',503)])
def test_rpc_failure_never_falls_back_to_non_atomic_writes(setup,code,expected):
    error=RuntimeError('synthetic unavailable RPC');error.code=code
    setup.outcome.side_effect=error
    assert setup.client.post('/api/ai/import-master-list',json=body()).status_code==expected
    assert len(setup.calls)==1


@pytest.mark.parametrize('fault',[None,'foreign','missing','duplicate','boolean','out_of_range','partial_stop'])
def test_paid_csv_parser_is_complete_correlated_and_single_attempt(monkeypatch,fault):
    lead=str(uuid4()); other=str(uuid4())
    result={'lead_id':lead,**{k:3 for k in ['score_motivation','score_timeline','score_equity','score_condition','score_flexibility']},'qualification_summary':'Evidence summary'}
    rows=[result]
    if fault=='foreign':result['lead_id']=other
    elif fault=='missing':rows=[]
    elif fault=='duplicate':rows=[result,result]
    elif fault=='boolean':result['score_motivation']=True
    elif fault=='out_of_range':result['score_equity']=4
    sdk=Mock();sdk.with_options.return_value=sdk
    sdk.messages.create.return_value=SimpleNamespace(stop_reason='max_tokens' if fault=='partial_stop' else 'end_turn',content=[SimpleNamespace(text=json.dumps(rows))])
    monkeypatch.setattr(api,'_get_client',lambda:sdk)
    if fault:
        with pytest.raises(ValueError):api._score_imported_leads_with_claude([{'lead_id':lead}],single_attempt=True)
    else:
        assert api._score_imported_leads_with_claude([{'lead_id':lead}],single_attempt=True)[lead]['score_motivation']==3
    sdk.with_options.assert_called_once_with(max_retries=0)
    sdk.messages.create.assert_called_once()
