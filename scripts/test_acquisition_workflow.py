"""Application workflows against real SQL; PostgREST adapted and Meta simulated.

Run with installed backend test dependencies through scripts/run_offline_tests.py.
The inherited runner creates an inert socket-only PostgreSQL cluster. This does
not claim real JWT signature, PostgREST, auth middleware or full-schema acceptance.
"""
import hashlib
import hmac
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
from web.api.acquisition_webhooks import router as facebook_router

ANALYSIS = 'b0000000-0000-4000-8000-000000000001'
OFFER = 'c0000000-0000-4000-8000-000000000001'
EVENT = 'd0000000-0000-4000-8000-000000000001'
RPC_ARGS = {
 'acquisition_cost_evidence':['p_workspace','p_campaign','p_start','p_end','p_as_of'],
 'acquisition_property_source_touches':['p_workspace','p_lead','p_after','p_limit'],
 'capture_acquisition_source_campaign':['p_id','p_workspace','p_source','p_link_review'],
 'acquisition_campaign_link_state':['p_workspace','p_intake'],
 'review_acquisition_campaign_link':['p_id','p_workspace','p_intake','p_expected_sequence','p_preparation_hash','p_action','p_campaign','p_ad_account','p_evidence_ref','p_note'],
 'create_acquisition_campaign':['p_id','p_workspace','p_name','p_channel','p_budget_cents','p_currency'],
 'recover_acquisition_inquiry': ['p_id','p_workspace','p_receipt','p_expected_updated_at','p_expected_reason','p_note','p_evidence_ref'],
 'reserve_acquisition_intake_analysis': ['p_id','p_workspace','p_intake','p_evidence_hash','p_inputs'],
 'acquisition_intake_analysis_state': ['p_workspace','p_analysis'],
 'acquisition_intake_qualification_state': ['p_workspace','p_intake'],
 'record_acquisition_intake_assessment': ['p_id','p_workspace','p_intake','p_expected_sequence','p_evidence_hash'],
 'acquisition_intake_identity_state': ['p_workspace','p_intake','p_target'],
 'review_acquisition_intake_identity': ['p_id','p_workspace','p_intake','p_expected_sequence','p_preparation_hash','p_action','p_target','p_target_hash','p_property_basis','p_property_evidence_ref','p_seller_evidence_ref','p_note'],
 'acquisition_intake_candidates': ['p_workspace','p_intake','p_limit'],
 'acquisition_inquiry_health': ['p_workspace','p_after','p_limit'],
 'accept_facebook_acquisition_batch': ['p_events','p_raw_body'],
 'claim_acquisition_events': ['p_integration','p_limit','p_lease_seconds'],
 'defer_acquisition_event': ['p_receipt','p_lease','p_outcome','p_reason'],
 'complete_facebook_acquisition_intake': ['p_receipt','p_lease','p_prepared'],
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
        self.lose_facebook_reply=None
        self.provider_error=None
        self.provider_form="200"
        self.disable_during_retrieval=False
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
        app=FastAPI();app.include_router(router);app.include_router(facebook_router)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer synthetic-admin-session'}
        self.base=f'/api/acquisition/workspaces/{WORKSPACE}'

    def handle(self, request):
        self.requests.append((request.url.path,request.headers.get('authorization')))
        if request.url.host=='graph.facebook.com':
            self.assertEqual(request.method,'GET')
            self.assertEqual(request.headers['authorization'],'Bearer synthetic-page-key')
            self.assertNotIn('apikey',request.headers)
            self.assertEqual(request.url.params['fields'].split(',')[0],'id')
            if self.disable_during_retrieval:
                self.sql("UPDATE private.acquisition_integrations SET enabled=false WHERE account_id='100';")
            if self.provider_error:
                return httpx.Response(400,json={'error':{'code':self.provider_error,'message':'Synthetic private provider detail'}})
            return httpx.Response(200,json={'id':request.url.path.split('/')[-1],'form_id':self.provider_form,
                'created_time':'2026-10-26T12:00:00Z',
                'field_data':getattr(self,'provider_fields',[{'name':'phone_number','values':['2145550101']}]),
                'custom_disclaimer_responses':[{'checkbox_key':'sms','is_checked':False}], **getattr(self,'provider_metadata',{})})
        self.assertEqual(request.url.host,'workflow.example.test')
        identity,role={
            'Bearer synthetic-admin-session':(ADMIN,'authenticated'),
            'Bearer synthetic-other-session':(OTHER,'authenticated'),
            'Bearer synthetic-worker-key':(ADMIN,'service_role'),
            'Bearer synthetic-ingestion-key':(ADMIN,'service_role'),
            'Bearer synthetic-facebook-worker-key':(ADMIN,'service_role'),
        }[request.headers['authorization']]
        self.assertEqual(request.headers['apikey'],request.headers['authorization'].removeprefix('Bearer ') if role=='service_role' else 'synthetic-public-key')
        if request.url.path.startswith('/rest/v1/rpc/'):
            name=request.url.path.rsplit('/',1)[-1]
            self.assertIn(name,RPC_ARGS)
            body=json.loads(request.content)
            self.assertEqual(set(body),set(RPC_ARGS[name]))
            args=[]
            for key in RPC_ARGS[name]:
                value=body[key]
                kind=('jsonb' if key in {'p_inputs','p_outputs','p_review_notes','p_events','p_prepared'} else 'uuid' if key in {'p_id','p_workspace','p_lead','p_analysis','p_offer','p_integration','p_receipt','p_lease','p_after','p_intake','p_target','p_campaign','p_source','p_link_review'}
                      else 'date' if key in {'p_start','p_end'} else 'timestamptz' if key in {'p_expected_updated_at','p_as_of'} else 'bytea' if key=='p_raw_body' else 'integer' if key in {'p_expected_sequence','p_limit','p_lease_seconds'} else 'bigint' if key=='p_budget_cents' else 'numeric' if key=='p_amount' else 'text')
                text=json.dumps(value) if kind=='jsonb' else str(value)
                args.append(f'{key}=>NULL::{kind}' if value is None else f'{key}=>{literal(text)}::{kind}')
            query=f"SELECT public.{name}({','.join(args)})::text;"
        elif request.url.path in ('/rest/v1/acquisition_lead_sources','/rest/v1/acquisition_source_campaign_reviews'):
            self.assertEqual(request.method,'GET')
            table=request.url.path.rsplit('/',1)[-1]
            fields=('id,workspace_id,lead_id,receipt_id,integration_id,source_type,preparation_hash,external_lead_id,form_id,external_campaign_id,adset_id,ad_id,submitted_at_raw,utm_data,projection_version,recorded_at'
                    if table=='acquisition_lead_sources' else 'id,workspace_id,source_id,link_review_id,campaign_id,preparation_hash,created_at')
            self.assertEqual(request.url.params['select'],fields)
            relation='lead_id' if table=='acquisition_lead_sources' else 'source_id'
            self.assertTrue(set(request.url.params)<={'select','workspace_id',relation,'order','limit','id','link_review_id'})
            self.assertEqual(request.url.params['order'],'id')
            filters=[]
            for key in ('workspace_id',relation):
                op,value=request.url.params[key].split('.',1); self.assertEqual(op,'eq'); filters.append(f'{key}={literal(value)}::uuid')
            if 'id' in request.url.params:
                op,value=request.url.params['id'].split('.',1); self.assertEqual(op,'gt'); filters.append(f'id>{literal(value)}::uuid')
            if 'link_review_id' in request.url.params:
                self.assertEqual(table,'acquisition_source_campaign_reviews')
                op,value=request.url.params['link_review_id'].split('.',1); self.assertEqual(op,'eq'); filters.append(f'link_review_id={literal(value)}::uuid')
            limit=int(request.url.params['limit']); self.assertTrue(1<=limit<=51)
            query=f"SELECT coalesce(jsonb_agg(to_jsonb(row)),'[]'::jsonb)::text FROM (SELECT {fields} FROM public.{table} WHERE {' AND '.join(filters)} ORDER BY id LIMIT {limit}) row;"
        elif request.url.path=='/rest/v1/acquisition_campaign_links':
            self.assertEqual(request.method,'GET')
            fields='id,workspace_id,integration_id,external_campaign_id,sequence,action,campaign_id,ad_account_id,intake_id,evidence_ref,review_note,created_at'
            self.assertEqual(request.url.params['select'],fields)
            self.assertTrue(set(request.url.params)<={'select','workspace_id','integration_id','external_campaign_id','order','limit','sequence'})
            self.assertEqual(request.url.params['order'],'sequence.desc')
            filters=[]
            for key in ('workspace_id','integration_id','external_campaign_id'):
                op,value=request.url.params[key].split('.',1); self.assertEqual(op,'eq')
                filters.append(f'{key}={literal(value)}')
            if 'sequence' in request.url.params:
                op,value=request.url.params['sequence'].split('.',1); self.assertEqual(op,'lt'); filters.append(f'sequence<{int(value)}')
            limit=int(request.url.params['limit']); self.assertTrue(1<=limit<=50)
            query=f"SELECT coalesce(jsonb_agg(to_jsonb(row)),'[]'::jsonb)::text FROM (SELECT {fields} FROM public.acquisition_campaign_links WHERE {' AND '.join(filters)} ORDER BY sequence DESC LIMIT {limit}) row;"
        elif request.url.path=='/rest/v1/ad_campaigns':
            self.assertEqual(request.method,'GET')
            self.assertEqual(request.url.params['select'],'id,name,workspace_id,status,acquisition_channel,acquisition_budget_cents,acquisition_currency,created_at')
            self.assertTrue(set(request.url.params)<={'select','workspace_id','order','limit','id'})
            self.assertEqual(request.url.params['order'],'id')
            op,workspace=request.url.params['workspace_id'].split('.',1);self.assertEqual(op,'eq')
            filters=[f'workspace_id={literal(workspace)}::uuid']
            if 'id' in request.url.params:
                op,value=request.url.params['id'].split('.',1);self.assertEqual(op,'gt')
                filters.append(f'id>{literal(value)}::uuid')
            limit=int(request.url.params['limit']);self.assertTrue(1<=limit<=51)
            query=f"SELECT coalesce(jsonb_agg(to_jsonb(row)),'[]'::jsonb)::text FROM (SELECT {request.url.params['select']} FROM public.ad_campaigns WHERE {' AND '.join(filters)} ORDER BY id LIMIT {limit}) row;"
        elif request.url.path=='/rest/v1/acquisition_analysis_intakes':
            self.assertEqual(request.method,'GET')
            self.assertEqual(request.url.params['select'],'analysis_id,intake_id,assessment_id,evidence_hash')
            self.assertEqual(set(request.url.params),{'select','workspace_id','analysis_id','limit'})
            self.assertEqual(request.url.params['limit'],'1')
            filters=[]
            for key in ('workspace_id','analysis_id'):
                op,value=request.url.params[key].split('.',1);self.assertEqual(op,'eq')
                filters.append(f'{key}={literal(value)}::uuid')
            query=f"SELECT coalesce(jsonb_agg(to_jsonb(row)),'[]'::jsonb)::text FROM (SELECT analysis_id,intake_id,assessment_id,evidence_hash FROM public.acquisition_analysis_intakes WHERE {' AND '.join(filters)} LIMIT 1) row;"
        elif request.url.path=='/rest/v1/seller_intakes':
            self.assertEqual(request.method,'GET')
            allowed={'id','lead_id','classification','created_at','prepared_answers','preparation_hash','normalization_notes'}
            fields=request.url.params['select'].split(',');self.assertTrue(set(fields)<=allowed)
            self.assertTrue(set(request.url.params)<={'select','workspace_id','id','limit','order'})
            op,workspace=request.url.params['workspace_id'].split('.',1);self.assertEqual(op,'eq')
            filters=[f'workspace_id={literal(workspace)}::uuid']
            if 'id' in request.url.params:
                op,value=request.url.params['id'].split('.',1);self.assertIn(op,('eq','gt'))
                filters.append(f"id{'=' if op=='eq' else '>'}{literal(value)}::uuid")
            if 'order' in request.url.params:self.assertEqual(request.url.params['order'],'id')
            limit=int(request.url.params['limit']);self.assertTrue(1<=limit<=51)
            query=f"SELECT coalesce(jsonb_agg(to_jsonb(row)),'[]'::jsonb)::text FROM (SELECT {','.join(fields)} FROM public.seller_intakes WHERE {' AND '.join(filters)} ORDER BY id LIMIT {limit}) row;"
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
        if request.url.path.endswith('/'+str(self.lose_facebook_reply)):
            self.lose_facebook_reply=None
            raise httpx.ReadTimeout('Synthetic lost Facebook reply after real commit',request=request)
        return httpx.Response(200,json=json.loads(result.stdout.strip()))

    def configure_facebook(self):
        self.inbox_config(account='100')
        integration=self.sql("SELECT id FROM private.acquisition_integrations WHERE account_id='100';")
        os.environ.update({
            'FACEBOOK_ACQUISITION_INGESTION_ENABLED':'true',
            'ACQUISITION_INGESTION_SERVICE_KEY':'synthetic-ingestion-key',
            'ACQUISITION_FACEBOOK_APP_SECRET':'synthetic-app-secret',
            'ACQUISITION_FACEBOOK_VERIFY_TOKEN':'synthetic-verify',
            'ACQUISITION_FACEBOOK_WORKER_ENABLED':'true',
            'ACQUISITION_FACEBOOK_WORKER_TRIGGER_SECRET':'synthetic-trigger',
            'ACQUISITION_FACEBOOK_WORKER_SERVICE_KEY':'synthetic-facebook-worker-key',
            'ACQUISITION_FACEBOOK_PAGE_TOKEN':'synthetic-page-key',
            'ACQUISITION_FACEBOOK_PAGE_ID':'100',
            'ACQUISITION_FACEBOOK_INTEGRATION_ID':integration,
            'ACQUISITION_FACEBOOK_GRAPH_VERSION':'v26.0',
        })

    def facebook_delivery(self, ids=('1',), tamper=False, metadata=None):
        body=json.dumps({'object':'page','entry':[{'id':'100','changes':[
            {'field':'leadgen','value':{'leadgen_id':identity,'form_id':'200',**(metadata or {})}} for identity in ids]}]}).encode()
        signature='sha256='+hmac.new(b'synthetic-app-secret',body,hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/facebook/acquisition',content=body+(b' ' if tamper else b''),
                                headers={'X-Hub-Signature-256':signature})

    def facebook_worker(self):
        return self.client.post('/webhooks/facebook/acquisition/worker',headers={'Authorization':'Bearer synthetic-trigger'})

    def test_facebook_http_to_real_intake_and_evidence_isolated(self):
        self.configure_facebook()
        self.assertEqual(self.facebook_delivery(('1','2')).status_code,200)
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='facebook_acquisition'"),'0')
        for _ in range(2):
            response=self.facebook_worker()
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['classification'],'incomplete')
        self.assertEqual(self.facebook_worker().json(),{'status':'idle'})
        self.assertEqual(self.sql('SELECT count(DISTINCT lead_id) FROM seller_intakes'),'2')
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='facebook_acquisition' AND owner_phone_1='+12145550101' AND sms_sequence_active=false AND email_sequence_active=false AND ai_calling_paused=true"),'2')
        self.assertEqual(self.sql("SELECT count(*) FROM seller_intakes WHERE prepared_answers->'provider_evidence'->'custom_disclaimer_responses'->0->'is_checked'='false'::jsonb"),'2')
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes',user=ADMIN),'2')
        first_page=self.client.get(self.base+'/intakes?limit=1',headers=self.headers)
        self.assertEqual(first_page.status_code,200,first_page.text)
        intake=first_page.json()['items'][0]['id']
        self.assertEqual(first_page.json()['next_after'],intake)
        next_page=self.client.get(self.base+f'/intakes?limit=1&after={intake}',headers=self.headers).json()
        self.assertEqual(len(next_page['items']),1); self.assertIsNone(next_page['next_after'])
        self.assertNotEqual(next_page['items'][0]['id'],intake)
        detail=self.client.get(self.base+f'/intakes/{intake}',headers=self.headers)
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['prepared_answers']['answers']['phone'],'2145550101')
        self.assertEqual(self.client.get(self.base+f'/intakes/{intake}',headers={'Authorization':'Bearer synthetic-other-session'}).status_code,404)

        response=self.client.get(f'{self.base}/intakes/{intake}/candidates',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        candidates=response.json()['items']
        self.assertEqual(len(candidates),2) # Existing scoped lead plus the other native inquiry.
        self.assertTrue(all(row['match_basis']=='CONTACT_ONLY' and not row['merge_authorized'] for row in candidates))
        self.assertEqual(sum(row['previous_intake'] for row in candidates),1)
        identity_path=f'{self.base}/intakes/{intake}'
        review_state=self.client.get(identity_path+f'/identity-state?target={LEAD}',headers=self.headers).json()
        review={'id':'72000000-0000-4000-8000-000000000001','expected_sequence':review_state['sequence'],
            'preparation_hash':review_state['preparation_hash'],'action':'repeat_inquiry','target_lead_id':LEAD,
            'target_hash':review_state['target_hash'],'property_basis':'parcel_document',
            'property_evidence_ref':'synthetic-property-diligence-42','seller_evidence_ref':'synthetic-seller-diligence-42',
            'review_note':'Independent synthetic documents reviewed by the test administrator.'}
        approved=self.client.post(identity_path+'/identity-reviews',headers=self.headers,json=review)
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertFalse(approved.json()['duplicate'])
        self.assertTrue(self.client.post(identity_path+'/identity-reviews',headers=self.headers,json=review).json()['duplicate'])
        current=self.client.get(identity_path+'/identity-state',headers=self.headers).json()
        self.assertTrue(current['link_current']); self.assertFalse(current['ownership_verified'])
        qualification=self.client.get(identity_path+'/qualification-state',headers=self.headers)
        self.assertEqual(qualification.status_code,200,qualification.text)
        self.assertEqual(qualification.json()['assessment']['classification'],'duplicate')
        assessment_request={'id':'74000000-0000-4000-8000-000000000001','expected_sequence':qualification.json()['sequence'],
            'evidence_hash':qualification.json()['evidence_hash']}
        recorded=self.client.post(identity_path+'/assessments',headers=self.headers,json=assessment_request)
        self.assertEqual(recorded.status_code,200,recorded.text)
        self.assertFalse(recorded.json()['duplicate'])
        self.assertTrue(self.client.post(identity_path+'/assessments',headers=self.headers,json=assessment_request).json()['duplicate'])
        self.assertTrue(self.client.get(identity_path+'/qualification-state',headers=self.headers).json()['assessment_current'])

        revoked=self.client.post(identity_path+'/identity-reviews',headers=self.headers,json={
            'id':'72000000-0000-4000-8000-000000000002','expected_sequence':current['sequence'],
            'preparation_hash':current['preparation_hash'],'action':'revoke','review_note':'Synthetic correction removes the reviewed association.'})
        self.assertEqual(revoked.status_code,200,revoked.text)
        self.assertFalse(self.client.get(identity_path+'/identity-state',headers=self.headers).json()['link_current'])
        changed_assessment=self.client.get(identity_path+'/qualification-state',headers=self.headers).json()
        self.assertFalse(changed_assessment['assessment_current'])
        self.assertEqual(changed_assessment['latest_assessment']['classification'],'duplicate')
        self.assertEqual(changed_assessment['assessment']['classification'],'incomplete')
        self.assertFalse(changed_assessment['assessment']['outreach_authorized'])
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake_assessment'"),'1')

        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake_identity'"),'2')
        self.assertEqual(self.sql('SELECT count(DISTINCT lead_id) FROM seller_intakes'),'2')

        self.assertEqual(self.client.get(f'{self.base}/intakes/{intake}/candidates',
            headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)

        self.assertEqual(self.facebook_delivery(('1','2')).status_code,200)
        self.assertEqual(self.facebook_worker().json(),{'status':'idle'})
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake'"),'2')
        self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE status='pending'"),'1') # Legacy sentinel only.

    def test_qualified_facebook_intake_handoff_calculates_canonical_property_and_goes_stale(self):
        self.configure_facebook()
        self.provider_metadata={'campaign_id':'300','adset_id':'400','ad_id':'500','is_organic':False,'platform':'fb'}
        answers=dict(property_address='1 Fixture St',city='Dallas',state='TX',authority='yes',
            condition='repairs',timeline='soon',motivation='move',asking_price='150000',phone='2145550101')
        self.provider_fields=[{'name':key,'values':[value]} for key,value in answers.items()]
        self.assertEqual(self.facebook_delivery().status_code,200)
        self.assertEqual(self.facebook_worker().status_code,200)
        intake=self.sql('SELECT id FROM seller_intakes')
        source_lead=self.sql('SELECT lead_id FROM seller_intakes')
        identity_path=f'{self.base}/intakes/{intake}'
        attribution=self.client.get(identity_path+'/attribution',headers=self.headers)
        self.assertEqual(attribution.status_code,200,attribution.text)
        self.assertEqual(attribution.json()['attribution']['campaign_id'],'300')
        self.assertEqual(attribution.json()['attribution']['status'],'available')
        self.assertIsNone(attribution.json()['attribution']['spend_cents'])
        self.assertEqual(self.client.get(identity_path+'/attribution',headers={'Authorization':'Bearer synthetic-other-session'}).status_code,404)
        source_path=f'{self.base}/leads/{LEAD}/source-touches'
        before_sources=self.client.get(source_path,headers=self.headers)
        self.assertEqual(before_sources.status_code,200,before_sources.text); self.assertEqual(before_sources.json()['items'],[])
        identity=self.client.get(identity_path+f'/identity-state?target={LEAD}',headers=self.headers).json()
        decision={'id':'75000000-0000-4000-8000-000000000001','expected_sequence':0,
            'preparation_hash':identity['preparation_hash'],'action':'link_property','target_lead_id':LEAD,'target_hash':identity['target_hash'],
            'property_basis':'parcel_document','property_evidence_ref':'synthetic-parcel-review-42','review_note':'Synthetic canonical property evidence reviewed for handoff.'}
        self.assertEqual(self.client.post(identity_path+'/identity-reviews',headers=self.headers,json=decision).status_code,200)
        property_sources=self.client.get(source_path,headers=self.headers)
        self.assertEqual(property_sources.status_code,200,property_sources.text)
        touch=property_sources.json()['items'][0]
        self.assertEqual(touch['source_id'],intake); self.assertEqual(touch['original_lead_id'],source_lead)
        self.assertEqual(touch['identity_review_id'],decision['id']); self.assertEqual(touch['association'],'reviewed_property')
        self.assertFalse(property_sources.json()['totals_available']); self.assertIsNone(touch['current_campaign_id'])
        self.assertEqual(self.client.get(source_path,headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)
        qualified=self.client.get(identity_path+'/qualification-state',headers=self.headers).json()
        self.assertEqual(qualified['assessment']['classification'],'qualified')
        body={'id':ANALYSIS,'evidence_hash':qualified['evidence_hash'],'inputs':inputs()}
        path=identity_path+'/underwriting/scenarios'
        response=self.client.post(path,headers=self.headers,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['analysis']['lead_id'],LEAD)
        self.assertNotEqual(response.json()['analysis']['lead_id'],source_lead)
        self.assertEqual(response.json()['analysis']['acquisition_status'],'calculated')
        self.assertTrue(response.json()['intake_context']['qualification_current'])
        self.assertFalse(response.json()['binding_offer'])
        provenance_path=f'{self.base}/underwriting/scenarios/{ANALYSIS}/intake-context'
        provenance=self.client.get(provenance_path,headers=self.headers)
        self.assertEqual(provenance.status_code,200,provenance.text)
        self.assertEqual(provenance.json()['evidence_hash'],body['evidence_hash'])
        self.assertTrue(provenance.json()['qualification_current'])
        self.assertEqual(self.client.get(provenance_path,headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments'),'1')
        self.assertEqual(self.proposal().status_code,200)
        self.assertEqual(self.client.post(path,headers=self.headers,json=body).status_code,200)
        revoked={ 'id':'75000000-0000-4000-8000-000000000002','expected_sequence':1,'preparation_hash':identity['preparation_hash'],
            'action':'revoke','review_note':'Synthetic correction revokes this canonical property association.'}
        self.assertEqual(self.client.post(identity_path+'/identity-reviews',headers=self.headers,json=revoked).status_code,200)
        self.assertEqual(self.client.get(source_path,headers=self.headers).json()['items'],[])
        replay=self.client.post(path,headers=self.headers,json=body)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertFalse(replay.json()['intake_context']['qualification_current'])
        historical=self.client.get(provenance_path,headers=self.headers)
        self.assertEqual(historical.status_code,200,historical.text)
        self.assertFalse(historical.json()['qualification_current'])
        self.assertEqual(historical.json()['evidence_hash'],body['evidence_hash'])
        offer=self.client.get(f'{self.base}/offers/{OFFER}/state',headers=self.headers).json()
        self.assertIn('INTAKE_QUALIFICATION_CHANGED',offer['amount_review_blockers'])
        self.assertNotIn('amount_approved',offer['available_review_actions'])
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'1')
        self.assertEqual(self.sql(f"SELECT (property_id IS NULL)::text FROM workspace_leads WHERE lead_id='{source_lead}'"),'true')

    def test_campaign_link_http_review_revoke_and_no_provider_action(self):
        self.configure_facebook(); self.provider_metadata={'campaign_id':'300'}
        self.assertEqual(self.facebook_delivery().status_code,200)
        self.assertEqual(self.facebook_worker().status_code,200)
        intake=self.sql('SELECT id FROM seller_intakes')
        campaign='cf000000-0000-4000-8000-000000000001'
        created=self.client.post(self.base+'/campaigns',headers=self.headers,json={'id':campaign,'name':'Reviewed campaign','channel':'facebook','budget_cents':50000,'currency':'USD'})
        self.assertEqual(created.status_code,200,created.text)
        path=self.base+'/intakes/'+intake
        state=self.client.get(path+'/campaign-link-state',headers=self.headers)
        self.assertEqual(state.status_code,200,state.text)
        self.assertEqual(state.json()['page_id'],'100')
        body={'id':'cf000000-0000-4000-8000-000000000002','expected_sequence':0,'preparation_hash':state.json()['preparation_hash'],
              'action':'link','campaign_id':campaign,'ad_account_id':'999','evidence_ref':'Synthetic ownership document','review_note':'Reviewed Page, ad account and campaign ownership.'}
        self.lose_facebook_reply='review_acquisition_campaign_link'
        self.assertEqual(self.client.post(path+'/campaign-link-reviews',headers=self.headers,json=body).status_code,503)
        replay=self.client.post(path+'/campaign-link-reviews',headers=self.headers,json=body)
        self.assertEqual(replay.status_code,200,replay.text); self.assertTrue(replay.json()['duplicate'])
        linked=self.client.get(path+'/campaign-link-state',headers=self.headers).json()
        self.assertTrue(linked['link_current']); self.assertFalse(linked['execution_authorized'])
        self.assertEqual(linked['internal_campaign_id'],campaign)
        self.assertEqual(self.client.get(path+'/campaign-link-state',headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)
        lead=self.sql('SELECT lead_id FROM seller_intakes')
        sources=self.client.get(self.base+'/leads/'+lead+'/sources',headers=self.headers)
        self.assertEqual(sources.status_code,200,sources.text); self.assertEqual(sources.json()['items'][0]['external_campaign_id'],'300')
        self.assertIsNone(sources.json()['items'][0]['utm_data'])
        capture={'id':'cd000000-0000-4000-8000-000000000001','link_review_id':body['id']}
        self.lose_facebook_reply='capture_acquisition_source_campaign'
        self.assertEqual(self.client.post(path+'/source-campaign-reviews',headers=self.headers,json=capture).status_code,503)
        captured=self.client.post(path+'/source-campaign-reviews',headers=self.headers,json=capture)
        self.assertEqual(captured.status_code,200,captured.text); self.assertTrue(captured.json()['duplicate'])
        current=self.client.get(path+'/source-campaign-reviews',headers=self.headers)
        self.assertEqual(current.status_code,200,current.text); self.assertTrue(current.json()['items'][0]['attribution_current']); self.assertEqual(current.json()['current_capture']['id'],capture['id'])
        revoke={**body,'id':'cf000000-0000-4000-8000-000000000003','expected_sequence':1,'action':'revoke','campaign_id':None,'ad_account_id':None}
        self.assertEqual(self.client.post(path+'/campaign-link-reviews',headers=self.headers,json=revoke).status_code,200)
        self.assertFalse(self.client.get(path+'/campaign-link-state',headers=self.headers).json()['link_current'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_campaign_links'),'2')
        historical=self.client.get(path+'/source-campaign-reviews',headers=self.headers)
        self.assertEqual(historical.status_code,200,historical.text); self.assertFalse(historical.json()['items'][0]['attribution_current']); self.assertIsNone(historical.json()['current_capture'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_source_campaign_reviews'),'1')
        self.assertEqual(self.client.get(self.base+'/leads/'+lead+'/sources',headers={'Authorization':'Bearer synthetic-other-session'}).json()['items'],[])
        history=self.client.get(path+'/campaign-link-reviews?limit=1',headers=self.headers)
        self.assertEqual(history.status_code,200,history.text); self.assertEqual(history.json()[0]['action'],'revoke')
        older=self.client.get(path+'/campaign-link-reviews?limit=1&before=2',headers=self.headers)
        self.assertEqual(older.status_code,200,older.text); self.assertEqual(older.json()[0]['action'],'link')
        self.assertEqual(self.client.get(path+'/campaign-link-reviews',headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)
        self.assertEqual(self.sql('SELECT count(*) FROM leads WHERE ad_campaign_id IS NOT NULL'),'0')
        self.assertEqual(sum(path.startswith('/v26.0/') for path,token in self.requests),1)

    def test_reviewed_cost_coverage_http_preserves_gaps_and_revoked_attribution(self):
        intake,review=self.cost_fixture()
        path=f'{self.base}/campaigns/{self.link_campaign}/cost-coverage?start_date=2026-10-24&end_date=2026-10-24'
        empty=self.client.get(path,headers=self.headers); self.assertEqual(empty.status_code,200,empty.text)
        self.assertEqual(empty.json()['status'],'unavailable')
        self.cost_record(review)
        response=self.client.get(path,headers=self.headers); self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['total_cost_minor'],'12550')
        self.assertTrue(response.json()['days'][0]['attribution_current'])
        gap=self.client.get(path.replace('end_date=2026-10-24','end_date=2026-10-25'),headers=self.headers)
        self.assertIsNone(gap.json()['total_cost_minor']); self.assertIn('COST_MISSING',gap.json()['reason_codes'])
        self.assertEqual(self.client.get(path,headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)
        self.campaign_link_review(intake,self.campaign_link_state(intake),p_id='cf000000-0000-4000-8000-000000000002',p_action='revoke',p_campaign=None,p_ad_account=None)
        stale=self.client.get(path,headers=self.headers).json()
        self.assertEqual(stale['status'],'requires_review'); self.assertIsNone(stale['total_cost_minor'])
        self.assertFalse(stale['days'][0]['attribution_current']); self.assertIsNone(stale['cost_per_lead_minor'])
        self.assertFalse(any('graph.facebook' in route for route,_ in self.requests))

    def test_campaign_draft_http_is_idempotent_scoped_and_non_executing(self):
        path=self.base+'/campaigns'
        body={'id':'91000000-0000-4000-8000-000000000001','name':'Synthetic draft','channel':'facebook','budget_cents':50000,'currency':'USD'}
        first=self.client.post(path,headers=self.headers,json=body)
        self.assertEqual(first.status_code,200,first.text)
        self.assertFalse(first.json()['execution_authorized'])
        self.assertTrue(self.client.post(path,headers=self.headers,json=body).json()['duplicate'])
        listed=self.client.get(path,headers=self.headers)
        self.assertEqual(listed.status_code,200,listed.text)
        self.assertEqual(listed.json()['items'][0]['id'],body['id'])
        self.assertEqual(listed.json()['items'][0]['status'],'draft')
        self.assertEqual(self.client.get(path,headers={'Authorization':'Bearer synthetic-other-session'}).json()['items'],[])
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_campaign'"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_inbox_processing'),'0')

    def test_facebook_ad_identity_conflict_holds_without_intake(self):
        self.configure_facebook()
        self.provider_metadata={'ad_id':'501'}
        self.assertEqual(self.facebook_delivery(metadata={'ad_id':'500'}).status_code,200)
        response=self.facebook_worker()
        self.assertEqual(response.json(),{'status':'review','reason_code':'IDENTITY_CONFLICT'})
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'0')
        self.assertEqual(self.sql("SELECT state||':'||reason_code FROM private.acquisition_inbox_processing"),'review:IDENTITY_CONFLICT')

    def test_facebook_unknown_receipt_and_completion_replies_reconcile(self):
        self.configure_facebook()
        self.lose_facebook_reply='accept_facebook_acquisition_batch'
        self.assertEqual(self.facebook_delivery().status_code,503)
        self.assertEqual(self.facebook_delivery().status_code,200)
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_inbox_processing'),'1')
        self.lose_facebook_reply='complete_facebook_acquisition_intake'
        response=self.facebook_worker()
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['duplicate'])
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake'"),'1')
        self.assertEqual(sum(path.startswith('/v26.0/') for path,token in self.requests),1)

    def test_facebook_expired_credentials_hold_real_job_without_crm_write(self):
        self.configure_facebook();self.provider_error=190
        self.assertEqual(self.facebook_delivery().status_code,200)
        response=self.facebook_worker()
        self.assertEqual(response.json(),{'status':'review','reason_code':'CREDENTIALS_INVALID'})
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'0')
        self.assertEqual(self.sql("SELECT state||':'||reason_code FROM private.acquisition_inbox_processing"),'review:CREDENTIALS_INVALID')
        self.assertEqual(self.facebook_worker().json(),{'status':'idle'})
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='processing_deferred'"),'1')
        health=self.client.get(self.base+'/inquiries/health',headers=self.headers)
        self.assertEqual(health.status_code,200,health.text)
        self.assertEqual(health.json()['summary']['requires_review'],1)
        self.assertEqual(health.json()['items'][0]['reason_code'],'CREDENTIALS_INVALID')
        self.assertIn('credential',health.json()['items'][0]['guidance'])
        self.assertEqual(self.client.get(self.base+'/inquiries/health',headers={'Authorization':'Bearer synthetic-other-session'}).status_code,403)
        item=health.json()['items'][0]
        recovery_path=self.base+'/inquiries/'+item['receipt_id']+'/recoveries'
        review={'id':'e0000000-0000-4000-8000-000000000001','expected_updated_at':item['updated_at'],
                'expected_reason':item['reason_code'],'review_note':'Synthetic credential repaired and Page access verified',
                'evidence_ref':'isolated-fixture/credential-review'}
        self.assertEqual(self.client.post(recovery_path,headers={'Authorization':'Bearer synthetic-other-session'},json=review).status_code,403)
        approved=self.client.post(recovery_path,headers=self.headers,json=review)
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertFalse(approved.json()['outreach_authorized'])
        self.assertTrue(self.client.post(recovery_path,headers=self.headers,json=review).json()['duplicate'])
        self.provider_error=None
        self.assertEqual(self.facebook_worker().json()['status'],'completed')
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_inquiry_recoveries'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='recovery_approved'"),'1')

    def test_facebook_signature_and_form_mismatch_do_not_create_leads(self):
        self.configure_facebook()
        self.assertEqual(self.facebook_delivery(tamper=True).status_code,403)
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_inbox_processing'),'0')
        self.assertEqual(self.facebook_delivery().status_code,200)
        self.provider_form='999'
        self.assertEqual(self.facebook_worker().json(),{'status':'review','reason_code':'IDENTITY_CONFLICT'})
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='facebook_acquisition'"),'0')

    def test_facebook_disable_during_retrieval_blocks_completion(self):
        self.configure_facebook()
        self.assertEqual(self.facebook_delivery().status_code,200)
        self.disable_during_retrieval=True
        response=self.facebook_worker()
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='facebook_acquisition'"),'0')
        self.assertEqual(self.sql("SELECT state FROM private.acquisition_inbox_processing"),'leased')
        self.assertEqual(sum(path.startswith('/v26.0/') for path,token in self.requests),1)
        self.assertEqual(self.facebook_worker().status_code,503) # No claim after disable.
        self.assertEqual(sum(path.startswith('/v26.0/') for path,token in self.requests),1)

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
