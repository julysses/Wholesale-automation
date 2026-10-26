"""API -> real calculator -> real SQL workflow, with only PostgREST transport adapted.

Run with installed backend test dependencies through scripts/run_offline_tests.py.
The inherited runner creates an inert socket-only PostgreSQL cluster. This does
not claim real JWT signature, PostgREST, auth middleware or full-schema acceptance.
"""
import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from test_acquisition_workspace import WorkspaceTests, main, ROOT, PG, ADMIN, OTHER, WORKSPACE, LEAD, literal
sys.path.insert(0, str(ROOT))
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from web.api.acquisition_api import router

ANALYSIS = 'b0000000-0000-4000-8000-000000000001'
OFFER = 'c0000000-0000-4000-8000-000000000001'
EVENT = 'd0000000-0000-4000-8000-000000000001'
RPC_ARGS = {
 'reserve_acquisition_analysis': ['p_id','p_workspace','p_lead','p_inputs'],
 'read_acquisition_calculation': ['p_id','p_workspace'],
 'complete_acquisition_calculation': ['p_id','p_workspace','p_input_hash','p_outputs'],
 'propose_acquisition_offer': ['p_id','p_workspace','p_analysis','p_case','p_amount','p_note'],
 'review_acquisition_offer': ['p_id','p_workspace','p_offer','p_expected_sequence','p_status','p_note','p_review_notes'],
 'acquisition_offer_review_state': ['p_workspace','p_offer'],
}


def inputs():
    def fact(value):
        return {'value':str(value),'source':'Synthetic workflow evidence','basis':'estimate','confidence':'medium','as_of':'2026-01-01'}
    case={'strategy':'fix_and_flip',**{key:fact(value) for key,value in {
      'purchase_price':150000,'acquisition_closing':3000,'liens':2000,'holding_months':6,
      'holding_monthly_ex_interest':500,'offer_floor_fraction':'0.9','arv':300000,'repairs':30000,
      'contingency':3000,'selling_rate':'0.06','selling_fixed':2000,'target_profit':40000}.items()},
      'financing':{key:fact(value) for key,value in {'principal':120000,'average_balance':120000,
        'annual_rate':'0.12','points_rate':'0.02','other_fees':500}.items()}}
    return {'cases':{name:copy.deepcopy(case) for name in ['base','downside','upside']}}


class WorkflowTests(WorkspaceTests):
    def setUp(self):
        super().setUp()
        self.bind()
        self.requests=[]
        self.lose_completion_once=False
        self.environment=patch.dict(os.environ,{
            'ACQUISITION_ENABLED':'true','ACQUISITION_CALCULATOR_ENABLED':'true',
            'ACQUISITION_CALCULATOR_SERVICE_KEY':'synthetic-worker-key',
            'SUPABASE_URL':'https://workflow.example.test','SUPABASE_ANON_KEY':'synthetic-public-key',
            'PYTHON_DOTENV_DISABLED':'1',
        },clear=True)
        self.environment.start();self.addCleanup(self.environment.stop)
        original=httpx.AsyncClient
        self.transport=patch('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(self.handle),**kwargs))
        self.transport.start();self.addCleanup(self.transport.stop)
        app=FastAPI();app.include_router(router)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer synthetic-admin-session'}
        self.base=f'/api/acquisition/workspaces/{WORKSPACE}'

    def handle(self, request):
        self.requests.append((request.url.path,request.headers.get('authorization')))
        self.assertEqual(request.url.host,'workflow.example.test')
        identity,role={
            'Bearer synthetic-admin-session':(ADMIN,'authenticated'),
            'Bearer synthetic-other-session':(OTHER,'authenticated'),
            'Bearer synthetic-worker-key':(ADMIN,'service_role'),
        }[request.headers['authorization']]
        self.assertEqual(request.headers['apikey'],'synthetic-worker-key' if role=='service_role' else 'synthetic-public-key')
        if request.url.path.startswith('/rest/v1/rpc/'):
            name=request.url.path.rsplit('/',1)[-1]
            self.assertIn(name,RPC_ARGS)
            body=json.loads(request.content)
            self.assertEqual(set(body),set(RPC_ARGS[name]))
            args=[]
            for key in RPC_ARGS[name]:
                value=body[key]
                kind=('jsonb' if key in {'p_inputs','p_outputs','p_review_notes'} else 'uuid' if key in {'p_id','p_workspace','p_lead','p_analysis','p_offer'}
                      else 'integer' if key=='p_expected_sequence' else 'numeric' if key=='p_amount' else 'text')
                text=json.dumps(value) if kind=='jsonb' else str(value)
                args.append(f'{key}=>{literal(text)}::{kind}')
            query=f"SELECT public.{name}({','.join(args)})::text;"
        else:
            self.assertEqual(request.method,'GET')
            self.assertEqual(request.url.path,'/rest/v1/deal_analyses')
            allowed={'id','workspace_id','lead_id','property_id','acquisition_revision','acquisition_strategy','calculation_version','acquisition_status','acquisition_inputs','acquisition_outputs','analyzed_at'}
            fields=request.url.params['select'].split(',');self.assertTrue(set(fields)<=allowed)
            self.assertEqual(set(request.url.params),{'select','id','workspace_id','lead_id','limit'})
            filters=[]
            for key in ['id','workspace_id','lead_id']:
                op,value=request.url.params[key].split('.',1);self.assertEqual(op,'eq')
                filters.append(f'{key}={literal(value)}::uuid')
            self.assertEqual(request.url.params['limit'],'1')
            query=f"SELECT coalesce(jsonb_agg(to_jsonb(row)),'[]'::jsonb)::text FROM (SELECT {','.join(fields)} FROM public.deal_analyses WHERE {' AND '.join(filters)} LIMIT 1) row;"
        claims={'sub':identity,'session_id':identity,'aal':'aal2'}
        query=f'SET ROLE {role}; SET request.jwt.claims={literal(json.dumps(claims))}; '+query
        result=subprocess.run([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose',
            '-h',self.socket,'-U','test_admin','-d','acquisition_test'],input=query,text=True,capture_output=True,env=self.env)
        if result.returncode:
            match=re.search(r'ERROR:\s+([0-9A-Z]{5}):',result.stderr)
            if not match:raise AssertionError(result.stderr)
            code=match.group(1)
            return httpx.Response(403 if code=='42501' else 400,json={'code':code})
        if request.url.path.endswith('complete_acquisition_calculation') and self.lose_completion_once:
            self.lose_completion_once=False
            raise httpx.ReadTimeout('Synthetic lost response after real commit',request=request)
        return httpx.Response(200,json=json.loads(result.stdout.strip()))

    def save(self, body=None):
        response=self.client.post(f'{self.base}/leads/{LEAD}/underwriting/scenarios',headers=self.headers,
            json=body or {'id':ANALYSIS,'inputs':inputs()})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def proposal(self, identity=OFFER, amount='180000.00'):
        return self.client.post(self.base+'/offers',headers=self.headers,json={
            'id':identity,'analysis_id':ANALYSIS,'case':'base','amount':amount,'note':'Synthetic reviewed cost assumptions'})

    def test_real_calculation_persists_then_enters_offer_review(self):
        saved=self.save()['analysis']
        self.assertEqual(saved['acquisition_status'],'calculated')
        result=saved['acquisition_outputs']
        self.assertEqual(result['cases']['base']['mao'],'188900.00')
        self.assertEqual(result['cases']['base']['metrics']['profit'],'78900.00')
        self.assertTrue(result['persisted'])
        self.assertEqual(saved['acquisition_inputs']['cases']['base']['arv']['source'],'Synthetic workflow evidence')
        self.assertEqual(self.proposal(amount='188900.01').status_code,409)
        self.assertEqual(self.proposal().status_code,200)
        response=self.client.post(f'{self.base}/offers/{OFFER}/reviews',headers=self.headers,json={
          'id':EVENT,'expected_sequence':1,'status':'amount_approved','note':'Synthetic internal review',
          'review_notes':{key:'Synthetic review, final documentation pending' for key in ['title','liens','occupancy','valuation','repairs','financing','downside']}})
        self.assertEqual(response.status_code,200,response.text)
        state=self.client.get(f'{self.base}/offers/{OFFER}/state',headers=self.headers).json()
        self.assertTrue(state['amount_approval_current']);self.assertFalse(state['transmission_authorized'])
        self.assertEqual(self.save()['analysis']['acquisition_revision'],1)
        self.assertEqual(self.proposal().status_code,200)
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_analysis' AND action='calculated'"),'1')
        self.assertEqual(self.sql(f"SELECT coalesce(mao,-1) FROM leads WHERE id='{LEAD}'"),'-1')
        other={'Authorization':'Bearer synthetic-other-session'}
        self.assertEqual(self.client.get(f'{self.base}/offers/{OFFER}/state',headers=other).status_code,403)

    def test_missing_market_value_is_persisted_as_incomplete_and_cannot_propose(self):
        data=inputs()
        del data['cases']['downside']['arv']
        saved=self.save({'id':ANALYSIS,'inputs':data})['analysis']
        self.assertEqual(saved['acquisition_status'],'incomplete')
        self.assertIsNone(saved['acquisition_outputs']['cases']['downside']['mao'])
        self.assertEqual(self.proposal().status_code,409)
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations'),'0')

    def test_lost_completion_response_retry_reconciles_existing_revision(self):
        self.lose_completion_once=True
        response=self.save()
        self.assertEqual(response['analysis']['acquisition_status'],'calculated')
        self.assertEqual(response['calculation']['status'],'calculated')
        self.assertEqual(response['calculation']['reason'],'RECONCILED_FROM_SAVED_SCENARIO')
        self.assertEqual(self.save()['calculation']['status'],'calculated')
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses'),'1')
        completions=[path for path,token in self.requests if path.endswith('complete_acquisition_calculation')]
        self.assertEqual(len(completions),1)


if __name__=='__main__':
    raise SystemExit(main(WorkflowTests,[name for name in WorkflowTests.__dict__ if name.startswith('test_')]))
