"""Real PostgreSQL acceptance in a disposable Unix-socket-only cluster.

Uses only stdlib + local PostgreSQL binaries, no inherited credentials, dotenv,
TCP listener, provider SDK, cron, pg_net, or production database connection.
This verifies the migration's touched dependencies; full upgrade QA is separate.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'frontend/supabase/migrations/20261026024157_acquisition_workspace_foundation.sql'
BOUNDARY_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026025259_acquisition_legacy_access_boundary.sql'
RELATED_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026030633_acquisition_related_record_isolation.sql'
ACTIVATION_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026031751_acquisition_activation_gate.sql'
CONTACT_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026032050_acquisition_contact_crosswalk.sql'
ELIGIBILITY_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026032519_acquisition_eligibility_ledger.sql'
OWNER_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026033010_acquisition_owner_relationships.sql'
PERMISSION_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026033554_acquisition_permission_evidence.sql'
ANALYSIS_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026040321_acquisition_analysis_versions.sql'
OFFER_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026041236_acquisition_offer_review.sql'
OFFER_STATE_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026041845_acquisition_offer_review_state.sql'
INBOX_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026153314_acquisition_provider_inbox.sql'
LEASE_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026153939_acquisition_inbox_leases.sql'
CATALOG = ROOT / 'docs/acquisition-automation/evidence/2026-10-25-catalog.json'
PG = Path(os.environ.get('PG_BIN', '/opt/homebrew/opt/postgresql@17/bin'))
ADMIN = '00000000-0000-4000-8000-000000000001'
OTHER = '00000000-0000-4000-8000-000000000002'
CALLER = '00000000-0000-4000-8000-000000000003'
OPERATOR = '00000000-0000-4000-8000-000000000004'
WORKSPACE = '10000000-0000-4000-8000-000000000001'
WORKSPACE_B = '10000000-0000-4000-8000-000000000002'
LEAD = '20000000-0000-4000-8000-000000000001'
LEAD_B = '20000000-0000-4000-8000-000000000002'
PROPERTY = '30000000-0000-4000-8000-000000000001'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


class WorkspaceTests(unittest.TestCase):
    env = None
    socket = None

    def sql(self, query, *, user=None, role='authenticated', aal='aal2', session=True, fail=False):
        if user:
            claims = {'sub': user, 'aal': aal}
            if session:
                claims['session_id'] = user  # Synthetic session IDs only.
            query = (f'SET ROLE {identifier(role)}; SET request.jwt.claims={literal(json.dumps(claims))}; ' + query)
        result = subprocess.run([str(PG/'psql'), '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
                                 '-h', self.socket, '-U', 'test_admin', '-d', 'acquisition_test'],
                                input=query, text=True, capture_output=True, env=self.env)
        if fail:
            self.assertNotEqual(result.returncode, 0, 'Expected database rejection')
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def setUp(self):
        self.sql('DROP SCHEMA IF EXISTS wholesale_ingest CASCADE; DROP SCHEMA IF EXISTS public CASCADE; DROP SCHEMA IF EXISTS private CASCADE; '
                 'DROP SCHEMA IF EXISTS auth CASCADE; CREATE SCHEMA public; CREATE SCHEMA private; '
                 'CREATE SCHEMA auth; CREATE SCHEMA wholesale_ingest; CREATE EXTENSION "uuid-ossp"; '
                 'GRANT USAGE ON SCHEMA public,private,auth,wholesale_ingest TO authenticated,service_role; '
                 'CREATE TABLE auth.users(id uuid PRIMARY KEY); '
                 'CREATE TABLE auth.sessions(id uuid PRIMARY KEY,user_id uuid NOT NULL REFERENCES auth.users(id),not_after timestamptz); '
                 "CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$; "
                 "CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT (auth.jwt()->>'sub')::uuid $$;")
        catalog = json.loads(CATALOG.read_text())
        # Recreate exact inspected column types/defaults for touched legacy tables.
        for schema, table in (('public','profiles'), ('public','audit_logs'), ('public','leads'), ('public','webhook_jobs'),
                              ('wholesale_ingest','properties'), ('public','campaigns'),
                              ('public','buyer_import_log'), ('public','buyers'), ('public','deals'), ('public','deal_matches'),
                              ('wholesale_ingest','property_aliases'), ('wholesale_ingest','contacts'), ('public','dnc_registry'), ('public','email_suppressions'), ('public','lead_form_submissions'), ('public','facebook_lead_submissions'), ('public','deal_analyses'), ('public','offer_recommendations')):
            columns = []
            for c in catalog['columns']:
                if c['table_schema'] == schema and c['table_name'] == table:
                    dtype = c['udt_name'][1:]+'[]' if c['udt_name'].startswith('_') else c['udt_name']
                    columns.append(identifier(c['column_name'])+' '+dtype+
                                   (' DEFAULT '+c['column_default'] if c['column_default'] else '')+
                                   (' NOT NULL' if c['is_nullable']=='NO' else ''))
            self.sql(f'CREATE TABLE {schema}.{table}('+','.join(columns)+');')
            for c in catalog['constraints']:
                if c['schema']==schema and c['table_name']==table:
                    # Leads' unrelated campaign/form/list FK targets are outside
                    # this focused fixture. Full production upgrade remains separate.
                    if table=='lead_form_submissions' and 'lead_form_configs' in c['definition']:
                        continue  # Source form configuration is outside this focused fixture.
                    if table=='contacts' and 'skip_trace_requests' in c['definition']:
                        continue  # Provider job storage is outside this focused fixture.
                    if table=='offer_recommendations' and 'qualification_results' in c['definition']:
                        continue  # Existing qualification/transcript chain is outside this focused fixture.
                    if table=='leads' and c['contype']=='f':
                        continue
                    self.sql(f'ALTER TABLE {schema}.{table} ADD CONSTRAINT '+identifier(c['conname'])+' '+c['definition'])
            if table not in ('profiles','audit_logs'):
                self.sql(f'ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY; '
                         f'GRANT SELECT,INSERT,UPDATE,DELETE ON {schema}.{table} TO authenticated; '
                         f'CREATE POLICY legacy_approved ON {schema}.{table} TO authenticated USING (true) WITH CHECK (true);')
        self.sql("ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY; "
                 "GRANT SELECT ON public.audit_logs TO authenticated; GRANT ALL ON public.audit_logs TO service_role; "
                 "CREATE POLICY approved_read_audit_logs ON public.audit_logs FOR SELECT TO authenticated USING (true); "
                 "INSERT INTO public.audit_logs(entity_type,entity_id,action,actor) VALUES('legacy','sentinel','historical','system');")
        for user, role in ((ADMIN,'admin'),(OTHER,'admin'),(CALLER,'user'),(OPERATOR,'user')):
            self.sql(f"INSERT INTO auth.users VALUES('{user}'); INSERT INTO auth.sessions VALUES('{user}','{user}',NULL); "
                     f"INSERT INTO profiles(id,email,role,status) VALUES('{user}','{user}@example.test','{role}','approved');")
        self.sql((ROOT/'frontend/supabase/migrations/20261008223315_repair_analysis_lead_sync.sql').read_text())
        self.sql('CREATE TRIGGER deal_analysis_sync AFTER INSERT OR UPDATE ON deal_analyses FOR EACH ROW EXECUTE FUNCTION sync_deal_to_lead(); '
                 'GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE ON deal_analyses TO service_role;')
        self.sql(MIGRATION.read_text())
        if self._testMethodName == 'test_migration_scopes_preexisting_memberships':
            self.create(ADMIN, WORKSPACE)
            self.member()
        self.sql(BOUNDARY_MIGRATION.read_text())
        self.sql(RELATED_MIGRATION.read_text())
        self.sql(ACTIVATION_MIGRATION.read_text())
        self.sql(CONTACT_MIGRATION.read_text())
        self.sql(ELIGIBILITY_MIGRATION.read_text())
        self.sql(OWNER_MIGRATION.read_text())
        self.sql(PERMISSION_MIGRATION.read_text())
        self.sql(ANALYSIS_MIGRATION.read_text())
        self.sql('GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE ON offer_recommendations TO service_role;')
        self.sql(OFFER_MIGRATION.read_text())
        self.sql(OFFER_STATE_MIGRATION.read_text())
        self.sql("GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE ON webhook_jobs TO service_role; "
                 "INSERT INTO webhook_jobs(source,payload) VALUES('legacy_fixture','{\"sentinel\":true}');")
        self.sql(INBOX_MIGRATION.read_text())
        self.sql(LEASE_MIGRATION.read_text())
        if self._testMethodName != 'test_activation_defaults_closed':
            self.activate()
        if self._testMethodName != 'test_activation_defaults_closed':
            self.create(ADMIN, WORKSPACE)
            self.create(OTHER, WORKSPACE_B)
        self.sql(f"INSERT INTO leads(id,property_address,city,owner_phone_1) VALUES ('{LEAD}','1 Fixture St','Dallas','+12145550101'),('{LEAD_B}','2 Fixture St','Plano','+12145550101'); "
                 f"INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES('{PROPERTY}','TX','Dallas','fixture-parcel','{LEAD}'); "
                 "INSERT INTO campaigns(name) VALUES('legacy-sentinel');")

    def inbox_config(self, account='fixture-page', workspace=WORKSPACE, enabled=True):
        self.sql(f"INSERT INTO private.acquisition_integrations(workspace_id,provider,account_id,enabled,approval_ref) "
                 f"VALUES('{workspace}','facebook',{literal(account)},{str(enabled).lower()},'isolated test only');")

    def inbox_accept(self, payload='{"leadgen_id":"fixture"}', account='fixture-page', role='service_role', fail=False):
        result=self.sql(f"SELECT public.accept_acquisition_event('facebook',{literal(account)},'fixture','leadgen',"
                        f"{literal(payload)}::jsonb,convert_to('synthetic raw envelope','UTF8'));",user=ADMIN,role=role,fail=fail)
        return result if fail else json.loads(result)

    def test_inbox_concurrent_duplicate_and_conflict(self):
        self.inbox_config()
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(lambda _:self.inbox_accept(),range(4)))
        self.assertEqual(len({r['receipt_id'] for r in receipts}),1)
        self.assertEqual(sum(not r['duplicate'] for r in receipts),1)
        self.inbox_accept(payload='{"leadgen_id":"changed"}',fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_inbox' AND action='received';"),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE status='pending';"),'1')
        self.assertEqual(self.sql("SELECT payload->>'sentinel' FROM webhook_jobs WHERE source='legacy_fixture';"),'true')

    def test_inbox_mapping_and_activation_fail_closed(self):
        self.inbox_accept(fail=True)
        self.inbox_config(enabled=False)
        self.inbox_accept(fail=True)
        self.sql("UPDATE private.acquisition_integrations SET enabled=true;")
        self.sql("UPDATE private.acquisition_activation SET enabled=false;")
        self.inbox_accept(fail=True)
        self.activate()
        self.sql(f"UPDATE workspaces SET status='suspended' WHERE id='{WORKSPACE}';")
        self.inbox_accept(fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE workspace_id IS NOT NULL;"),'0')

    def test_inbox_private_immutable_and_workspace_routing(self):
        self.inbox_config()
        receipt=self.inbox_accept()
        self.inbox_config(account='other-page',workspace=WORKSPACE_B)
        other=self.inbox_accept(account='other-page')
        self.assertNotEqual(receipt['receipt_id'],other['receipt_id'])
        self.assertEqual(other['workspace_id'],WORKSPACE_B)
        self.inbox_accept(role='authenticated',fail=True)
        for actor in (ADMIN,OTHER,CALLER):
            self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE workspace_id IS NOT NULL;",user=actor),'0')
        for statement in ("UPDATE webhook_jobs SET status='pending' WHERE workspace_id IS NOT NULL;",
                          "UPDATE webhook_jobs SET workspace_id=NULL WHERE workspace_id IS NOT NULL;",
                          "DELETE FROM webhook_jobs WHERE workspace_id IS NOT NULL;", "TRUNCATE webhook_jobs;",
                          "UPDATE private.acquisition_integrations SET enabled=false;"):
            self.sql(statement,user=ADMIN,role='service_role',fail=True)
        self.sql("UPDATE webhook_jobs SET status='done' WHERE source='legacy_fixture';",user=ADMIN,role='service_role')

    def test_inbox_retention_preserves_identity_and_hash(self):
        self.inbox_config()
        receipt=self.inbox_accept()
        self.assertEqual(self.sql("SELECT public.purge_acquisition_payloads();",user=ADMIN,role='service_role'),'0')
        # Owner-only fixture simulates a receipt whose retention period has elapsed.
        self.sql("INSERT INTO webhook_jobs(source,payload,status,workspace_id,acquisition_integration_id,external_event_id,"
                 "acquisition_event_type,acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,acquisition_expires_at) "
                 "SELECT source,payload,status,workspace_id,acquisition_integration_id,'expired-fixture',acquisition_event_type,"
                 "acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,now()-interval '1 day' FROM webhook_jobs WHERE workspace_id IS NOT NULL;")
        self.assertEqual(self.sql("SELECT public.purge_acquisition_payloads(1);",user=ADMIN,role='service_role'),'1')
        self.assertEqual(self.sql("SELECT public.purge_acquisition_payloads();",user=ADMIN,role='service_role'),'0')
        self.assertEqual(self.sql("SELECT (payload='{}'::jsonb AND acquisition_raw_body IS NULL AND length(acquisition_payload_hash)=64)::text "
                                 "FROM webhook_jobs WHERE external_event_id='expired-fixture';"),'true')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_inbox' AND action='payload_purged';"),'1')
        self.assertTrue(self.inbox_accept()['duplicate'])

    def inbox_claim(self, role='service_role', fail=False):
        integration=self.sql("SELECT id FROM private.acquisition_integrations WHERE account_id='fixture-page';")
        value=self.sql(f"SELECT public.claim_acquisition_events('{integration}',1,120);",user=ADMIN,role=role,fail=fail)
        return value if fail else json.loads(value)

    def inbox_defer(self, claim, outcome='retry', reason='PROVIDER_TIMEOUT', fail=False):
        value=self.sql(f"SELECT public.defer_acquisition_event('{claim['receipt_id']}','{claim['lease_token']}',"
                       f"{literal(outcome)},{literal(reason)});",user=ADMIN,role='service_role',fail=fail)
        return value if fail else json.loads(value)

    def test_inbox_leases_are_exclusive_and_recover_crashed_worker(self):
        self.inbox_config(); self.inbox_accept()
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims=list(pool.map(lambda _:self.inbox_claim(),range(4)))
        claimed=[item for batch in claims for item in batch]
        self.assertEqual(len(claimed),1)
        original=claimed[0]
        self.assertEqual(original['attempt'],1)
        self.assertNotIn('acquisition_raw_body',original)
        self.assertEqual(self.inbox_claim(),[])
        self.sql("UPDATE private.acquisition_inbox_processing SET lease_expires_at=now()-interval '1 second';")
        self.inbox_defer(original,fail=True)
        replacement=self.inbox_claim()[0]
        self.assertEqual(replacement['attempt'],2)
        self.assertNotEqual(original['lease_token'],replacement['lease_token'])
        self.inbox_defer(original,fail=True)
        result=self.inbox_defer(replacement)
        self.assertEqual(result['state'],'retry')
        self.assertTrue(self.inbox_defer(replacement)['duplicate'])
        self.inbox_defer(replacement,reason='PROVIDER_RATE_LIMIT',fail=True)
        self.assertEqual(self.inbox_claim(),[]) # Backoff is server enforced.
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='processing_deferred';"),'1')

    def test_inbox_retry_budget_and_credential_hold(self):
        self.inbox_config(); self.inbox_accept()
        for attempt in range(1,6):
            claim=self.inbox_claim()[0]
            self.assertEqual(claim['attempt'],attempt)
            result=self.inbox_defer(claim)
            self.assertEqual(result['state'],'review' if attempt==5 else 'retry')
            self.sql("UPDATE private.acquisition_inbox_processing SET next_attempt_at=now()-interval '1 second';")
        self.assertEqual(result['reason_code'],'RETRY_EXHAUSTED')
        self.assertEqual(self.inbox_claim(),[])
        self.assertTrue(self.inbox_defer(claim)['duplicate'])
        self.sql("UPDATE private.acquisition_inbox_processing SET state='ready',attempts=0;") # New case fixture only.
        claim=self.inbox_claim()[0]
        held=self.inbox_defer(claim,'review','CREDENTIALS_INVALID')
        self.assertEqual(held['reason_code'],'CREDENTIALS_INVALID')
        self.assertEqual(self.inbox_claim(),[])
        self.inbox_defer(claim,'review','secret or arbitrary exception text',fail=True)

    def test_inbox_lease_exhaustion_and_expiry_never_reprocess(self):
        self.inbox_config(); self.inbox_accept()
        claim=self.inbox_claim()[0]
        self.sql("UPDATE private.acquisition_inbox_processing SET attempts=5,lease_expires_at=now()-interval '1 second';")
        self.assertEqual(self.inbox_claim(),[])
        self.assertEqual(self.sql("SELECT reason_code FROM private.acquisition_inbox_processing;"),'RETRY_EXHAUSTED')
        self.inbox_defer(claim,fail=True)
        self.sql("INSERT INTO webhook_jobs(source,payload,status,workspace_id,acquisition_integration_id,external_event_id,"
                 "acquisition_event_type,acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,acquisition_expires_at) "
                 "SELECT source,payload,status,workspace_id,acquisition_integration_id,'expired-job',acquisition_event_type,"
                 "acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,now()-interval '1 day' FROM webhook_jobs WHERE workspace_id IS NOT NULL;")
        self.assertEqual(self.inbox_claim(),[])
        self.assertEqual(self.sql("SELECT count(*) FROM private.acquisition_inbox_processing WHERE reason_code='PAYLOAD_EXPIRED';"),'1')

    def test_inbox_worker_authority_and_kill_switch(self):
        self.inbox_config(); self.inbox_accept()
        self.inbox_claim(role='authenticated',fail=True)
        self.sql("SELECT * FROM private.acquisition_inbox_processing;",user=ADMIN,role='service_role',fail=True)
        self.sql("UPDATE private.acquisition_inbox_processing SET state='ready';",user=ADMIN,role='service_role',fail=True)
        claim=self.inbox_claim()[0]
        self.sql("UPDATE private.acquisition_activation SET enabled=false;")
        self.inbox_claim(fail=True)
        self.assertEqual(self.inbox_defer(claim,'review','UNSUPPORTED_EVENT')['state'],'review')
        self.activate()
        self.sql("UPDATE private.acquisition_integrations SET enabled=false;")
        self.inbox_claim(fail=True)
        self.sql("UPDATE private.acquisition_integrations SET enabled=true;")
        self.sql(f"UPDATE workspaces SET status='suspended' WHERE id='{WORKSPACE}';")
        self.inbox_claim(fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE status='pending';"),'1')

    def reserve_analysis(self, identity='b0000000-0000-4000-8000-000000000001', actor=ADMIN, workspace=WORKSPACE, lead=LEAD, inputs=None, fail=False):
        if inputs is None: inputs={'cases':{name:{'strategy':'fix_and_flip'} for name in ('base','downside','upside')}}
        result=self.sql(f"SELECT public.reserve_acquisition_analysis('{identity}','{workspace}','{lead}',{literal(json.dumps(inputs))}::jsonb);",user=actor,fail=fail)
        return result if fail else json.loads(result)

    def calculation_snapshot(self, identity='b0000000-0000-4000-8000-000000000001', workspace=WORKSPACE, role='service_role', fail=False):
        result=self.sql(f"SELECT public.read_acquisition_calculation('{identity}','{workspace}');",user=ADMIN,role=role,fail=fail)
        return result if fail else json.loads(result)

    def complete_analysis(self, snapshot, role='service_role', fail=False, output=None):
        if output is None:
            output={'status':'incomplete','calculation_version':'acquisition-underwriting-v1','strategy':'fix_and_flip',
                    'cases':{name:{'mao':None} for name in ('base','downside','upside')},'binding_offer':False,'human_approval_required':True,'persisted':False}
        return self.sql(f"SELECT public.complete_acquisition_calculation('{snapshot['id']}','{snapshot['workspace_id']}',"
                        f"{literal(snapshot['input_hash'])},{literal(json.dumps(output))}::jsonb);",user=ADMIN,role=role,fail=fail)

    def test_analysis_versions_are_immutable_and_do_not_sync_lead_mao(self):
        self.sql(f"UPDATE leads SET mao=12345,estimated_arv=200000,estimated_repairs=10000 WHERE id='{LEAD}';")
        self.bind()
        first=self.reserve_analysis()
        self.assertEqual(first,self.reserve_analysis())
        second=self.reserve_analysis(identity='b0000000-0000-4000-8000-000000000002')
        self.assertEqual([first['revision'],second['revision']],[1,2])
        snapshot=self.calculation_snapshot()
        finished=self.complete_analysis(snapshot)
        self.assertEqual(finished,self.complete_analysis(snapshot))
        self.assertEqual(self.sql(f"SELECT mao||':'||estimated_arv||':'||estimated_repairs FROM leads WHERE id='{LEAD}';"),'12345:200000:10000')
        self.assertEqual(self.sql("SELECT acquisition_outputs->>'persisted' FROM deal_analyses WHERE acquisition_revision=1"),'true')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_analysis' AND action='calculated'"),'1')
        self.sql("UPDATE deal_analyses SET acquisition_inputs='{}' WHERE workspace_id IS NOT NULL;",fail=True)
        self.sql('DELETE FROM deal_analyses WHERE workspace_id IS NOT NULL;',fail=True)
        changed={'cases':{name:{'strategy':'rental'} for name in ('base','downside','upside')}}
        self.reserve_analysis(inputs=changed,fail=True)

    def test_analysis_output_requires_worker_rpc_not_user_or_raw_service_write(self):
        self.bind(); self.reserve_analysis()
        snapshot=self.calculation_snapshot()
        self.calculation_snapshot(role='authenticated',fail=True)
        self.complete_analysis(snapshot,role='authenticated',fail=True)
        self.sql("UPDATE deal_analyses SET acquisition_status='invalid',acquisition_outputs='{}' WHERE workspace_id IS NOT NULL;",user=ADMIN,role='service_role',fail=True)
        self.sql('TRUNCATE deal_analyses;',user=ADMIN,role='service_role',fail=True)
        self.complete_analysis({**snapshot,'input_hash':'wrong'},fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_analysis_jobs'),'1')

    def test_analysis_scope_revocation_and_worker_session_recheck(self):
        self.bind();self.reserve_analysis()
        self.reserve_analysis(actor=OTHER,fail=True)
        self.calculation_snapshot(workspace=WORKSPACE_B,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses',user=OTHER),'0')
        self.member(target=CALLER,role='acquisition_caller')
        self.reserve_analysis(actor=CALLER,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses',user=CALLER),'0')
        self.sql(f"DELETE FROM auth.sessions WHERE user_id='{ADMIN}';")
        self.calculation_snapshot(fail=True)

    def test_unbound_legacy_sync_preserved_but_bound_legacy_writes_held(self):
        self.sql(f"INSERT INTO deal_analyses(lead_id,arv_low,mao,repair_cost_mid) VALUES('{LEAD_B}',250000,120000,20000);")
        self.assertEqual(self.sql(f"SELECT mao FROM leads WHERE id='{LEAD_B}'"),'120000')
        self.bind()
        self.sql(f"INSERT INTO deal_analyses(lead_id,arv_low,mao) VALUES('{LEAD}',999999,999999);",user=ADMIN,role='service_role',fail=True)
        self.sql(f"INSERT INTO deal_analyses(lead_id,arv_low,mao) VALUES('{LEAD}',999999,999999);")
        self.sql(f"UPDATE deal_analyses SET lead_id='{LEAD_B}' WHERE lead_id='{LEAD}';",user=ADMIN,role='service_role',fail=True)
        self.assertEqual(self.sql(f"SELECT coalesce(mao,-1) FROM leads WHERE id='{LEAD}'"),'-1')

    def test_parallel_analysis_requests_get_distinct_ordered_revisions(self):
        self.bind()
        ids=['b0000000-0000-4000-8000-000000000001','b0000000-0000-4000-8000-000000000002']
        with ThreadPoolExecutor(max_workers=2) as pool:
            values=list(pool.map(lambda identity:self.reserve_analysis(identity=identity),ids))
        self.assertEqual(sorted(value['revision'] for value in values),[1,2])

    def ready_offer(self):
        self.bind(); self.reserve_analysis()
        output={'status':'calculated','calculation_version':'acquisition-underwriting-v1','strategy':'fix_and_flip',
                'cases':{name:{'status':'calculated','mao':'150000.00','proposed_offer_range':{'low':'120000.00','high':'150000.00'}} for name in ('base','downside','upside')},
                'binding_offer':False,'human_approval_required':True}
        self.complete_analysis(self.calculation_snapshot(),output=output)

    def propose_offer(self, identity='c0000000-0000-4000-8000-000000000001', actor=ADMIN, amount=140000, fail=False):
        result=self.sql(f"SELECT public.propose_acquisition_offer('{identity}','{WORKSPACE}','b0000000-0000-4000-8000-000000000001','base',{amount},'Fixture proposal');",user=actor,fail=fail)
        return result if fail else json.loads(result)

    def review_offer(self, identity='d0000000-0000-4000-8000-000000000001', actor=ADMIN, status='amount_approved', sequence=1, notes=None, fail=False):
        if notes is None: notes={key:'Fixture review with unresolved conditions; internal amount only' for key in ('title','liens','occupancy','valuation','repairs','financing','downside')}
        result=self.sql(f"SELECT public.review_acquisition_offer('{identity}','{WORKSPACE}','c0000000-0000-4000-8000-000000000001',{sequence},{literal(status)},'Fixture decision',{literal(json.dumps(notes))}::jsonb);",user=actor,fail=fail)
        return result if fail else json.loads(result)

    def test_offer_review_is_exact_immutable_idempotent_and_not_transmission(self):
        self.ready_offer()
        first=self.propose_offer();self.assertEqual(first,self.propose_offer())
        self.propose_offer(amount=140001,fail=True)
        reviewed=self.review_offer();self.assertEqual(reviewed,self.review_offer())
        self.assertFalse(reviewed['transmission_authorized'])
        self.assertFalse(reviewed['binding_offer'])
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_offer_events"),'2')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_offer'"),'2')
        self.sql("UPDATE offer_recommendations SET target_offer=1 WHERE workspace_id IS NOT NULL;",fail=True)
        self.sql("DELETE FROM acquisition_offer_events;",fail=True)
        self.review_offer(identity='d0000000-0000-4000-8000-000000000002',status='rejected',sequence=2,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        revoked=self.review_offer(identity='d0000000-0000-4000-8000-000000000002',status='approval_revoked',sequence=2)
        self.assertEqual(revoked['status'],'approval_revoked')
        self.review_offer(identity='d0000000-0000-4000-8000-000000000003',sequence=3,fail=True)

    def test_offer_amount_scope_and_review_roles_are_enforced(self):
        self.ready_offer()
        self.propose_offer(amount=150000.01,fail=True)
        self.propose_offer(amount="'NaN'::numeric",fail=True)
        self.propose_offer(actor=OTHER,fail=True)
        self.member(target=OPERATOR,role='operator')
        self.propose_offer(actor=OPERATOR)
        self.review_offer(actor=OPERATOR,fail=True)
        self.review_offer(notes={},fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_offer_events',user=OTHER),'0')
        self.member(target=CALLER,role='acquisition_caller')
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations',user=CALLER),'0')
        self.review_offer(actor=CALLER,fail=True)
        self.assertEqual(self.review_offer(actor=OPERATOR,status='withdrawn')['status'],'withdrawn')

    def test_offer_stale_scenario_and_activation_hold_approval_but_allow_withdrawal(self):
        self.ready_offer();self.propose_offer()
        self.reserve_analysis(identity='b0000000-0000-4000-8000-000000000002')
        self.review_offer(fail=True)
        self.propose_offer(identity='c0000000-0000-4000-8000-000000000002',fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.review_offer(fail=True)
        self.assertEqual(self.review_offer(status='withdrawn')['status'],'withdrawn')

    def test_offer_disabled_activation_blocks_fresh_approval_and_preserves_withdrawal(self):
        self.ready_offer();self.propose_offer()
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.review_offer(fail=True)
        self.propose_offer(identity='c0000000-0000-4000-8000-000000000002',fail=True)
        self.assertEqual(self.review_offer(status='withdrawn')['status'],'withdrawn')

    def test_offer_legacy_analysis_parent_is_scoped_and_raw_service_mutation_denied(self):
        self.ready_offer()
        analysis='b0000000-0000-4000-8000-000000000001'
        self.sql(f"INSERT INTO offer_recommendations(lead_id,deal_analysis_id,target_offer) VALUES('{LEAD_B}','{analysis}',1);")
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations',user=OTHER),'0')
        self.sql(f"INSERT INTO offer_recommendations(lead_id,deal_analysis_id,target_offer) VALUES('{LEAD_B}','{analysis}',1);",user=ADMIN,role='service_role',fail=True)
        self.sql("UPDATE offer_recommendations SET deal_analysis_id=NULL;",user=ADMIN,role='service_role',fail=True)
        self.sql('TRUNCATE offer_recommendations;',user=ADMIN,role='service_role',fail=True)
        self.bind(actor=OTHER,workspace=WORKSPACE_B,lead=LEAD_B,property_id=None)
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations',user=ADMIN),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM offer_recommendations',user=OTHER),'0')

    def test_offer_review_concurrency_cannot_approve_and_reject_same_revision(self):
        self.ready_offer();self.propose_offer()
        def run(status):
            identity='d0000000-0000-4000-8000-00000000000'+('1' if status=='amount_approved' else '2')
            try:return self.review_offer(identity=identity,status=status)['status']
            except AssertionError:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,['amount_approved','rejected']))
        self.assertEqual(results.count('conflict'),1)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_offer_events'),'2')

    def offer_state(self, actor=ADMIN, workspace=WORKSPACE, fail=False):
        value=self.sql(f"SELECT public.acquisition_offer_review_state('{workspace}','c0000000-0000-4000-8000-000000000001');",user=actor,fail=fail)
        return value if fail else json.loads(value)

    def test_effective_offer_review_rechecks_latest_scenario_and_never_authorizes_delivery(self):
        self.ready_offer();self.propose_offer()
        pending=self.offer_state()
        self.assertFalse(pending['amount_approval_current'])
        self.assertEqual(set(pending['available_review_actions']),{'withdrawn','rejected','amount_approved'})
        self.review_offer()
        current=self.offer_state()
        self.assertTrue(current['amount_approval_current'])
        self.assertFalse(current['transmission_authorized'])
        self.assertIsNone(current['execution_authorization'])
        self.assertEqual(current['available_review_actions'],['approval_revoked'])
        self.reserve_analysis(identity='b0000000-0000-4000-8000-000000000002')
        changed=self.offer_state()
        self.assertFalse(changed['amount_approval_current'])
        self.assertEqual(changed['historical_status'],'amount_approved')
        self.assertEqual(changed['latest_analysis_revision'],2)
        self.assertIn('UNDERWRITING_CHANGED_OR_UNAVAILABLE',changed['amount_review_blockers'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_offer_events'),'2')

    def test_effective_offer_review_does_not_resurrect_after_membership_reenrollment(self):
        self.ready_offer();self.propose_offer()
        self.member(target=OPERATOR,role='admin')
        self.review_offer(actor=OPERATOR)
        self.assertTrue(self.offer_state()['amount_approval_current'])
        self.member(target=OPERATOR,role='admin',status='revoked')
        self.assertIn('APPROVER_AUTHORITY_CHANGED',self.offer_state()['amount_review_blockers'])
        self.member(target=OPERATOR,role='admin')
        self.assertFalse(self.offer_state()['amount_approval_current'])
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        state=self.offer_state()
        self.assertIn('ACQUISITION_ACTIVATION_DISABLED',state['amount_review_blockers'])
        self.assertEqual(state['available_review_actions'],['approval_revoked'])

    def test_offer_review_queue_bounds_and_scope(self):
        self.ready_offer();self.propose_offer()
        query=f"SELECT public.acquisition_offer_review_queue('{WORKSPACE}',NULL,1);"
        page=json.loads(self.sql(query,user=ADMIN))
        self.assertEqual(len(page['items']),1)
        next_id=page['next_after']
        last=json.loads(self.sql(f"SELECT public.acquisition_offer_review_queue('{WORKSPACE}','{next_id}',1);",user=ADMIN))
        self.assertEqual(last['items'],[])
        self.assertIsNone(last['next_after'])
        self.sql(query,user=OTHER,fail=True)
        self.offer_state(actor=OTHER,fail=True)
        self.offer_state(workspace=WORKSPACE_B,fail=True)
        self.sql(query,user=ADMIN,role='service_role',fail=True)
        self.member(target=CALLER,role='acquisition_caller')
        self.sql(query,user=CALLER,fail=True)
        self.sql(f"SELECT public.acquisition_offer_review_queue('{WORKSPACE}',NULL,51);",user=ADMIN,fail=True)

    def permission_receipt(self, source='website', accepted=True, disclosure='Synthetic SMS checkbox disclosure', when='2020-01-01T12:00:00Z', phone='+12145550101'):
        receipt = '90000000-0000-4000-8000-000000000001'
        form = '90000000-0000-4000-8000-000000000002'
        if source == 'website':
            answers = {'phone':phone, '_sms_consent':{'accepted':accepted,'rendered_disclosure_matches':True,
                'form_id':form,'disclosure':disclosure,'disclosure_sha256':hashlib.sha256(disclosure.encode()).hexdigest()}}
            self.sql(f"INSERT INTO lead_form_submissions(id,lead_id,form_id,created_at,raw_answers) VALUES('{receipt}','{LEAD}','{form}',{literal(when)},{literal(json.dumps(answers))}::jsonb);")
        else:
            key=disclosure.lower().replace(' ','_')
            ai='Synthetic separate AI voice checkbox disclosure'
            ai_key=ai.lower().replace(' ','_')
            consent={'source':'facebook_native_form','recognized_form':True,'form_id':form,'submitted_at':when,'phone':phone,
                     'sms':{'accepted':accepted,'disclosure':disclosure,'checkbox_key':key},
                     'ai_calls':{'accepted':False,'disclosure':ai,'checkbox_key':ai_key},
                     'raw_responses':[{'checkbox_key':key,'is_checked':accepted},{'checkbox_key':ai_key,'is_checked':False}]}
            self.sql(f"INSERT INTO facebook_lead_submissions(id,lead_id,leadgen_id,form_id,submitted_at,phone_number,raw_answers) "
                     f"VALUES('{receipt}','{LEAD}','fixture-meta-lead','{form}',{literal(when)},{literal(phone)},{literal(json.dumps({'_facebook_consent':consent}))}::jsonb);")
        return receipt

    def permission(self, point, source='website', channel='sms', actor=ADMIN, workspace=WORKSPACE, lead=LEAD, fail=False):
        result=self.sql(f"SELECT public.import_acquisition_permission('{workspace}','{lead}','{point}',{literal(source)},"
                        f"'90000000-0000-4000-8000-000000000001',{literal(channel)});", user=actor, fail=fail)
        return result if fail else json.loads(result)

    def test_permission_evidence_is_versioned_unreviewed_and_never_authorizes(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt()
        first=self.permission(point)
        self.assertEqual(first,self.permission(point))
        self.assertEqual(first['selection'],'affirmative')
        self.assertEqual(first['review_status'],'unreviewed')
        self.assertEqual(first['scope'],'property_inquiry')
        self.assertEqual(first['expiry_basis'],'not_reviewed')
        self.assertTrue(first['disclosure_version'].startswith('sha256:'))
        self.assertEqual(self.evaluate(point,channel='sms')['decision'],'REVIEW')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='evidence_imported'"),'1')
        self.sql('DELETE FROM acquisition_contact_permissions;',fail=True)
        self.permission(point,channel='ai_voice',fail=True)

    def test_native_channels_are_independent_and_false_is_preserved(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt(source='facebook')
        sms=self.permission(point,source='facebook')
        ai=self.permission(point,source='facebook',channel='ai_voice')
        self.assertEqual(sms['selection'],'affirmative')
        self.assertEqual(ai['selection'],'declined')
        self.assertNotEqual(sms['id'],ai['id'])
        self.assertNotEqual(sms['disclosure_version'],ai['disclosure_version'])

    def test_permission_unknown_or_inconsistent_evidence_never_becomes_affirmative(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt(source='facebook',when='2020-01-01')
        self.assertEqual(self.permission(point,source='facebook')['selection'],'unknown')
        self.sql("UPDATE facebook_lead_submissions SET submitted_at='2020-01-01T12:00:00Z';")
        self.assertEqual(self.permission(point,source='facebook')['selection'],'unknown')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_permissions'),'2')

    def test_duplicate_native_checkbox_and_future_timestamp_remain_unknown(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt(source='facebook',when='2999-01-01T12:00:00Z')
        self.assertEqual(self.permission(point,source='facebook')['selection'],'unknown')
        self.sql("UPDATE facebook_lead_submissions SET submitted_at='2020-01-01T12:00:00Z',raw_answers=jsonb_set(raw_answers,'{_facebook_consent,submitted_at}',to_jsonb('2020-01-01T12:00:00Z'::text));")
        self.sql("UPDATE facebook_lead_submissions SET raw_answers=jsonb_set(raw_answers,'{_facebook_consent,raw_responses}',"
                 "(raw_answers#>'{_facebook_consent,raw_responses}')||jsonb_build_array(raw_answers#>'{_facebook_consent,raw_responses,0}'));")
        self.assertEqual(self.permission(point,source='facebook')['selection'],'unknown')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_permissions'),'2')

    def test_revocation_collision_rolls_back_entire_transaction(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt()
        permission=self.permission(point)['id']
        self.suppress(point)  # Existing ID targets all channels, not the SMS-only revocation.
        self.sql(f"SELECT public.revoke_acquisition_permission('50000000-0000-4000-8000-000000000001','{WORKSPACE}',"
                 f"'{permission}','seller_revoked');",user=ADMIN,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_permission_revocations'),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='revoked' AND entity_type='contact_permission'"),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_suppressions'),'1')

    def test_permission_requires_matching_receipt_contact_and_workspace(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt(phone='+12145550102')
        self.permission(point,fail=True)
        self.permission(point,actor=OTHER,fail=True)
        self.permission(point,lead=LEAD_B,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_permissions'),'0')

    def test_permission_revocation_atomically_suppresses_channel_and_keeps_evidence(self):
        self.bind()
        point=self.import_contact()['contact_point_id']
        self.permission_receipt()
        permission=self.permission(point)['id']
        self.member(target=CALLER,role='acquisition_caller')
        query=(f"SELECT public.revoke_acquisition_permission('a0000000-0000-4000-8000-000000000001','{WORKSPACE}',"
               f"'{permission}','seller_revoked');")
        self.sql(query,user=CALLER,fail=True)
        self.sql(f"SELECT public.assign_acquisition_lead('{WORKSPACE}','{LEAD}','{CALLER}');",user=ADMIN)
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        first=self.sql(query,user=CALLER)
        self.assertEqual(first,self.sql(query,user=CALLER))
        self.assertTrue(self.permission(point)['revoked'])
        self.assertEqual(self.evaluate(point,channel='sms')['decision'],'BLOCK')
        self.assertEqual(self.evaluate(point,channel='ai_voice',actor_type='ai')['decision'],'REVIEW')
        self.assertEqual(self.sql('SELECT effective_status FROM acquisition_permission_status',user=ADMIN),'revoked')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_permission_status',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_permission_status',user=CALLER),'0')
        self.sql('DELETE FROM acquisition_permission_revocations;',fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_permissions'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_suppressions'),'1')

    def owner(self, owner_id='60000000-0000-4000-8000-000000000001', actor=ADMIN, workspace=WORKSPACE, lead=LEAD, fail=False):
        result = self.sql(f"SELECT public.create_acquisition_owner('{owner_id}','{workspace}','{lead}');", user=actor, fail=fail)
        return result if fail else json.loads(result)

    def owner_property(self, relationship_id='70000000-0000-4000-8000-000000000001', owner_id='60000000-0000-4000-8000-000000000001',
                       actor=ADMIN, workspace=WORKSPACE, lead=LEAD, fail=False):
        result = self.sql(f"SELECT public.associate_acquisition_owner('{relationship_id}','{workspace}','{owner_id}',"
                          f"'{lead}','reported_owner','Synthetic operator review; title not verified');", user=actor, fail=fail)
        return result if fail else json.loads(result)

    def test_owner_same_name_does_not_merge_and_retries_preserve_source(self):
        self.sql("UPDATE leads SET owner_first_name='Jane',owner_last_name='Fixture';")
        self.bind()
        self.bind(lead=LEAD_B, property_id=None)
        first = self.owner()
        self.assertEqual(first, self.owner())
        second = self.owner(owner_id='60000000-0000-4000-8000-000000000002', lead=LEAD_B)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['display_name'], second['display_name'])
        self.assertEqual(first['verification_status'], 'unverified')
        self.sql(f"UPDATE leads SET owner_last_name='Changed' WHERE id='{LEAD}';")
        self.assertEqual(self.owner()['source_evidence']['owner_last_name'], 'Fixture')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_owner'"), '2')
        self.owner(lead=LEAD_B, fail=True)  # Same UUID cannot be reassigned to another source.
        self.sql('DELETE FROM acquisition_owners;', fail=True)

    def test_owner_relations_reuse_canonical_property_and_support_multiple_leads(self):
        self.sql("UPDATE leads SET owner_first_name='Jane',owner_last_name='Fixture';")
        self.bind()
        self.bind(lead=LEAD_B, property_id=None)
        self.owner()
        first = self.owner_property()
        self.assertEqual(first, self.owner_property())
        self.assertEqual(first['property_id'], PROPERTY)
        second = self.owner_property(relationship_id='70000000-0000-4000-8000-000000000002', lead=LEAD_B)
        self.assertIsNone(second['property_id'])
        self.assertEqual(first['owner_id'],second['owner_id'])
        self.assertFalse(first['evidence']['title_verified'])
        self.assertEqual(self.sql('SELECT count(*) FROM wholesale_ingest.properties'), '1')
        self.sql('UPDATE acquisition_owner_properties SET relationship=relationship;', fail=True)

    def test_owner_relations_require_admin_and_workspace_scope(self):
        self.sql("UPDATE leads SET owner_first_name='Jane',owner_last_name='Fixture';")
        self.bind()
        self.member()
        self.owner(actor=OPERATOR)
        self.owner_property(actor=OPERATOR, fail=True)
        self.owner_property(actor=OTHER, fail=True)
        self.owner_property(workspace=WORKSPACE_B, fail=True)
        self.owner_property(lead=LEAD_B, fail=True)
        self.owner_property()
        self.member(target=CALLER,role='acquisition_caller')
        self.owner(actor=CALLER, fail=True)
        for table in ('acquisition_owners','acquisition_owner_properties','acquisition_owner_contacts'):
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table}',user=CALLER),'0')
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table}',user=OTHER),'0')
        self.sql(f"UPDATE acquisition_owners SET verification_status='verified';", user=ADMIN, fail=True)

    def test_owner_contact_link_requires_same_lead_observation_and_never_grants_consent(self):
        self.sql("UPDATE leads SET owner_first_name='Jane',owner_last_name='Fixture';")
        self.bind()
        self.bind(lead=LEAD_B, property_id=None)
        self.owner()
        relation=self.owner_property()['id']
        point=self.import_contact(lead=LEAD_B)['contact_point_id']
        query=(f"SELECT public.associate_acquisition_owner_contact('80000000-0000-4000-8000-000000000001','{WORKSPACE}',"
               f"'{relation}','{point}','Synthetic contact association review');")
        self.sql(query,user=ADMIN,fail=True)
        self.import_contact()
        first=json.loads(self.sql(query,user=ADMIN))
        self.assertEqual(first,json.loads(self.sql(query,user=ADMIN)))
        self.assertFalse(first['evidence']['consent_inferred'])
        self.assertEqual(first['verification_status'],'unverified')
        self.assertEqual(self.evaluate(point)['decision'],'REVIEW')
        self.sql(query,user=OTHER,fail=True)
        self.sql('DELETE FROM acquisition_owner_contacts;',fail=True)

    def test_owner_incomplete_intake_and_disabled_activation_block_creation(self):
        self.bind()
        self.owner(fail=True)
        self.sql("UPDATE leads SET owner_first_name='Jane';")
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.owner(fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_owners'),'0')

    def evaluate(self, contact, actor=ADMIN, workspace=WORKSPACE, lead=LEAD, channel='human_voice', actor_type='human', campaign=None, fail=False, aal='aal2'):
        result = self.sql(f"SELECT public.evaluate_acquisition_eligibility('{workspace}','{lead}','{contact}',"
                          f"{literal(channel)},'principal_property_acquisition',{literal(actor_type)},"
                          f"{literal(campaign) if campaign else 'NULL'});", user=actor, fail=fail, aal=aal)
        return result if fail else json.loads(result)

    def suppress(self, contact, actor=ADMIN, workspace=WORKSPACE, lead=LEAD, channel='all', fail=False):
        result = self.sql(f"SELECT public.record_acquisition_suppression('50000000-0000-4000-8000-000000000001',"
                          f"'{workspace}','{lead}','{contact}',{literal(channel)},'seller_opt_out');", user=actor, fail=fail)
        return result if fail else json.loads(result)

    def test_pending_eligibility_records_fresh_immutable_nonpermissions(self):
        self.bind()
        point = self.import_contact()['contact_point_id']
        first = self.evaluate(point)
        second = self.evaluate(point)
        self.assertNotEqual(first['decision_id'], second['decision_id'])
        self.assertEqual(first['decision'], 'REVIEW')
        self.assertEqual(first['reason_codes'], ['LEGAL_POLICY_NOT_APPROVED'])
        self.assertEqual(first['permitted_actions'], [])
        self.assertIsNone(first['expires_at'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_eligibility_decisions'), '2')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='eligibility_decision'"), '2')
        self.assertEqual(self.sql("SELECT inputs->>'actor_type' FROM acquisition_eligibility_decisions LIMIT 1"), 'human')
        self.sql("UPDATE acquisition_eligibility_decisions SET decision='ALLOW';", fail=True)
        self.sql('DELETE FROM acquisition_eligibility_decisions;', fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_eligibility_decisions', user=OTHER), '0')

    def test_suppression_matches_other_workspace_without_disclosing_identity(self):
        self.bind()
        self.bind(actor=OTHER, workspace=WORKSPACE_B, lead=LEAD_B, property_id=None)
        point = self.import_contact()['contact_point_id']
        other = self.import_contact(actor=OTHER, workspace=WORKSPACE_B, lead=LEAD_B)['contact_point_id']
        first = self.suppress(other, actor=OTHER, workspace=WORKSPACE_B, lead=LEAD_B, channel='sms')
        self.assertEqual(first, self.suppress(other, actor=OTHER, workspace=WORKSPACE_B, lead=LEAD_B, channel='sms'))
        self.assertEqual(self.evaluate(point, channel='sms')['decision'], 'BLOCK')
        self.assertEqual(self.evaluate(point)['decision'], 'REVIEW')
        result = self.evaluate(point, channel='sms')
        self.assertNotIn(WORKSPACE_B, json.dumps(result))
        self.assertNotIn(other, json.dumps(result))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_suppressions', user=ADMIN), '0')
        self.sql('DELETE FROM acquisition_contact_suppressions;', fail=True)
        self.suppress(point, fail=True)  # Same request UUID cannot replace another tenant's event.

    def test_assigned_caller_can_record_opt_out_and_evaluate_without_contact_export(self):
        self.bind()
        point = self.import_contact()['contact_point_id']
        self.member(target=CALLER, role='acquisition_caller')
        self.evaluate(point, actor=CALLER, fail=True)
        self.sql(f"SELECT public.assign_acquisition_lead('{WORKSPACE}','{LEAD}','{CALLER}');", user=ADMIN)
        self.evaluate(point, actor=CALLER, aal='aal1', fail=True)
        self.assertEqual(self.evaluate(point, actor=CALLER)['decision'], 'REVIEW')
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.suppress(point, actor=CALLER)
        self.assertEqual(self.evaluate(point, actor=CALLER)['decision'], 'BLOCK')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_points', user=CALLER), '0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_eligibility_decisions', user=CALLER), '0')
        self.member(target=CALLER, role='acquisition_caller', status='revoked')
        self.evaluate(point, actor=CALLER, fail=True)

    def test_legacy_formatted_dnc_matches_across_leads(self):
        self.bind()
        point = self.import_contact()['contact_point_id']
        self.sql(f"INSERT INTO dnc_registry(lead_id,phone_number,reason) VALUES('{LEAD_B}','(214) 555-0101','opt_out');")
        self.assertEqual(self.evaluate(point)['decision'], 'BLOCK')
        self.sql('DELETE FROM dnc_registry;')
        self.sql(f"UPDATE leads SET dnc=true WHERE id='{LEAD_B}';")
        self.assertEqual(self.evaluate(point,channel='ai_voice',actor_type='ai')['decision'], 'BLOCK')

    def test_email_and_retained_skiptrace_restrictions(self):
        self.sql(f"UPDATE leads SET owner_email='seller@example.test' WHERE id='{LEAD}';")
        self.bind()
        email = self.import_contact(field='owner_email')['contact_point_id']
        self.sql("INSERT INTO email_suppressions(email,reason) VALUES('seller@example.test','bounce');")
        self.assertEqual(self.evaluate(email, channel='email')['decision'], 'BLOCK')
        source = '40000000-0000-4000-8000-000000000001'
        self.sql(f"INSERT INTO wholesale_ingest.contacts(id,lead_id,provider,traced_at,expires_at,phone,dnc_status) "
                 f"VALUES('{source}','{LEAD}','fixture',now(),now()+interval '1 day','+12145550101','listed');")
        phone = self.import_contact(source=source, field='phone')['contact_point_id']
        self.sql('DELETE FROM wholesale_ingest.contacts;')
        self.assertEqual(self.evaluate(phone)['decision'], 'BLOCK')

    def test_eligibility_rejects_mismatched_lead_and_invalid_actor(self):
        self.bind()
        point = self.import_contact()['contact_point_id']
        self.evaluate(point, lead=LEAD_B, fail=True)
        self.evaluate(point, actor=OTHER, fail=True)
        self.evaluate(point, channel='human_voice', actor_type='ai', fail=True)
        self.assertEqual(self.evaluate(point, channel='email')['decision'], 'BLOCK')
        self.assertIn('CAMPAIGN_SCOPE_NOT_VERIFIED', self.evaluate(point, campaign=OTHER)['reason_codes'])
        self.assertEqual(self.evaluate(point, channel='direct_mail')['permitted_actions'], [])

    def import_contact(self, actor=ADMIN, workspace=WORKSPACE, lead=LEAD, source=None, field='owner_phone_1', fail=False):
        value = self.sql(f"SELECT public.import_acquisition_contact('{workspace}','{lead}',"
                         f"{literal(source) if source else 'NULL'},{literal(field)});", user=actor, fail=fail)
        return value if fail else json.loads(value)

    def test_contact_crosswalk_is_idempotent_and_does_not_merge_leads(self):
        self.bind()
        self.bind(lead=LEAD_B, property_id=None)
        first = self.import_contact()
        self.assertEqual(first, self.import_contact())
        second = self.import_contact(lead=LEAD_B)
        self.assertEqual(first['contact_point_id'], second['contact_point_id'])
        self.assertNotEqual(first['observation_id'], second['observation_id'])
        self.assertEqual(first['verification_status'], 'unverified')
        self.assertEqual(self.sql('SELECT count(*) FROM leads'), '2')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_observations'), '2')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='source_imported'"), '2')
        self.sql('UPDATE acquisition_contact_points SET normalized_value=normalized_value;', fail=True)
        self.sql('DELETE FROM acquisition_contact_observations;', fail=True)

    def test_same_endpoint_in_other_workspace_is_separate_and_updates_append(self):
        self.bind()
        self.bind(actor=OTHER, workspace=WORKSPACE_B, lead=LEAD_B, property_id=None)
        first = self.import_contact()
        other = self.import_contact(actor=OTHER, workspace=WORKSPACE_B, lead=LEAD_B)
        self.assertNotEqual(first['contact_point_id'], other['contact_point_id'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_points', user=ADMIN), '1')
        self.sql(f"UPDATE leads SET owner_phone_1='+12145550109' WHERE id='{LEAD}';")
        changed = self.import_contact()
        self.assertNotEqual(first['contact_point_id'], changed['contact_point_id'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contact_observations WHERE lead_id='{LEAD}'"), '2')
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contact_points WHERE normalized_value='+12145550101'"), '2')

    def test_contact_import_is_workspace_scoped_and_operator_only(self):
        self.bind()
        self.member(target=CALLER, role='acquisition_caller')
        self.import_contact(actor=OTHER, fail=True)
        self.import_contact(actor=CALLER, fail=True)
        self.import_contact(workspace=WORKSPACE_B, fail=True)
        self.member()
        value = self.import_contact(actor=OPERATOR)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_points', user=OPERATOR), '1')
        for actor in (OTHER,CALLER):
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_points', user=actor), '0')
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_observations', user=actor), '0')
        self.sql(f"INSERT INTO acquisition_contact_points(workspace_id,type,normalized_value,created_by) "
                 f"VALUES('{WORKSPACE}','phone','+12145550102','{ADMIN}');", user=ADMIN, fail=True)
        self.assertTrue(value['contact_point_id'])

    def test_phone_normalization_rejects_ambiguous_extensions_and_preserves_original(self):
        self.sql(f"UPDATE leads SET owner_phone_1='(214) 555-0101',owner_phone_2='2145550101 ext 3',"
                 f"owner_email=' Owner@Example.test ' WHERE id='{LEAD}';")
        self.bind()
        self.import_contact()
        self.import_contact(field='owner_phone_2', fail=True)
        email = self.import_contact(field='owner_email')
        self.assertEqual(email['type'], 'email')
        self.assertEqual(self.sql("SELECT normalized_value FROM acquisition_contact_points WHERE type='phone'"), '+12145550101')
        self.assertEqual(self.sql("SELECT evidence->>'raw_value' FROM acquisition_contact_observations WHERE source_field='owner_phone_1'"), '(214) 555-0101')
        self.assertEqual(self.sql("SELECT normalized_value FROM acquisition_contact_points WHERE type='email'"), 'owner@example.test')
        self.import_contact(field='property_address', fail=True)

    def test_skiptrace_crosswalk_preserves_expiry_and_survives_source_retention(self):
        source = '40000000-0000-4000-8000-000000000001'
        self.sql(f"INSERT INTO wholesale_ingest.contacts(id,lead_id,provider,traced_at,expires_at,phone,email,dnc_status) "
                 f"VALUES('{source}','{LEAD}','fixture',now()-interval '2 days',now()-interval '1 day','+12145550101','seller@example.test','unknown');")
        self.bind()
        phone = self.import_contact(source=source, field='phone')
        email = self.import_contact(source=source, field='email')
        self.assertNotEqual(phone['contact_point_id'],email['contact_point_id'])
        self.bind(lead=LEAD_B, property_id=None)
        self.import_contact(lead=LEAD_B, source=source, field='phone', fail=True)
        self.sql(f"DELETE FROM wholesale_ingest.contacts WHERE id='{source}';")
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contact_observations WHERE (evidence->>'expires_at')::timestamptz<now()"), '2')
        self.import_contact(source=source, field='phone', fail=True)

    def test_contact_creation_requires_activation_and_parallel_import_deduplicates(self):
        self.bind()
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda _: self.import_contact(), range(2)))
        self.assertEqual(values[0], values[1])
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.bind(lead=LEAD_B, property_id=None, fail=True)
        self.sql(f"UPDATE leads SET owner_phone_2='+12145550103' WHERE id='{LEAD}';")
        self.import_contact(field='owner_phone_2', fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contact_points'), '1')

    def activate(self):
        self.sql("UPDATE private.acquisition_activation SET enabled=true, approval_ref='isolated-test-approval', "
                 "application_revision=repeat('a',40),verified_at=now();")

    def test_activation_defaults_closed(self):
        error = self.sql(f"SELECT public.create_acquisition_workspace('{WORKSPACE}','test');", user=ADMIN, fail=True)
        self.assertIn('activation approval required', error)
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces'), '0')
        self.sql('UPDATE private.acquisition_activation SET enabled=true;', fail=True)
        for role in ('authenticated', 'service_role'):
            self.sql('UPDATE private.acquisition_activation SET enabled=true;', user=ADMIN, role=role, fail=True)
        self.activate()
        self.create(ADMIN, WORKSPACE)
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_activation_events'), '1')
        self.sql('DELETE FROM private.acquisition_activation_events;', fail=True)
        self.sql('DELETE FROM private.acquisition_activation;', fail=True)

    def test_disabling_blocks_enrollment_binding_but_allows_revocation(self):
        self.member()
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.assertIn('activation approval required', self.bind(fail=True))
        self.member(target=CALLER, role='acquisition_caller', fail=True)
        self.member(status='revoked')
        self.assertEqual(self.sql(f"SELECT status FROM workspace_memberships WHERE user_id='{OPERATOR}'"), 'revoked')
        self.assertEqual(self.sql(f"SELECT acquisition_only FROM profiles WHERE id='{CALLER}'"), 'f')
        self.assertEqual(self.sql('SELECT count(*) FROM workspace_leads'), '0')
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_activation_events'), '2')

    def create(self, actor, workspace):
        return self.sql(f"SELECT public.create_acquisition_workspace('{workspace}','Hilltop test');", user=actor)

    def member(self, target=OPERATOR, role='operator', status='active', actor=ADMIN, fail=False):
        return self.sql(f"SELECT public.set_acquisition_membership('{WORKSPACE}','{target}','{role}','{status}');", user=actor, fail=fail)

    def bind(self, actor=ADMIN, workspace=WORKSPACE, lead=LEAD, property_id=PROPERTY, fail=False):
        prop = literal(property_id) if property_id else 'NULL'
        return self.sql(f"SELECT public.bind_acquisition_lead('{workspace}','{lead}',{prop});", user=actor, fail=fail)

    def queue(self, actor=CALLER, workspace=WORKSPACE, aal='aal2', fail=False):
        data = self.sql(f"SELECT public.list_acquisition_leads('{workspace}');", user=actor, aal=aal, fail=fail)
        return data if fail else json.loads(data)

    def test_restricted_account_cannot_inherit_legacy_table_access(self):
        self.member(target=CALLER, role='acquisition_caller')
        self.assertEqual(self.sql('SELECT count(*) FROM campaigns;', user=CALLER), '0')
        self.assertEqual(self.sql('SELECT count(*) FROM leads;', user=CALLER), '0')
        self.assertEqual(self.sql('SELECT count(*) FROM campaigns;', user=ADMIN), '1')
        self.member(target=CALLER, role='acquisition_caller', status='revoked')
        self.assertEqual(self.sql('SELECT count(*) FROM campaigns;', user=CALLER), '0')
        self.assertEqual(self.sql(f"SELECT acquisition_only FROM profiles WHERE id='{CALLER}';"), 't')

    def test_migration_scopes_preexisting_memberships(self):
        self.assertEqual(self.sql(f"SELECT acquisition_only FROM profiles WHERE id='{OPERATOR}';"), 't')
        self.assertEqual(self.sql('SELECT count(*) FROM campaigns;', user=OPERATOR), '0')

    def test_platform_admin_cannot_be_enrolled_as_limited_caller(self):
        self.member(target=OTHER, role='acquisition_caller', fail=True)
        self.assertEqual(self.sql(f"SELECT acquisition_only FROM profiles WHERE id='{OTHER}';"), 'f')

    def test_binding_preserves_canonical_property_and_does_not_merge_phone_matches(self):
        before = self.sql(f"SELECT row_to_json(p) FROM wholesale_ingest.properties p WHERE id='{PROPERTY}';")
        self.bind()
        self.bind()
        self.assertEqual(self.sql(f"SELECT row_to_json(p) FROM wholesale_ingest.properties p WHERE id='{PROPERTY}';"), before)
        self.assertEqual(self.sql('SELECT count(*) FROM leads;'), '2')
        self.assertEqual(self.sql('SELECT count(*) FROM workspace_leads;'), '1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='bound';"), '1')

    def test_binding_requires_authority_and_matching_property(self):
        self.member()
        self.bind(actor=OPERATOR, fail=True)
        self.bind(lead=LEAD_B, fail=True)
        self.bind()
        self.bind(actor=OTHER, workspace=WORKSPACE_B, fail=True)

    def test_cross_workspace_and_unbound_read_boundaries(self):
        self.bind()
        self.member()
        self.assertEqual(self.sql('SELECT count(*) FROM leads;', user=OPERATOR), '1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM leads WHERE id='{LEAD}';", user=OTHER), '0')
        self.assertEqual(self.sql(f"SELECT count(*) FROM leads WHERE id='{LEAD_B}';", user=OPERATOR), '0')
        self.sql(f"UPDATE leads SET property_address='changed' WHERE id='{LEAD}'; DELETE FROM leads WHERE id='{LEAD}';", user=OPERATOR)
        self.assertEqual(self.sql(f"SELECT property_address FROM leads WHERE id='{LEAD}';"), '1 Fixture St')

    def test_assignment_queue_has_no_unassigned_contacts_or_cross_workspace_access(self):
        self.bind()
        self.member(target=CALLER, role='acquisition_caller')
        self.assertEqual(self.queue(), [])
        self.sql(f"SELECT public.assign_acquisition_lead('{WORKSPACE}','{LEAD}','{CALLER}');", user=ADMIN)
        result = self.queue()
        self.assertEqual([r['lead_id'] for r in result], [LEAD])
        self.assertNotIn('owner_phone_1', result[0])
        self.assertEqual(self.sql('SELECT count(*) FROM leads;', user=CALLER), '0')
        self.queue(workspace=WORKSPACE_B, fail=True)
        self.queue(aal='aal1', fail=True)
        self.sql(f"SELECT public.assign_acquisition_lead('{WORKSPACE}','{LEAD}','{OTHER}');", user=ADMIN, fail=True)
        self.member(target=CALLER, role='acquisition_caller', status='revoked')
        self.queue(fail=True)

    def test_related_property_and_deal_records_follow_workspace(self):
        self.bind()
        self.member()
        self.sql(f"INSERT INTO wholesale_ingest.property_aliases(alias_key,property_id) VALUES('fixture-alias','{PROPERTY}'); "
                 f"INSERT INTO deals(id,lead_id,deal_name) VALUES('{LEAD}','{LEAD}','fixture-deal'); "
                 f"INSERT INTO buyers(id,first_name,last_name) VALUES('{OTHER}','Fixture','Buyer'); "
                 f"INSERT INTO deal_matches(deal_id,buyer_id) VALUES('{LEAD}','{OTHER}');")
        for table in ('wholesale_ingest.properties','wholesale_ingest.property_aliases','deals','deal_matches'):
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table};',user=OTHER),'0')
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table};',user=OPERATOR),'1')
            self.sql(f'DELETE FROM {table};',user=OPERATOR)
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table};'),'1')

    def test_bound_property_identity_cannot_drift(self):
        self.bind()
        self.sql(f"UPDATE wholesale_ingest.properties SET lead_id='{LEAD_B}' WHERE id='{PROPERTY}';", fail=True)
        self.assertEqual(self.sql(f"SELECT lead_id FROM wholesale_ingest.properties WHERE id='{PROPERTY}';"),LEAD)

    def test_mixed_workspace_parent_references_are_not_visible(self):
        self.bind()
        self.bind(actor=OTHER,workspace=WORKSPACE_B,lead=LEAD_B,property_id=None)
        self.sql(f"INSERT INTO deals(id,lead_id,deal_name) VALUES('{LEAD_B}','{LEAD_B}','other-deal');")
        self.assertEqual(self.sql(f"SELECT private.acquisition_record_access('{LEAD}','{LEAD_B}',NULL,false);",user=ADMIN),'f')
        self.assertEqual(self.sql(f"SELECT private.acquisition_record_access('{LEAD}','{LEAD_B}',NULL,false);",user=OTHER),'f')

    def test_workspace_and_membership_isolation(self):
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=ADMIN), '1')
        self.assertEqual(self.sql('SELECT count(*) FROM workspace_memberships;', user=ADMIN), '1')
        self.member()
        self.assertEqual(self.sql('SELECT count(*) FROM workspace_memberships;', user=OPERATOR), '1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspaces WHERE id='{WORKSPACE_B}';", user=OPERATOR), '0')
        self.member(target=CALLER, actor=OTHER, fail=True)

    def test_no_raw_membership_or_workspace_writes(self):
        for role in ('authenticated','anon','service_role'):
            self.sql(f"INSERT INTO workspace_memberships VALUES('{WORKSPACE}','{CALLER}','owner','active',now());", user=ADMIN, role=role, fail=True)
            self.sql(f"UPDATE workspaces SET status='suspended' WHERE id='{WORKSPACE}';", user=ADMIN, role=role, fail=True)

    def test_creation_requires_live_approved_admin(self):
        self.sql(f"SELECT public.create_acquisition_workspace(gen_random_uuid(),'denied');", user=OPERATOR, fail=True)
        self.sql("SELECT public.create_acquisition_workspace(gen_random_uuid(),'denied');", user=ADMIN, session=False, fail=True)
        self.sql("SELECT public.create_acquisition_workspace(gen_random_uuid(),'denied');", user=ADMIN, role='service_role', fail=True)

    def test_creation_retry_is_idempotent_and_cannot_steal_workspace(self):
        self.create(ADMIN, WORKSPACE)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE workspace_id='{WORKSPACE}';"), '1')
        self.sql(f"SELECT public.create_acquisition_workspace('{WORKSPACE}','Hilltop test');", user=OTHER, fail=True)
        self.sql(f"SELECT public.create_acquisition_workspace('{WORKSPACE}','changed');", user=ADMIN, fail=True)

    def test_current_session_and_profile_revocation(self):
        self.member()
        self.sql(f"UPDATE auth.sessions SET not_after=now()-interval '1 second' WHERE user_id='{OPERATOR}';")
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=OPERATOR), '0')
        self.sql(f"UPDATE auth.sessions SET not_after=NULL WHERE user_id='{OPERATOR}'; UPDATE profiles SET status='suspended' WHERE id='{OPERATOR}';")
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=OPERATOR), '0')
        self.sql(f"UPDATE profiles SET status='approved' WHERE id='{OPERATOR}'; DELETE FROM auth.sessions WHERE user_id='{OPERATOR}';")
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=OPERATOR), '0')

    def test_caller_and_agency_require_mfa(self):
        for role in ('acquisition_caller','agency_manager'):
            self.member(target=CALLER, role=role)
            self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=CALLER, aal='aal1'), '0')
            self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=CALLER, aal='aal2'), '1')
            self.member(target=OPERATOR, actor=CALLER, fail=True)

    def test_membership_revocation_is_immediate(self):
        self.member()
        self.member(status='revoked')
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=OPERATOR), '0')

    def test_approved_nonmember_and_suspended_workspace_have_no_access(self):
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=CALLER), '0')
        self.sql(f"UPDATE workspaces SET status='suspended' WHERE id='{WORKSPACE}';")
        self.assertEqual(self.sql('SELECT count(*) FROM workspaces;', user=ADMIN), '0')
        self.member(fail=True)

    def test_parallel_creation_has_one_membership_and_audit(self):
        workspace = '10000000-0000-4000-8000-000000000099'
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.create(ADMIN, workspace), range(8)))
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspace_memberships WHERE workspace_id='{workspace}';"), '1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE workspace_id='{workspace}';"), '1')

    def test_parallel_owner_removals_preserve_one_owner(self):
        self.member(target=OTHER, role='owner')
        def remove_self(user):
            try:
                self.member(target=user, role='owner', status='revoked', actor=user)
                return True
            except AssertionError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(remove_self, [ADMIN, OTHER]))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspace_memberships WHERE workspace_id='{WORKSPACE}' AND role='owner' AND status='active';"), '1')

    def test_caller_cannot_read_scoped_audit(self):
        self.member(target=CALLER, role='acquisition_caller')
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs WHERE workspace_id IS NOT NULL;', user=CALLER), '0')

    def test_admin_cannot_escalate_or_change_owner(self):
        self.member(role='admin')
        self.member(target=OPERATOR, role='owner', actor=OPERATOR, fail=True)
        self.member(target=ADMIN, role='operator', actor=OPERATOR, fail=True)
        self.member(target=CALLER, role='acquisition_caller', actor=OPERATOR)

    def test_last_owner_cannot_be_removed(self):
        self.member(target=ADMIN, role='owner', status='revoked', fail=True)
        self.member(target=ADMIN, role='operator', fail=True)
        self.member(target=OTHER, role='owner')
        self.member(target=ADMIN, role='operator', actor=OTHER)
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspace_memberships WHERE workspace_id='{WORKSPACE}' AND role='owner' AND status='active';"), '1')

    def test_invalid_roles_statuses_and_pending_targets_rejected(self):
        self.member(role='superuser', fail=True)
        self.member(status='unknown', fail=True)
        self.sql(f"UPDATE profiles SET status='pending' WHERE id='{OPERATOR}';")
        self.member(fail=True)

    def test_audit_is_scoped_append_only_and_retries_do_not_duplicate(self):
        self.member()
        self.member()
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE workspace_id='{WORKSPACE}';"), '2')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE workspace_id='{WORKSPACE_B}';", user=ADMIN), '0')
        for query in (f"UPDATE audit_logs SET action='forged' WHERE workspace_id='{WORKSPACE}';",
                      f"DELETE FROM audit_logs WHERE workspace_id='{WORKSPACE}';", 'TRUNCATE audit_logs;'):
            self.sql(query, user=ADMIN, role='service_role', fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_id='sentinel' AND action='historical';"), '1')
        self.sql("INSERT INTO audit_logs(entity_type,entity_id,action,actor) VALUES('legacy','new-sentinel','appended','system');", user=ADMIN, role='service_role')


def main(test_case=WorkspaceTests, test_names=None):
    for executable in ('initdb','pg_ctl','createdb','psql'):
        if not (PG/executable).is_file():
            raise SystemExit('Set PG_BIN to a local PostgreSQL bin directory')
    with tempfile.TemporaryDirectory(prefix='acq-', dir='/tmp') as folder:
        env = {'PATH': '/usr/bin:/bin', 'HOME': folder, 'TMPDIR': folder, 'LANG': 'C', 'PGCONNECT_TIMEOUT': '5'}
        data = Path(folder)/'data'
        def run(args):
            return subprocess.run([str(x) for x in args], check=True, env=env, stdout=subprocess.DEVNULL)
        run([PG/'initdb','-D',data,'-U','test_admin','--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'])
        with (data/'postgresql.conf').open('a') as f:
            f.write(f"\nlisten_addresses=''\nunix_socket_directories='{folder}'\n")
        started = False
        try:
            run([PG/'pg_ctl','-D',data,'-l',Path(folder)/'postgres.log','-w','start'])
            started = True
            run([PG/'createdb','-h',folder,'-U','test_admin','acquisition_test'])
            WorkspaceTests.env, WorkspaceTests.socket = env, folder
            check = WorkspaceTests()
            check.sql('CREATE ROLE authenticated NOLOGIN; CREATE ROLE anon NOLOGIN; CREATE ROLE service_role NOLOGIN BYPASSRLS;')
            suite = (unittest.TestSuite(test_case(name) for name in test_names) if test_names is not None
                     else unittest.defaultTestLoader.loadTestsFromTestCase(test_case))
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            if started:
                run([PG/'pg_ctl','-D',data,'-m','immediate','-w','stop'])


if __name__ == '__main__':
    raise SystemExit(main())
