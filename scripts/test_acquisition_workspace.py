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
from acquisition_campaign_fixture import install_campaign_fixture
from acquisition_call_fixture import install_call_fixture
from acquisition_task_fixture import install_task_fixture

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
INTAKE_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026162924_acquisition_seller_intakes.sql'
BATCH_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026163900_acquisition_facebook_batch_acceptance.sql'
HEALTH_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026165322_acquisition_inquiry_health.sql'
RECOVERY_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026170113_acquisition_inquiry_recovery.sql'
CANDIDATES_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026171817_acquisition_intake_candidates.sql'
IDENTITY_REVIEW_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026173422_acquisition_intake_identity_reviews.sql'
QUALIFICATION_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026181452_acquisition_intake_qualification.sql'
HANDOFF_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026184848_acquisition_intake_underwriting_handoff.sql'
CAMPAIGN_MIGRATION = ROOT / 'frontend/supabase/migrations/20261026205233_acquisition_campaign_ownership.sql'
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
            claims = {'sub': user, 'aal': aal, 'role': role}
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
                 "CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT (auth.jwt()->>'sub')::uuid $$; "
                 "CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT auth.jwt()->>'role' $$;")
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
        install_campaign_fixture(self.sql)
        install_call_fixture(self.sql)
        install_task_fixture(self.sql)
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
        self.sql(INTAKE_MIGRATION.read_text())
        self.sql(BATCH_MIGRATION.read_text())
        self.sql(HEALTH_MIGRATION.read_text())
        self.sql(RECOVERY_MIGRATION.read_text())
        self.sql(CANDIDATES_MIGRATION.read_text())
        self.sql(IDENTITY_REVIEW_MIGRATION.read_text())
        self.sql(QUALIFICATION_MIGRATION.read_text())
        self.sql(HANDOFF_MIGRATION.read_text())
        self.sql(CAMPAIGN_MIGRATION.read_text())
        self.sql((ROOT/"frontend/supabase/migrations/20261026214412_acquisition_campaign_links.sql").read_text())
        if self._testMethodName != 'test_source_migration_backfills_without_changing_intakes':
            self.sql((ROOT/'frontend/supabase/migrations/20261026221434_acquisition_lead_sources.sql').read_text())
            self.sql((ROOT/'frontend/supabase/migrations/20261026223054_acquisition_property_source_touches.sql').read_text())
        if self._testMethodName == 'test_cost_migration_preserves_populated_legacy_metrics':
            self.sql("INSERT INTO fb_campaign_performance(id,date,spend,leads) VALUES('94000000-0000-4000-8000-000000000001','2026-10-24',123.45,3)")
            self.legacy_cost_before=self.sql("SELECT jsonb_build_object('id',id,'date',date,'spend',spend,'leads',leads,'cpl',cpl)::text FROM fb_campaign_performance")
        if self._testMethodName != 'test_source_migration_backfills_without_changing_intakes':
            self.sql((ROOT/'frontend/supabase/migrations/20261026234504_acquisition_cost_evidence.sql').read_text())
        if self._testMethodName == 'test_inbound_migration_preserves_populated_legacy_events':
            self.sql("INSERT INTO call_events(id,disposition,notes,raw_payload) VALUES('97000000-0000-4000-8000-000000000001','no_answer','historical legacy note','{\"sentinel\":true}')")
            self.legacy_call_before=self.sql("SELECT jsonb_strip_nulls(to_jsonb(c)) FROM call_events c")
        self.sql((ROOT/'frontend/supabase/migrations/20261027010558_acquisition_inbound_event_ledger.sql').read_text())
        if self._testMethodName == 'test_inbound_task_migration_preserves_legacy':
            self.sql("INSERT INTO tasks(title,description,priority,status) VALUES('Sentinel legacy task','Preserve history','high','pending')")
            self.legacy_task_before=self.sql('SELECT jsonb_strip_nulls(to_jsonb(t)) FROM tasks t')
        self.sql((ROOT/'frontend/supabase/migrations/20261027013724_acquisition_inbound_review_tasks.sql').read_text())
        if self._testMethodName not in ('test_source_migration_backfills_without_changing_intakes','test_inbound_intake_migration_preserves_populated_facebook'):
            self.sql((ROOT/'frontend/supabase/migrations/20261027015624_acquisition_inbound_intakes.sql').read_text())
        if self._testMethodName != 'test_activation_defaults_closed':
            self.activate()
        if self._testMethodName != 'test_activation_defaults_closed':
            self.create(ADMIN, WORKSPACE)
            self.create(OTHER, WORKSPACE_B)
        self.sql(f"INSERT INTO leads(id,property_address,city,owner_phone_1) VALUES ('{LEAD}','1 Fixture St','Dallas','+12145550101'),('{LEAD_B}','2 Fixture St','Plano','+12145550101'); "
                 f"INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES('{PROPERTY}','TX','Dallas','fixture-parcel','{LEAD}'); "
                 "INSERT INTO campaigns(name) VALUES('legacy-sentinel');")

    def inbound_intake(self, *, request='99000000-0000-4000-8000-000000000001',revision=0,call='call_test',answers=None,prepared=None,role='service_role',fail=False):
        import importlib.util
        spec=importlib.util.spec_from_file_location('shared_intake',ROOT/'tools/acquisition_intake.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        values=answers or {'property_address':'123 Main St','city':'Dallas','state':'TX','authority':'yes','condition':'needs repairs','timeline':'30 days','motivation':'moving','asking_price':'150000','phone':'2145550101'}
        data=prepared or {'version':'seller-intake-v1',**module.normalize_seller_fields([{'name':k,'values':[v]} for k,v in sorted(values.items())])}
        result=self.sql(f"SELECT public.record_acquisition_inbound_intake('96000000-0000-4000-8000-000000000001','+12145550100','agent_test',3,{literal(call)},'{request}',{revision},{literal(json.dumps(data))}::jsonb)",user=ADMIN,role=role,fail=fail)
        return result if fail else json.loads(result)

    def test_inbound_intake_migration_preserves_populated_facebook(self):
        intake=self.campaign_link_fixture()
        before=self.sql(f"SELECT jsonb_strip_nulls(to_jsonb(i)) FROM seller_intakes i WHERE id='{intake}'")
        source=self.sql(f"SELECT jsonb_strip_nulls(to_jsonb(s)) FROM acquisition_lead_sources s WHERE id='{intake}'")
        self.sql((ROOT/'frontend/supabase/migrations/20261027015624_acquisition_inbound_intakes.sql').read_text())
        self.assertEqual(self.sql(f"SELECT jsonb_strip_nulls(to_jsonb(i)) FROM seller_intakes i WHERE id='{intake}'"),before)
        self.assertEqual(self.sql(f"SELECT jsonb_strip_nulls(to_jsonb(s)) FROM acquisition_lead_sources s WHERE id='{intake}'"),source)
        self.inbound_fixture();self.inbound_accept();self.inbound_intake()
        self.assertEqual(self.sql("SELECT count(*) FROM seller_intakes WHERE source_type='facebook_native_form' AND receipt_id IS NOT NULL"),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_lead_sources WHERE source_type='retell_inbound' AND external_campaign_id IS NULL"),'1')

    def test_inbound_intake_revisions_keep_one_lead_and_supersede_qualification(self):
        self.inbound_fixture();self.inbound_accept();first=self.inbound_intake()
        self.assertTrue(self.inbound_intake()['duplicate'])
        self.assertFalse(first['execution_authorized'])
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='retell_inbound_acquisition'"),'1')
        original=self.sql(f"SELECT to_jsonb(l) FROM leads l WHERE id='{first['lead_id']}'")
        self.bind()
        self.identity_review(first['id'],self.identity_state(first['id']))
        qualified=self.qualification_state(first['id'])
        self.assertEqual(qualified['assessment']['classification'],'qualified')
        self.record_assessment(first['id'],qualified)
        self.assertTrue(self.qualification_state(first['id'])['assessment_current'])
        second=self.inbound_intake(request='99000000-0000-4000-8000-000000000002',revision=1,answers={'property_address':'456 Changed St','city':'Dallas','asking_price':'150k'})
        self.assertEqual(second['lead_id'],first['lead_id']);self.assertEqual(second['revision'],2)
        self.assertEqual(self.sql(f"SELECT to_jsonb(l) FROM leads l WHERE id='{first['lead_id']}'"),original)
        old=json.loads(self.sql(f"SELECT public.acquisition_intake_qualification_state('{WORKSPACE}','{first['id']}')",user=ADMIN))
        self.assertEqual(old['assessment']['reason_codes'],['SUPERSEDED_INBOUND_INTAKE'])
        self.assertFalse(old['assessment_current'])
        self.assertEqual(old['latest_assessment']['classification'],'qualified')
        self.assertFalse(old['assessment']['binding_offer'])
        self.assertEqual(self.sql(f"SELECT prepared_answers->>'asking_price' IS NULL FROM seller_intakes WHERE id='{second['id']}'"),'t')
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_lead_sources WHERE source_type='retell_inbound' AND receipt_id IS NULL AND external_campaign_id IS NULL"),'2')
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='retell_inbound_acquisition' AND (sms_sequence_active OR email_sequence_active OR NOT ai_calling_paused OR retention_deletable)"),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes',user=OTHER),'0')
        self.sql(f"UPDATE seller_intakes SET classification='unqualified' WHERE id='{first['id']}'",fail=True)

    def test_inbound_intake_gate_replay_and_no_phone_merge(self):
        self.inbound_fixture();self.inbound_intake(fail=True)
        self.inbound_accept();self.inbound_intake(role='authenticated',fail=True)
        first=self.inbound_intake()
        self.assertNotEqual(first['lead_id'],LEAD)  # Same supplied phone, unrelated identity.
        self.inbound_intake(answers={'property_address':'Changed'},fail=True)
        self.inbound_intake(request='99000000-0000-4000-8000-000000000002',fail=True)
        self.inbound_accept(self.inbound_data('call_ended'))
        self.assertTrue(self.inbound_intake()['duplicate'])
        self.inbound_intake(request='99000000-0000-4000-8000-000000000002',revision=1,fail=True)
        self.sql('UPDATE private.acquisition_inbound_routes SET enabled=false')
        self.inbound_intake(fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'1')

    def test_inbound_intake_concurrent_replay_and_invalid_authority(self):
        self.inbound_fixture();self.inbound_accept()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.inbound_intake(),range(3)))
        self.assertEqual(len({r['id'] for r in results}),1)
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake' AND action='created'"),'1')
        data=json.loads(self.sql('SELECT prepared_answers FROM seller_intakes'))
        for field in ['binding_offer','outreach_authorized','property_verified','contact_permission_granted']:
            invalid={**data,field:True};self.inbound_intake(prepared=invalid,fail=True)
        self.inbound_intake(prepared={**data,'classification':'qualified'},fail=True)
        self.inbound_intake(prepared={**data,'transcript':'private'},fail=True)

    def inbound_request(self, *, request='98000000-0000-4000-8000-000000000001', revision=0,
                        kind='request_callback', evidence=None, call='call_test', role='service_role', fail=False,
                        number='+12145550100', agent='agent_test', agent_version=3):
        if evidence is None:
            evidence=({'phone':'(214) 555-0101','preferred_time':'Tomorrow afternoon','purpose':'Discuss property','requested_by_caller':True}
                if kind=='request_callback' else {'reason':'unsupported_language','details':'Needs a human interpreter','requested_by_caller':False})
        result=self.sql(f"SELECT public.record_acquisition_inbound_request('96000000-0000-4000-8000-000000000001',{literal(number)},{literal(agent)},{agent_version},{literal(call)},'{request}',{revision},{literal(kind)},{literal(json.dumps(evidence))}::jsonb)",user=ADMIN,role=role,fail=fail)
        return result if fail else json.loads(result)

    def test_inbound_task_migration_preserves_legacy(self):
        self.assertEqual(self.sql('SELECT jsonb_strip_nulls(to_jsonb(t)) FROM tasks t'),self.legacy_task_before)
        self.sql("UPDATE tasks SET description='Still editable'",user=ADMIN)
        self.assertEqual(self.sql('SELECT description FROM tasks',user=OTHER),'Still editable')
        self.assertEqual(self.sql("SELECT has_table_privilege('anon','tasks','TRUNCATE') OR has_table_privilege('service_role','tasks','TRIGGER')"),'f')

    def test_inbound_request_atomic_replay_revision_and_read_scope(self):
        integration=self.inbound_fixture();self.inbound_accept()
        first=self.inbound_request();self.assertEqual(first['revision'],1);self.assertFalse(first['execution_authorized'])
        self.assertTrue(self.inbound_request()['duplicate'])
        self.inbound_request(evidence={'phone':'2145550102','preferred_time':'Tomorrow','purpose':'Discuss','requested_by_caller':True},fail=True)
        self.inbound_request(request='98000000-0000-4000-8000-000000000002',fail=True)
        second=self.inbound_request(request='98000000-0000-4000-8000-000000000002',revision=1)
        self.assertEqual(second['revision'],2)
        human=self.inbound_request(request='98000000-0000-4000-8000-000000000003',kind='request_human')
        self.assertEqual(human['revision'],1)
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_inbound_request'"),'3')
        self.assertEqual(self.sql('SELECT count(*) FROM tasks',user=ADMIN),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM tasks',user=OTHER),'0')
        query=f"SELECT public.acquisition_inbound_requests('{WORKSPACE}','{integration}','call_test')"
        rows=json.loads(self.sql(query,user=ADMIN));self.assertEqual(len(rows['items']),3)
        self.assertFalse(rows['execution_authorized'])
        self.assertEqual(self.sql(f"SELECT acquisition_phone FROM tasks WHERE id='{first['id']}'"),'+12145550101')
        self.sql(query,user=OTHER,fail=True)
        self.member(CALLER,'acquisition_caller');self.sql(query,user=CALLER,fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM tasks WHERE due_date IS NOT NULL OR completed_at IS NOT NULL OR assigned_to IS NOT NULL OR status<>'acquisition_review_required'"),'0')

    def test_inbound_request_requires_ongoing_call_and_current_route(self):
        self.inbound_fixture();self.inbound_request(fail=True)
        self.inbound_accept();self.inbound_request(role='authenticated',fail=True)
        self.inbound_request(number='+12145550199',fail=True);self.inbound_request(agent_version=4,fail=True)
        first=self.inbound_request()
        self.inbound_accept(self.inbound_data('call_ended'))
        self.assertEqual(self.inbound_request()['id'],first['id'])  # confirmation only
        self.inbound_request(request='98000000-0000-4000-8000-000000000002',revision=1,fail=True)
        self.sql('UPDATE private.acquisition_inbound_routes SET enabled=false')
        self.inbound_request(fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM tasks'),'1')

    def test_inbound_request_strict_evidence_and_immutable_namespace(self):
        self.inbound_fixture();self.inbound_accept()
        for evidence in [{},{'phone':'2145550101','preferred_time':'Tomorrow','purpose':'Discuss','requested_by_caller':'true'},
            {'phone':'2145550101','preferred_time':'Tomorrow','purpose':'Discuss','requested_by_caller':True,'approved':True},
            {'phone':None,'preferred_time':'Tomorrow','purpose':'Discuss','requested_by_caller':True}]:
            self.inbound_request(evidence=evidence,fail=True)
        self.inbound_request(kind='request_human',evidence={'reason':'caller_requested','details':'Help','requested_by_caller':False},fail=True)
        first=self.inbound_request(evidence={'phone':'unknown number','preferred_time':'Unknown','purpose':'Discuss','requested_by_caller':True})
        self.assertEqual(self.sql('SELECT count(*) FROM tasks WHERE acquisition_phone IS NULL'),'1')
        self.sql(f"UPDATE tasks SET status='completed' WHERE id='{first['id']}'",fail=True)
        self.sql(f"DELETE FROM tasks WHERE id='{first['id']}'",fail=True)
        self.sql(f"UPDATE tasks SET workspace_id=NULL WHERE id='{first['id']}'",user=ADMIN,role='service_role',fail=True)
        columns='title,priority,status,type,workspace_id,acquisition_integration_id,acquisition_call_id,acquisition_request_id,acquisition_revision,acquisition_request_kind,acquisition_evidence,acquisition_request_hash,acquisition_phone'
        error=self.sql(f'INSERT INTO tasks({columns}) SELECT {columns} FROM tasks',user=ADMIN,role='service_role',fail=True)
        self.assertIn('Use controlled inbound task receipt',error)
        self.assertEqual(self.sql('SELECT count(*) FROM tasks'),'1')

    def test_inbound_request_read_limits_and_membership_revocation(self):
        integration=self.inbound_fixture();self.inbound_accept();self.inbound_request();self.member()
        query=f"SELECT public.acquisition_inbound_requests('{WORKSPACE}','{integration}','call_test')"
        self.assertEqual(len(json.loads(self.sql(query,user=OPERATOR))['items']),1)
        other=f"SELECT public.acquisition_inbound_requests('{WORKSPACE}','99000000-0000-4000-8000-000000000001','call_test')"
        self.assertEqual(json.loads(self.sql(other,user=ADMIN))['items'],[])
        for bound in [0,51]:
            self.sql(f"SELECT public.acquisition_inbound_requests('{WORKSPACE}','{integration}','call_test',NULL,{bound})",user=ADMIN,fail=True)
        self.member(status='revoked');self.sql(query,user=OPERATOR,fail=True)
        self.sql('UPDATE private.acquisition_integrations SET enabled=false')
        self.inbound_request(fail=True)
        # Historical evidence remains readable after provider disablement.
        self.assertEqual(len(json.loads(self.sql(query,user=ADMIN))['items']),1)

    def test_inbound_request_concurrent_replay(self):
        self.inbound_fixture();self.inbound_accept()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.inbound_request(),range(3)))
        self.assertEqual(len({row['id'] for row in results}),1)
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_inbound_request'"),'1')

    def test_inspected_tasks_fixture_defaults_and_legacy_compatibility(self):
        identity=self.sql("INSERT INTO tasks(title,description) VALUES('Legacy task','Preserved text') RETURNING id",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT priority||':'||status FROM tasks WHERE id='{identity}'",user=OTHER),'medium:pending')
        self.sql(f"UPDATE tasks SET description='Still editable' WHERE id='{identity}'",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT description FROM tasks WHERE id='{identity}'",user=OTHER),'Still editable')
        self.sql("INSERT INTO tasks(description) VALUES('Missing title')",user=ADMIN,fail=True)
        self.sql("INSERT INTO tasks(title,lead_id) VALUES('Invalid parent','99999999-0000-4000-8000-000000000001')",user=ADMIN,fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND tablename='tasks'"),'5')

    def test_inspected_tasks_fixture_bound_lead_isolation(self):
        self.bind()
        identity=self.sql(f"INSERT INTO tasks(title,lead_id) VALUES('Bound task','{LEAD}') RETURNING id")
        self.assertEqual(self.sql(f"SELECT count(*) FROM tasks WHERE id='{identity}'",user=ADMIN),'1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM tasks WHERE id='{identity}'",user=OTHER),'0')
        self.member(CALLER, 'acquisition_caller')
        self.assertEqual(self.sql(f"SELECT count(*) FROM tasks WHERE id='{identity}'",user=CALLER),'0')
        self.sql(f"INSERT INTO tasks(title,lead_id) VALUES('Direct prohibited','{LEAD}')",user=ADMIN,fail=True)
        self.assertEqual(self.sql(f"WITH changed AS (UPDATE tasks SET title='Changed' WHERE id='{identity}' RETURNING id) SELECT count(*) FROM changed",user=ADMIN),'0')
        self.assertEqual(self.sql(f"WITH removed AS (DELETE FROM tasks WHERE id='{identity}' RETURNING id) SELECT count(*) FROM removed",user=ADMIN),'0')

    def test_inspected_tasks_fixture_call_only_gaps_and_dependency_edges(self):
        # Baseline evidence: an unbound task is visible to approved legacy users.
        # The forthcoming scoped extension must close this path for call requests.
        self.sql("INSERT INTO tasks(title,type) VALUES('Synthetic inbound request','acquisition_callback_review')")
        self.assertEqual(self.sql('SELECT count(*) FROM tasks',user=OTHER),'1')
        self.assertEqual(self.sql("SELECT has_table_privilege('authenticated','tasks','TRUNCATE') AND has_table_privilege('service_role','tasks','TRIGGER')"),'f')
        catalog=json.loads((ROOT/'docs/acquisition-automation/evidence/2026-10-26-inbound-task-catalog.json').read_text())
        self.assertEqual(len(catalog['incoming_fks']),7)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_constraint WHERE conrelid='tasks'::regclass AND contype='f'"),'5')

    def test_inbound_migration_preserves_populated_legacy_events(self):
        self.assertEqual(self.sql("SELECT jsonb_strip_nulls(to_jsonb(c)) FROM call_events c"),self.legacy_call_before)
        self.sql("UPDATE call_events SET notes='legacy still writable'",user=ADMIN)
        self.assertEqual(self.sql('SELECT notes FROM call_events',user=OTHER),'legacy still writable')
        self.assertEqual(self.sql("SELECT has_table_privilege('anon','call_events','TRUNCATE') OR has_table_privilege('authenticated','call_events','TRIGGER')"),'f')

    def inbound_fixture(self, enabled=True):
        integration='96000000-0000-4000-8000-000000000001'
        self.sql(f"INSERT INTO private.acquisition_integrations(id,workspace_id,provider,account_id,enabled,approval_ref) VALUES('{integration}','{WORKSPACE}','retell','synthetic-retell-account',true,'fixture approval'); "
                 f"INSERT INTO private.acquisition_inbound_routes(integration_id,workspace_id,agent_id,agent_version,acquisition_number,enabled,privacy_approval_ref,disclosure_approval_ref,phase_one_acceptance_ref) "
                 f"VALUES('{integration}','{WORKSPACE}','agent_test',3,'+12145550100',{str(enabled).lower()},'synthetic privacy approval','synthetic disclosure approval','synthetic phase one acceptance');")
        return integration

    def inbound_data(self, event='call_started', **patch):
        import importlib.util
        spec=importlib.util.spec_from_file_location('inbound_projection',ROOT/'tools/acquisition_inbound_events.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        call=dict(call_id='call_test',agent_id='agent_test',agent_version=3,direction='inbound',call_type='phone_call',to_number='+12145550100',call_status='ongoing' if event=='call_started' else 'ended',start_timestamp=1000)
        if event!='call_started':call['end_timestamp']=5000
        call.update(patch)
        return module.project_inbound_event({'event':event,'call':call},workspace_id=WORKSPACE,integration_id='96000000-0000-4000-8000-000000000001',agent_id='agent_test',agent_version=3,acquisition_number='+12145550100')

    def inbound_accept(self,data=None,role='service_role',number='+12145550100',fail=False):
        result=self.sql(f"SELECT public.accept_acquisition_inbound_event('96000000-0000-4000-8000-000000000001',{literal(number)},{literal(json.dumps(data or self.inbound_data()))}::jsonb)",user=ADMIN,role=role,fail=fail)
        return result if fail else json.loads(result)

    def test_inbound_ledger_idempotency_privacy_and_immutability(self):
        self.inbound_fixture(); first=self.inbound_accept(); second=self.inbound_accept()
        self.assertEqual(first['id'],second['id']); self.assertTrue(second['duplicate'])
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_inbound_event'"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM call_events',user=ADMIN),'0')
        rows=json.loads(self.sql(f"SELECT public.acquisition_inbound_events('{WORKSPACE}','96000000-0000-4000-8000-000000000001','call_test')",user=ADMIN))
        self.assertEqual(len(rows['items']),1)
        self.assertEqual(json.loads(self.sql(f"SELECT public.acquisition_inbound_events('{WORKSPACE}','96000000-0000-4000-8000-000000000002','call_test')",user=ADMIN))['items'],[])
        self.assertFalse(rows['execution_authorized'])
        self.sql(f"SELECT public.acquisition_inbound_events('{WORKSPACE}','96000000-0000-4000-8000-000000000001','call_test')",user=OTHER,fail=True)
        self.member(target=CALLER,role='acquisition_caller')
        self.sql(f"SELECT public.acquisition_inbound_events('{WORKSPACE}','96000000-0000-4000-8000-000000000001','call_test')",user=CALLER,fail=True)
        for sql in ["UPDATE call_events SET notes='changed'",'DELETE FROM call_events']:
            self.assertIn('immutable',self.sql(sql,user=ADMIN,role='service_role',fail=True))
        direct="INSERT INTO call_events(dialer,disposition,raw_payload,workspace_id,acquisition_integration_id,acquisition_call_id,acquisition_event_type,acquisition_projection) SELECT dialer,disposition,raw_payload,workspace_id,acquisition_integration_id,'call_other',acquisition_event_type,acquisition_projection FROM call_events"
        self.assertIn('controlled inbound receipt',self.sql(direct,user=ADMIN,role='service_role',fail=True))
        self.assertEqual(self.sql("SELECT count(*) FROM call_events WHERE phone_number IS NOT NULL OR recording_url IS NOT NULL OR notes IS NOT NULL OR raw_payload<>'{}'"),'0')

    def test_inbound_ledger_requires_enabled_trusted_route_and_strict_projection(self):
        self.inbound_fixture(enabled=False); self.inbound_accept(fail=True)
        self.sql('UPDATE private.acquisition_inbound_routes SET enabled=true')
        self.inbound_accept(number='+12145550999',fail=True)
        self.inbound_accept(role='authenticated',fail=True)
        for patch in [{'workspace_id':WORKSPACE_B},{'agent_id':'other'},{'transcript':'private'},{'projection_hash':'bad'},{'sensitive_content_present':'false'}]:
            self.inbound_accept(self.inbound_data()|patch,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM call_events'),'0')
        self.inbound_accept()
        self.sql('UPDATE private.acquisition_inbound_routes SET enabled=false')
        self.inbound_accept(fail=True)
        self.sql('UPDATE private.acquisition_inbound_routes SET enabled=true; UPDATE private.acquisition_integrations SET enabled=false')
        self.inbound_accept(fail=True)

    def test_inbound_ledger_concurrent_replay_and_changed_retry(self):
        self.inbound_fixture()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.inbound_accept(),range(3)))
        self.assertEqual(len({row['id'] for row in results}),1)
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        self.inbound_accept(self.inbound_data(start_timestamp=2000),fail=True)
        self.inbound_accept(self.inbound_data('call_analyzed'))
        self.inbound_accept(self.inbound_data('call_ended'))
        self.assertEqual(self.sql('SELECT count(*) FROM call_events'),'3')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_inbound_event'"),'3')

    def cost_record(self, review, data=None, request='93000000-0000-4000-8000-000000000001', user=ADMIN, fail=False, **kwargs):
        payload={'date':'2026-10-24','amount_minor':12550,'coverage':'complete','currency':'USD','reporting_timezone':'America/Chicago',
                 'observed_at':'2026-10-25T06:00:00Z','external_campaign_id':'987654','ad_account_id':'123456',
                 'evidence_ref':'private-reviewed-cost-artifact','evidence_hash':'a'*64,'expected_revision':0}
        payload.update(data or {})
        result=self.sql(f"SELECT public.record_acquisition_cost('{request}','{WORKSPACE}','{review}',{literal(json.dumps(payload))}::jsonb)",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def cost_fixture(self):
        self.bind(); self.member(); self.link_campaign=self.campaign_draft()['id']
        intake=self.campaign_link_fixture()
        review=self.campaign_link_review(intake,self.campaign_link_state(intake))['review_id']
        return intake,review

    def test_cost_evidence_idempotent_revision_and_legacy_namespace(self):
        intake,review=self.cost_fixture()
        saved=self.cost_record(review); self.assertEqual(saved['revision'],1)
        self.assertTrue(self.cost_record(review)['duplicate'])
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_cost'"),'1')
        self.cost_record(review,{'amount_minor':9},fail=True)
        self.cost_record(review,request='93000000-0000-4000-8000-000000000002',fail=True)
        withdrawn=self.cost_record(review,{'expected_revision':1,'coverage':'withdrawn','amount_minor':None},request='93000000-0000-4000-8000-000000000002')
        self.assertEqual(withdrawn['revision'],2)
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=ADMIN),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance WHERE spend IS NULL AND leads IS NULL AND cpl IS NULL'),'2')
        self.sql("INSERT INTO fb_campaign_performance(date,spend,leads) VALUES('2026-10-24',100,4)",user=ADMIN)
        self.assertEqual(self.sql('SELECT cpl::text FROM fb_campaign_performance',user=ADMIN),'25.00')
        self.campaign_link_review(intake,self.campaign_link_state(intake),p_id='cf000000-0000-4000-8000-000000000002',p_action='revoke',p_campaign=None,p_ad_account=None)
        self.assertTrue(self.cost_record(review)['duplicate'])
        self.cost_record(review,{'expected_revision':2},request='93000000-0000-4000-8000-000000000003',fail=True)

    def test_cost_evidence_roles_immutability_units_and_account(self):
        intake,review=self.cost_fixture()
        for patch in ({'currency':'CAD'},{'reporting_timezone':'bad/zone'},{'amount_minor':True},{'amount_minor':1.5},
                      {'amount_minor':-1},{'amount_minor':10**15},{'observed_at':'2026-10-24T06:00:00Z'},
                      {'observed_at':'2026-10-25'},{'observed_at':'2999-01-01T00:00:00Z'},
                      {'ad_account_id':'998'},{'external_campaign_id':'301'},{'evidence_hash':'bad'},
                      {'coverage':'withdrawn'},{'coverage':'unknown'},{'expected_revision':True}):
            self.cost_record(review,patch,fail=True)
        self.cost_record(review,user=OTHER,fail=True)
        self.member(target=OPERATOR,role='operator'); self.cost_record(review,user=OPERATOR,fail=True)
        self.cost_record(review,aal='aal1',fail=True); self.cost_record(review,session=False,fail=True)
        saved=self.cost_record(review)
        self.cost_record(review,{'date':'2026-10-23','reporting_timezone':'UTC'},request='93000000-0000-4000-8000-000000000002',fail=True)
        for role in ('authenticated','service_role'):
            self.sql(f"UPDATE fb_campaign_performance SET acquisition_coverage='partial' WHERE id='{saved['id']}'",user=ADMIN,role=role,fail=(role=='service_role'))
            self.sql('TRUNCATE fb_campaign_performance',user=ADMIN,role=role,fail=True)
        self.sql(f"DELETE FROM fb_campaign_performance WHERE id='{saved['id']}'",fail=True)
        self.assertEqual(self.sql(f"SELECT acquisition_coverage FROM fb_campaign_performance WHERE id='{saved['id']}'"),'complete')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=OTHER),'0')
        self.cost_record(review,role='service_role',fail=True)
        columns='date,campaign_id,ad_set_id,spend,leads,contact_rate,appt_rate,frequency,workspace_id,acquisition_campaign_id,acquisition_link_review_id,acquisition_amount_minor,acquisition_coverage,acquisition_timezone,acquisition_observed_at,acquisition_data,acquisition_actor_id,acquisition_recorded_at'
        rejected=self.sql(f"INSERT INTO fb_campaign_performance(id,acquisition_revision,{columns}) SELECT '93000000-0000-4000-8000-000000000099',99,{columns} FROM fb_campaign_performance WHERE workspace_id IS NOT NULL",user=ADMIN,role='service_role',fail=True)
        self.assertIn('Use reviewed cost function',rejected)


    def cost_evidence(self, user=ADMIN, fail=False, campaign=None, workspace=WORKSPACE, cutoff='statement_timestamp()', **kwargs):
        campaign=campaign or self.link_campaign
        result=self.sql(f"SELECT public.acquisition_cost_evidence('{workspace}','{campaign}','2026-10-24','2026-10-24',{cutoff})",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_cost_evidence_read_latest_scope_cutoff_and_revoked_attribution(self):
        intake,review=self.cost_fixture()
        empty=self.cost_evidence(); self.assertEqual(empty['items'],[]); self.assertIsNone(empty['reporting_timezone'])
        self.cost_record(review)
        value=self.cost_evidence(); self.assertEqual(value['items'][0]['amount_minor'],12550)
        self.assertTrue(value['items'][0]['attribution_current']); self.assertFalse(value['truncated'])
        self.assertNotIn('private-reviewed-cost-artifact',json.dumps(value))
        cutoff=literal(self.sql('SELECT clock_timestamp()'))+'::timestamptz'
        self.cost_record(review,{'coverage':'partial','expected_revision':1,'amount_minor':500},request='93000000-0000-4000-8000-000000000002')
        self.assertEqual(self.cost_evidence()['items'][0]['revision'],2)
        self.assertEqual(self.cost_evidence(cutoff=cutoff)['items'][0]['revision'],1)
        self.cost_evidence(user=OTHER,fail=True); self.cost_evidence(workspace=WORKSPACE_B,fail=True)
        self.cost_evidence(campaign=LEAD,fail=True); self.cost_evidence(role='service_role',fail=True)
        self.cost_evidence(cutoff="'2999-01-01T00:00:00Z'",fail=True)
        self.member(target=OPERATOR,role='operator'); self.assertEqual(len(self.cost_evidence(user=OPERATOR)['items']),1)
        self.member(target=CALLER,role='acquisition_caller'); self.cost_evidence(user=CALLER,fail=True)
        self.campaign_link_review(intake,self.campaign_link_state(intake),p_id='cf000000-0000-4000-8000-000000000002',p_action='revoke',p_campaign=None,p_ad_account=None)
        historical=self.cost_evidence()['items'][0]; self.assertFalse(historical['attribution_current']); self.assertEqual(historical['revision'],2)

    def test_cost_evidence_concurrent_retries_create_one_revision(self):
        intake,review=self.cost_fixture()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.cost_record(review),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        self.assertEqual(self.sql("SELECT count(*) FROM fb_campaign_performance WHERE workspace_id IS NOT NULL"),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_cost'"),'1')

    def test_cost_migration_preserves_populated_legacy_metrics(self):
        after=self.sql("SELECT jsonb_build_object('id',id,'date',date,'spend',spend,'leads',leads,'cpl',cpl)::text FROM fb_campaign_performance")
        self.assertEqual(after,self.legacy_cost_before)
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance WHERE workspace_id IS NULL'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=ADMIN),'1')

    def test_cost_fixture_restores_generated_metrics_and_parent_edges(self):
        campaign='92000000-0000-4000-8000-000000000001'
        adset='92000000-0000-4000-8000-000000000002'
        self.sql(f"INSERT INTO fb_campaigns(id,name) VALUES('{campaign}','Synthetic legacy performance'); "
                 f"INSERT INTO fb_ad_sets(id,campaign_id) VALUES('{adset}','{campaign}'); "
                 f"INSERT INTO fb_campaign_performance(campaign_id,ad_set_id,date,spend,leads) VALUES('{campaign}','{adset}','2026-10-24',100,4)")
        self.assertEqual(self.sql('SELECT cpl::text FROM fb_campaign_performance'),'25.00')
        self.sql('UPDATE fb_campaign_performance SET cpl=1',fail=True)
        self.sql(f"INSERT INTO fb_campaign_performance(campaign_id,ad_set_id,date) VALUES('{campaign}','{adset}','2026-10-24')",fail=True)
        self.sql(f"DELETE FROM fb_ad_sets WHERE id='{adset}'",fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_indexes WHERE tablename IN ('fb_campaigns','fb_ad_sets','fb_campaign_performance') AND indexname NOT LIKE 'acquisition_%'"),'6')
        self.sql('UPDATE fb_campaign_performance SET ad_set_id=NULL')
        self.sql(f"DELETE FROM fb_campaigns WHERE id='{campaign}'")
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance'),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_ad_sets'),'0')

    def test_cost_fixture_exposes_legacy_access_and_zero_defaults(self):
        self.sql("INSERT INTO fb_campaign_performance(date) VALUES('2026-10-24')")
        self.assertEqual(self.sql('SELECT spend::text FROM fb_campaign_performance'),'0.00')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance WHERE cpl IS NULL'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=ADMIN),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=OTHER),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=OTHER,role='anon'),'0')
        self.member(target=OPERATOR,role='operator')
        self.assertEqual(self.sql('SELECT count(*) FROM fb_campaign_performance',user=OPERATOR),'0')
        self.sql('UPDATE fb_campaign_performance SET spend=10',user=ADMIN)
        self.assertEqual(self.sql('SELECT spend::text FROM fb_campaign_performance'),'10.00')
        # The cost extension removes the captured baseline TRUNCATE grant.
        self.assertEqual(self.sql("SELECT has_table_privilege('anon','fb_campaign_performance','TRUNCATE')::text"),'false')

    def test_campaign_fixture_preserves_generated_cost_and_parent_constraints(self):
        campaign='90000000-0000-4000-8000-000000000001'
        creative='90000000-0000-4000-8000-000000000002'
        self.sql(f"INSERT INTO ad_campaigns(id,name,total_spend,leads_count) VALUES('{campaign}','Legacy campaign',100,4); "
                 f"INSERT INTO ad_creatives(id,campaign_id,name) VALUES('{creative}','{campaign}','Legacy creative');")
        self.assertEqual(self.sql(f"SELECT cpl::text FROM ad_campaigns WHERE id='{campaign}'"),'25.00')
        self.sql(f"UPDATE ad_campaigns SET cpl=0 WHERE id='{campaign}'",fail=True)
        self.sql(f"UPDATE leads SET ad_campaign_id='{campaign}',ad_creative_id='{creative}' WHERE id='{LEAD}'")
        self.sql(f"DELETE FROM ad_campaigns WHERE id='{campaign}'",fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_constraint WHERE conname IN ('leads_ad_campaign_id_fkey','leads_ad_creative_id_fkey','leads_form_submission_id_fkey','lead_form_submissions_form_id_fkey')"),'4')
        self.sql(f"UPDATE leads SET ad_campaign_id=NULL,ad_creative_id=NULL WHERE id='{LEAD}'; DELETE FROM ad_campaigns WHERE id='{campaign}'")
        self.assertEqual(self.sql('SELECT count(*) FROM ad_creatives'),'0')

    def test_campaign_fixture_exposes_baseline_access_for_isolation_regressions(self):
        self.sql("INSERT INTO ad_campaigns(name) VALUES('Legacy shared campaign'); "
                 "INSERT INTO lead_form_configs(name,slug,active) VALUES('Public fixture','public-fixture',true),('Hidden fixture','hidden-fixture',false)")
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns',user=ADMIN),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns',user=OTHER),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM lead_form_configs',user=ADMIN,role='anon'),'1')
        self.assertEqual(self.sql("SELECT has_table_privilege('anon','ad_campaigns','TRUNCATE')::text"),'false')
        self.member(role='operator',target=OPERATOR)
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns',user=OPERATOR),'0')

    def campaign_draft(self, identity='91000000-0000-4000-8000-000000000001',actor=ADMIN,workspace=WORKSPACE,fail=False):
        value=self.sql(f"SELECT public.create_acquisition_campaign('{identity}','{workspace}','Draft campaign','facebook',50000,'USD')",user=actor,fail=fail)
        return value if fail else json.loads(value)

    def property_sources(self, lead=LEAD, workspace=WORKSPACE, user=ADMIN, after=None, limit=20, fail=False, **kwargs):
        cursor='NULL' if after is None else literal(after)
        result=self.sql(f"SELECT public.acquisition_property_source_touches('{workspace}','{lead}',{cursor},{limit})",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_property_sources_require_review_and_preserve_separate_inquiries(self):
        self.bind(); self.member(); self.link_campaign=self.campaign_draft()['id']
        first=self.campaign_link_fixture(); second=self.campaign_link_fixture(account='second-page',external='123456')
        self.assertEqual(self.property_sources()['items'],[])
        self.identity_review(first,self.identity_state(first))
        self.identity_review(second,self.identity_state(second),request='71000000-0000-4000-8000-000000000002',action='repeat_inquiry')
        report=self.property_sources(); self.assertEqual(len(report['items']),2)
        self.assertEqual({row['association'] for row in report['items']},{'reviewed_property','reviewed_repeat_inquiry'})
        self.assertEqual(len({row['original_lead_id'] for row in report['items']}),2)
        self.assertTrue(all(row['original_lead_id']!=LEAD and row['current_campaign_id'] is None for row in report['items']))
        self.assertFalse(report['totals_available']); self.assertFalse(report['ownership_verified']); self.assertFalse(report['execution_authorized'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_lead_sources'),'2')
        self.assertEqual(self.sql("SELECT count(*) FROM workspace_leads WHERE binding_integration_id IS NOT NULL AND property_id IS NULL"),'2')
        self.assertNotIn('phone',json.dumps(report)); self.assertNotIn('target_snapshot',json.dumps(report))

    def test_property_sources_exclude_stale_identity_and_allow_empty_continuation(self):
        self.bind(); self.member()
        first=self.campaign_link_fixture(); second=self.campaign_link_fixture(account='second-page',external='123456')
        self.identity_review(first,self.identity_state(first))
        self.identity_review(second,self.identity_state(second),request='71000000-0000-4000-8000-000000000002')
        ordered=sorted([first,second]); stale=ordered[0]
        self.identity_review(stale,self.identity_state(stale),request='71000000-0000-4000-8000-000000000003',action='revoke')
        page=self.property_sources(limit=1); self.assertEqual(page['items'],[]); self.assertEqual(page['excluded_count'],1); self.assertEqual(page['next_after'],stale)
        next_page=self.property_sources(after=page['next_after'],limit=1)
        self.assertEqual(next_page['items'][0]['source_id'],ordered[1]); self.assertIsNone(next_page['next_after'])
        self.sql(f"UPDATE wholesale_ingest.properties SET unit='new unit' WHERE id='{PROPERTY}'")
        self.assertEqual(self.property_sources()['items'],[])

    def test_property_sources_current_and_historical_campaign_capture(self):
        self.bind(); self.member(); self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture()
        self.identity_review(intake,self.identity_state(intake))
        linked=self.campaign_link_review(intake,self.campaign_link_state(intake))
        before=self.property_sources()['items'][0]; self.assertEqual(before['attribution_status'],'current_review_not_captured'); self.assertIsNone(before['current_campaign_id'])
        self.source_capture(intake,linked['review_id'])
        captured=self.property_sources()['items'][0]; self.assertTrue(captured['attribution_current']); self.assertEqual(captured['current_campaign_id'],self.link_campaign)
        self.campaign_link_review(intake,self.campaign_link_state(intake),p_id='cf000000-0000-4000-8000-000000000002',p_action='revoke',p_campaign=None,p_ad_account=None)
        historical=self.property_sources()['items'][0]; self.assertFalse(historical['attribution_current']); self.assertIsNone(historical['current_campaign_id'])
        self.assertEqual(historical['captured_attribution']['id'],captured['captured_attribution']['id'])

    def test_property_sources_role_scope_limits_and_missing_market_metadata(self):
        self.bind(); self.member(); saved=self.candidate_fixture_without_config_for_sources()
        self.identity_review(saved,self.identity_state(saved))
        report=self.property_sources(); self.assertEqual(report['items'][0]['attribution_status'],'campaign_evidence_unavailable')
        self.property_sources(user=OTHER,fail=True); self.property_sources(workspace=WORKSPACE_B,user=OTHER,fail=True)
        self.property_sources(lead=LEAD_B,fail=True); self.property_sources(limit=0,fail=True); self.property_sources(limit=51,fail=True)
        self.property_sources(session=False,fail=True); self.property_sources(role='service_role',fail=True)
        self.member(target=OPERATOR,role='operator'); self.assertEqual(len(self.property_sources(user=OPERATOR)['items']),1)
        self.member(target=CALLER,role='acquisition_caller'); self.property_sources(user=CALLER,fail=True)

    def candidate_fixture_without_config_for_sources(self):
        self.inbox_config(); self.inbox_accept()
        return self.complete_intake(self.inbox_claim()[0])['intake_id']

    def source_capture(self, intake, review, user=ADMIN, fail=False, identity='cd000000-0000-4000-8000-000000000001', workspace=WORKSPACE):
        result=self.sql(f"SELECT public.capture_acquisition_source_campaign('{identity}','{workspace}','{intake}','{review}')",user=user,fail=fail)
        return result if fail else json.loads(result)

    def test_sources_record_original_evidence_atomic_and_scoped(self):
        self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture()
        source=json.loads(self.sql(f"SELECT to_jsonb(s) FROM acquisition_lead_sources s WHERE id='{intake}'",user=ADMIN))
        self.assertEqual(source['external_campaign_id'],'987654'); self.assertIsNone(source['utm_data']); self.assertIsNone(source['ad_id'])
        self.assertNotIn('phone',json.dumps(source)); self.assertNotIn('answers',source)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_lead_sources',user=OTHER),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_lead_source'"),'1')
        for role in ('authenticated','service_role'):
            for table in ('acquisition_lead_sources','acquisition_source_campaign_reviews'):
                for query in (f'DELETE FROM {table}',f'TRUNCATE {table}',f'INSERT INTO {table} SELECT * FROM {table}'):
                    self.sql(query,user=ADMIN,role=role,fail=True)
        self.sql(f"UPDATE acquisition_lead_sources SET external_campaign_id='999' WHERE id='{intake}'",fail=True)

    def test_source_projection_failure_rolls_back_intake_and_retries_once(self):
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        self.sql("CREATE FUNCTION private.fixture_source_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Synthetic source failure'; END $$; "
                 "CREATE TRIGGER fixture_source_failure BEFORE INSERT ON acquisition_lead_sources FOR EACH ROW EXECUTE FUNCTION private.fixture_source_failure();")
        self.complete_intake(claim,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes'),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='facebook_acquisition'"),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_lead_sources'),'0')
        self.assertEqual(self.sql('SELECT state FROM private.acquisition_inbox_processing'),'leased')
        self.sql('DROP TRIGGER fixture_source_failure ON acquisition_lead_sources')
        self.complete_intake(claim); self.assertTrue(self.complete_intake(claim)['duplicate'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_lead_sources'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_lead_source'"),'1')

    def test_source_campaign_capture_concurrent_and_revocation_preserves_history(self):
        self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture(); state=self.campaign_link_state(intake)
        reviewed=self.campaign_link_review(intake,state)
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda _:self.source_capture(intake,reviewed['review_id']),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        self.assertTrue(all(not row['execution_authorized'] for row in results))
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_source_campaign'"),'1')
        self.source_capture(intake,reviewed['review_id'],identity='cd000000-0000-4000-8000-000000000002',fail=True)
        fresh=self.campaign_link_state(intake)
        self.campaign_link_review(intake,fresh,p_id='cf000000-0000-4000-8000-000000000002',p_action='revoke',p_campaign=None,p_ad_account=None)
        self.assertTrue(self.source_capture(intake,reviewed['review_id'])['duplicate'])
        self.source_capture(intake,reviewed['review_id'],identity='cd000000-0000-4000-8000-000000000003',fail=True)
        corrected=self.campaign_link_review(intake,self.campaign_link_state(intake),p_id='cf000000-0000-4000-8000-000000000003')
        self.source_capture(intake,corrected['review_id'],identity='cd000000-0000-4000-8000-000000000004')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_source_campaign_reviews'),'2')
        self.sql('DELETE FROM acquisition_source_campaign_reviews',fail=True)

    def test_source_campaign_capture_requires_current_matching_review_and_role(self):
        self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture(); reviewed=self.campaign_link_review(intake,self.campaign_link_state(intake))
        self.source_capture(intake,reviewed['review_id'],user=OTHER,workspace=WORKSPACE_B,fail=True)
        other=self.campaign_link_fixture(external='123456',account='second-page')
        self.source_capture(other,reviewed['review_id'],fail=True)
        self.sql('UPDATE private.acquisition_integrations SET enabled=false')
        self.source_capture(intake,reviewed['review_id'],fail=True)
        self.sql('UPDATE private.acquisition_integrations SET enabled=true')
        self.member(target=OPERATOR,role='operator')
        result=self.source_capture(intake,reviewed['review_id'],user=OPERATOR)
        self.assertEqual(result['campaign_id'],self.link_campaign)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_source_campaign_reviews',user=OTHER),'0')

    def test_source_migration_backfills_without_changing_intakes(self):
        intake=self.campaign_link_fixture()
        before=self.sql('SELECT jsonb_agg(to_jsonb(i)) FROM seller_intakes i')
        self.sql((ROOT/'frontend/supabase/migrations/20261026221434_acquisition_lead_sources.sql').read_text())
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(i)) FROM seller_intakes i'))
        self.assertEqual(self.sql('SELECT id FROM acquisition_lead_sources'),intake)
        self.sql(f"SELECT private.record_acquisition_lead_source('{intake}')")
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_lead_sources'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_lead_source'"),'1')

    def campaign_link_fixture(self, external='987654', account='fixture-page', workspace=WORKSPACE):
        self.inbox_config(account=account,workspace=workspace); self.inbox_accept(account=account)
        prepared=self.prepared_intake()
        prepared['provider_evidence']['campaign_id']=external
        prepared['provider_evidence_hash']=hashlib.sha256(json.dumps(prepared['provider_evidence'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        integration=self.sql(f"SELECT id FROM private.acquisition_integrations WHERE account_id={literal(account)}")
        claim=json.loads(self.sql(f"SELECT public.claim_acquisition_events('{integration}',1,120)",user=ADMIN,role='service_role'))[0]
        intake=self.complete_intake(claim,prepared)
        return intake['intake_id']

    def campaign_link_state(self, intake, user=ADMIN, workspace=WORKSPACE, fail=False):
        result=self.sql(f"SELECT public.acquisition_campaign_link_state('{workspace}','{intake}')",user=user,fail=fail)
        return result if fail else json.loads(result)

    def campaign_link_review(self, intake, state, user=ADMIN, fail=False, aal='aal2', **overrides):
        args=dict(p_id='cf000000-0000-4000-8000-000000000001',p_workspace=WORKSPACE,p_intake=intake,
                  p_expected_sequence=state['sequence'],p_preparation_hash=state['preparation_hash'],p_action='link',
                  p_campaign=self.link_campaign,p_ad_account='123456',p_evidence_ref='Synthetic account ownership evidence',
                  p_note='Reviewed Page and ad account ownership with campaign identity.')
        args.update(overrides)
        sqlargs=','.join(k+'=>'+('NULL' if v is None else str(v) if isinstance(v,int) else literal(v)) for k,v in args.items())
        result=self.sql('SELECT public.review_acquisition_campaign_link('+sqlargs+')',user=user,fail=fail,aal=aal)
        return result if fail else json.loads(result)

    def test_campaign_link_concurrent_review_scope_and_legacy_unchanged(self):
        self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture(); state=self.campaign_link_state(intake)
        self.assertFalse(state['link_current']); self.assertEqual(state['page_id'],'fixture-page')
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda _:self.campaign_link_review(intake,state),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        current=self.campaign_link_state(intake); self.assertTrue(current['link_current']); self.assertEqual(current['internal_campaign_id'],self.link_campaign)
        self.assertFalse(current['execution_authorized'])
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_campaign_link'"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_campaign_links',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM leads WHERE ad_campaign_id IS NOT NULL'),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns WHERE external_campaign_id IS NOT NULL'),'0')
        self.campaign_link_state(intake,user=OTHER,workspace=WORKSPACE_B,fail=True)
        for role in ('authenticated','service_role'):
            for query in ('DELETE FROM acquisition_campaign_links','TRUNCATE acquisition_campaign_links',"UPDATE acquisition_campaign_links SET ad_account_id='9'",'INSERT INTO acquisition_campaign_links SELECT * FROM acquisition_campaign_links'):
                self.sql(query,user=ADMIN,role=role,fail=True)
        self.sql("UPDATE acquisition_campaign_links SET ad_account_id='9'",fail=True)

    def test_campaign_link_revocation_correction_and_stale_rejection(self):
        self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture(); state=self.campaign_link_state(intake)
        self.campaign_link_review(intake,state,p_preparation_hash='f'*64,fail=True)
        self.campaign_link_review(intake,state); current=self.campaign_link_state(intake)
        self.campaign_link_review(intake,current,p_id='cf000000-0000-4000-8000-000000000002',fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_integrations SET enabled=false')
        self.assertFalse(self.campaign_link_state(intake)['link_current'])
        revoke=dict(p_id='cf000000-0000-4000-8000-000000000002',p_action='revoke',p_campaign=None,p_ad_account=None)
        self.campaign_link_review(intake,current,**revoke)
        self.assertTrue(self.campaign_link_review(intake,current,**revoke)['duplicate'])
        self.activate(); self.sql('UPDATE private.acquisition_integrations SET enabled=true')
        fresh=self.campaign_link_state(intake); self.assertFalse(fresh['link_current'])
        self.campaign_link_review(intake,fresh,p_id='cf000000-0000-4000-8000-000000000003',p_ad_account='654321')
        self.assertEqual(self.campaign_link_state(intake)['latest_review']['ad_account_id'],'654321')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_campaign_links'),'3')

    def test_campaign_link_rejects_missing_evidence_and_cross_workspace_target(self):
        self.link_campaign=self.campaign_draft()['id']
        missing=self.campaign_link_fixture(external=None)
        self.campaign_link_state(missing,fail=True)
        intake=self.campaign_link_fixture(account='valid-page'); state=self.campaign_link_state(intake)
        other=self.campaign_draft(identity='cf000000-0000-4000-8000-000000000099',actor=OTHER,workspace=WORKSPACE_B)['id']
        self.campaign_link_review(intake,state,p_campaign=other,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_campaign_links'),'0')

    def test_campaign_link_mfa_roles_authority_and_account_conflicts(self):
        self.link_campaign=self.campaign_draft()['id']; intake=self.campaign_link_fixture(); state=self.campaign_link_state(intake)
        self.member(target=OPERATOR,role='operator')
        self.campaign_link_review(intake,state,user=OPERATOR,fail=True)
        self.campaign_link_review(intake,state,aal='aal1',fail=True)
        self.campaign_link_review(intake,state,p_ad_account='act_123',fail=True)
        self.campaign_link_review(intake,state,p_campaign='cf000000-0000-4000-8000-000000000099',fail=True)
        self.campaign_link_review(intake,state)
        other_intake=self.campaign_link_fixture(account='another-page')
        other_state=self.campaign_link_state(other_intake)
        self.campaign_link_review(other_intake,other_state,p_id='cf000000-0000-4000-8000-000000000002',fail=True)
        self.sql(f"UPDATE workspace_memberships SET updated_at=clock_timestamp() WHERE workspace_id='{WORKSPACE}' AND user_id='{ADMIN}'")
        self.assertFalse(self.campaign_link_state(intake)['link_current'])
        self.campaign_link_review(other_intake,other_state,p_id='cf000000-0000-4000-8000-000000000002',fail=True)
        self.sql(f"DELETE FROM auth.sessions WHERE id='{ADMIN}'")
        self.campaign_link_review(intake,state,fail=True)

    def test_campaign_draft_scope_idempotence_and_unknown_spend(self):
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda _:self.campaign_draft(),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        self.assertTrue(all(row['status']=='draft' and not row['execution_authorized'] for row in results))
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_campaign'"),'1')
        self.assertEqual(self.sql("SELECT (total_spend IS NULL AND cpl IS NULL AND daily_budget IS NULL AND external_campaign_id IS NULL)::text FROM ad_campaigns"),'true')
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns',user=OTHER),'0')
        self.member(target=OPERATOR,role='operator')
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns',user=OPERATOR),'1')
        self.campaign_draft(actor=OPERATOR,fail=True)
        self.campaign_draft(actor=OTHER,workspace=WORKSPACE_B,fail=True)

    def test_campaign_draft_service_mutation_and_child_associations_blocked(self):
        campaign=self.campaign_draft()['id']
        for query in (f"UPDATE ad_campaigns SET status='active' WHERE id='{campaign}'",f"UPDATE ad_campaigns SET workspace_id=NULL WHERE id='{campaign}'",
                      f"DELETE FROM ad_campaigns WHERE id='{campaign}'",'TRUNCATE ad_campaigns CASCADE',
                      f"INSERT INTO ad_creatives(name,campaign_id) VALUES('Unsafe','{campaign}')",
                      f"INSERT INTO lead_form_configs(name,slug,campaign_id) VALUES('Unsafe','unsafe','{campaign}')",
                      f"UPDATE leads SET ad_campaign_id='{campaign}' WHERE id='{LEAD}'"):
            self.sql(query,user=ADMIN,role='service_role',fail=True)
        self.sql(f"UPDATE ad_campaigns SET name='overwrite' WHERE id='{campaign}'",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT name FROM ad_campaigns WHERE id='{campaign}'"),'Draft campaign')
        self.sql(f"INSERT INTO ad_creatives(name,campaign_id) VALUES('Unsafe','{campaign}')",fail=True)
        self.sql(f"INSERT INTO ad_campaigns(name,workspace_id,acquisition_channel,acquisition_budget_cents,acquisition_currency,acquisition_created_by) VALUES('Raw','{WORKSPACE}','facebook',1,'USD','{ADMIN}')",user=ADMIN,role='service_role',fail=True)
        self.assertEqual(self.sql("SELECT has_table_privilege('authenticated','ad_campaigns','TRIGGER')::text"),'false')
        self.assertEqual(self.sql('SELECT count(*) FROM lead_form_configs',user=ADMIN,role='anon'),'0')

    def test_campaign_creation_requires_live_authority_and_activation(self):
        self.sql("UPDATE private.acquisition_activation SET enabled=false")
        self.campaign_draft(fail=True)
        self.activate()
        self.sql(f"DELETE FROM auth.sessions WHERE id='{ADMIN}'")
        self.campaign_draft(fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM ad_campaigns'),'0')

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

    def prepared_intake(self, **overrides):
        import importlib.util
        # Load the pure normalizer without tools.__init__ importing provider SDKs.
        spec=importlib.util.spec_from_file_location('isolated_acquisition_intake',ROOT/'tools/acquisition_intake.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        prepare_facebook_intake=module.prepare_facebook_intake
        answers=dict(property_address='123 Fixture',city='Dallas',state='TX',authority='yes',
                     condition='repairs',timeline='soon',motivation='move',asking_price='150000',phone='2145550101')
        answers.update(overrides)
        return prepare_facebook_intake(leadgen_id='fixture',provider_data={'id':'fixture','form_id':'form',
            'field_data':[{'name':k,'values':[v]} for k,v in answers.items()]})

    def complete_intake(self, claim, prepared=None, role='service_role', fail=False):
        if prepared is None: prepared=self.prepared_intake()
        value=self.sql(f"SELECT public.complete_facebook_acquisition_intake('{claim['receipt_id']}','{claim['lease_token']}',"
                       f"{literal(json.dumps(prepared))}::jsonb);",user=ADMIN,role=role,fail=fail)
        return value if fail else json.loads(value)

    def candidate_fixture(self, **answers):
        self.bind(); self.member()
        self.sql(f"UPDATE leads SET state='TX' WHERE id='{LEAD}';")
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        return self.complete_intake(claim,self.prepared_intake(**answers))

    def candidates(self, intake, user=ADMIN, workspace=WORKSPACE, limit=20, fail=False, **kwargs):
        value=self.sql(f"SELECT public.acquisition_intake_candidates('{workspace}','{intake}',{limit});",
                       user=user,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def reserve_intake_analysis(self, intake, state, request='b0000000-0000-4000-8000-000000000001', user=ADMIN, inputs=None, fail=False, **kwargs):
        if inputs is None: inputs={'cases':{name:{'strategy':'fix_and_flip'} for name in ('base','downside','upside')}}
        result=self.sql(f"SELECT public.reserve_acquisition_intake_analysis('{request}','{WORKSPACE}','{intake}',"
            f"{literal(state['evidence_hash'])},{literal(json.dumps(inputs))}::jsonb);",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_intake_handoff_atomic_idempotent_and_canonical(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake)); state=self.qualification_state(intake)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.reserve_intake_analysis(intake,state),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in results),1)
        self.assertTrue(all(row['lead_id']==LEAD and row['property_id']==PROPERTY and row['qualification_current'] for row in results))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments;'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_analysis_intakes;'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_analysis_jobs;'),'1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspace_leads WHERE lead_id='{saved['lead_id']}' AND property_id IS NULL;"),'1')
        self.reserve_intake_analysis(intake,state,inputs={'cases':{}},fail=True)
        fresh=self.qualification_state(intake)
        self.reserve_intake_analysis(intake,fresh,request='b0000000-0000-4000-8000-000000000002',inputs={'cases':{}},fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments;'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses;'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='intake_handoff';"),'1')
        self.sql("UPDATE acquisition_analysis_intakes SET evidence_hash='changed';",user=ADMIN,fail=True)
        self.sql('TRUNCATE acquisition_analysis_intakes;',user=ADMIN,role='service_role',fail=True)

    def test_intake_handoff_rejects_unqualified_duplicate_stale_and_scope(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.reserve_intake_analysis(intake,self.qualification_state(intake),fail=True)
        self.identity_review(intake,self.identity_state(intake),action='repeat_inquiry')
        self.reserve_intake_analysis(intake,self.qualification_state(intake),fail=True)
        self.identity_review(intake,self.identity_state(intake),request='71000000-0000-4000-8000-000000000002')
        state=self.qualification_state(intake)
        self.reserve_intake_analysis(intake,state,user=OTHER,fail=True)
        self.reserve_intake_analysis(intake,state,session=False,fail=True)
        self.reserve_intake_analysis(intake,state,role='service_role',fail=True)
        self.sql(f"UPDATE wholesale_ingest.properties SET unit='B' WHERE id='{PROPERTY}';")
        self.reserve_intake_analysis(intake,state,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM deal_analyses;'),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments;'),'0')

    def test_intake_handoff_revocation_blocks_worker_completion(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake)); state=self.qualification_state(intake)
        self.reserve_intake_analysis(intake,state,user=OPERATOR)
        snapshot=self.calculation_snapshot()
        self.identity_review(intake,self.identity_state(intake),request='71000000-0000-4000-8000-000000000002',action='revoke')
        self.calculation_snapshot(fail=True); self.complete_analysis(snapshot,fail=True)
        replay=self.reserve_intake_analysis(intake,state,user=OPERATOR)
        self.assertTrue(replay['duplicate']); self.assertFalse(replay['qualification_current'])
        self.assertEqual(self.sql("SELECT acquisition_status FROM deal_analyses;"),'pending')

    def test_intake_handoff_stale_source_invalidates_offer_but_allows_revocation(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake)); self.reserve_intake_analysis(intake,self.qualification_state(intake))
        output={'status':'calculated','calculation_version':'acquisition-underwriting-v1','strategy':'fix_and_flip',
            'cases':{name:{'status':'calculated','mao':'150000.00','proposed_offer_range':{'low':'120000.00','high':'150000.00'}} for name in ('base','downside','upside')},
            'binding_offer':False,'human_approval_required':True}
        self.complete_analysis(self.calculation_snapshot(),output=output)
        self.propose_offer(); self.review_offer()
        self.propose_offer(identity='c0000000-0000-4000-8000-000000000002')
        self.assertTrue(self.offer_state()['amount_approval_current'])
        self.identity_review(intake,self.identity_state(intake),request='71000000-0000-4000-8000-000000000002',action='revoke')
        current=self.offer_state()
        self.assertFalse(current['amount_approval_current'])
        self.assertIn('INTAKE_QUALIFICATION_CHANGED',current['amount_review_blockers'])
        self.assertNotIn('amount_approved',current['available_review_actions'])
        self.propose_offer(identity='c0000000-0000-4000-8000-000000000003',fail=True)
        notes={key:'Synthetic complete diligence evidence' for key in ('title','liens','occupancy','valuation','repairs','financing','downside')}
        failure=self.sql(f"SELECT public.review_acquisition_offer('d0000000-0000-4000-8000-000000000003','{WORKSPACE}',"
            f"'c0000000-0000-4000-8000-000000000002',1,'amount_approved','Synthetic decision',{literal(json.dumps(notes))}::jsonb);",user=ADMIN,fail=True)
        self.assertIn('Intake qualification changed',failure)
        cross_scope=self.sql(f"SELECT public.propose_acquisition_offer('c0000000-0000-4000-8000-000000000004','{WORKSPACE_B}',"
            "'b0000000-0000-4000-8000-000000000001','base',140000,'Synthetic cross-scope attempt');",user=OTHER,fail=True)
        self.assertIn('Workspace analysis unavailable',cross_scope)
        self.review_offer(identity='d0000000-0000-4000-8000-000000000002',status='approval_revoked',sequence=2)
        self.assertEqual(self.offer_state()['historical_status'],'approval_revoked')

    def test_intake_handoff_cannot_adopt_an_existing_manual_analysis(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake)); self.reserve_analysis()
        self.reserve_intake_analysis(intake,self.qualification_state(intake),fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_analysis_intakes;'),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments;'),'0')

    def qualification_state(self, intake, user=ADMIN, fail=False, **kwargs):
        result=self.sql(f"SELECT public.acquisition_intake_qualification_state('{WORKSPACE}','{intake}');",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def record_assessment(self, intake, state, request='73000000-0000-4000-8000-000000000001', user=ADMIN, fail=False, **kwargs):
        result=self.sql(f"SELECT public.record_acquisition_intake_assessment('{request}','{WORKSPACE}','{intake}',"
            f"{state['sequence']},{literal(state['evidence_hash'])});",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_qualification_complete_requires_current_property_and_territory(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.assertEqual(self.qualification_state(intake)['assessment']['classification'],'requires_human_review')
        self.identity_review(intake,self.identity_state(intake))
        state=self.qualification_state(intake)
        self.assertEqual(state['assessment']['classification'],'qualified')
        self.assertEqual(state['assessment']['canonical_county'],'dallas')
        self.assertFalse(state['assessment']['ownership_verified']); self.assertFalse(state['assessment']['outreach_authorized'])
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.record_assessment(intake,state),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(self.qualification_state(intake)['assessment_current'])
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake_assessment';"),'1')
        self.sql(f"UPDATE wholesale_ingest.properties SET county='Collin' WHERE id='{PROPERTY}';")
        changed=self.qualification_state(intake)
        self.assertFalse(changed['assessment_current'])
        self.assertEqual(changed['latest_assessment']['classification'],'qualified')
        self.assertEqual(changed['latest_assessment']['assessment']['target_snapshot']['county'],'Dallas')
        self.assertEqual(changed['assessment']['target_snapshot']['county'],'Collin')
        self.assertEqual(changed['assessment']['classification'],'requires_human_review')
        self.record_assessment(intake,state,request='73000000-0000-4000-8000-000000000002',fail=True)
        self.identity_review(intake,self.identity_state(intake),request='71000000-0000-4000-8000-000000000002')
        outside=self.qualification_state(intake)
        self.assertEqual(outside['assessment']['classification'],'qualified')
        self.assertEqual(outside['assessment']['canonical_county'],'collin')
        self.sql(f"UPDATE wholesale_ingest.properties SET county='Denton' WHERE id='{PROPERTY}';",fail=True)
        self.record_assessment(intake,outside,request='73000000-0000-4000-8000-000000000002',user=OPERATOR)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments;',user=OPERATOR),'2')
        self.sql("UPDATE acquisition_intake_assessments SET classification='qualified';",user=ADMIN,fail=True)
        self.sql('TRUNCATE acquisition_intake_assessments;',user=ADMIN,role='service_role',fail=True)

    def test_qualification_incomplete_preserves_missing_and_invalid_contact(self):
        saved=self.candidate_fixture(condition='',phone='2145550101 ext 9'); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake))
        assessment=self.qualification_state(intake)['assessment']
        self.assertEqual(assessment['classification'],'incomplete')
        self.assertIn('condition',assessment['missing_fields']); self.assertIn('valid_contact',assessment['missing_fields'])

    def test_qualification_duplicate_requires_reviewed_repeat_not_same_phone(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']
        self.assertNotEqual(self.qualification_state(intake)['assessment']['classification'],'duplicate')
        self.identity_review(intake,self.identity_state(intake),action='repeat_inquiry')
        state=self.qualification_state(intake)
        self.assertEqual(state['assessment']['classification'],'duplicate')
        self.record_assessment(intake,state)
        self.identity_review(intake,self.identity_state(intake),request='71000000-0000-4000-8000-000000000002',action='revoke')
        self.assertFalse(self.qualification_state(intake)['assessment_current'])
        self.assertNotEqual(self.qualification_state(intake)['assessment']['classification'],'duplicate')

    def test_qualification_denied_authority_is_not_overridden_by_property_review(self):
        saved=self.candidate_fixture(authority='no'); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake))
        self.assertEqual(self.qualification_state(intake)['assessment']['classification'],'unqualified')

    def test_qualification_ambiguous_price_is_never_zero_or_qualified(self):
        saved=self.candidate_fixture(asking_price='150k'); intake=saved['intake_id']
        self.identity_review(intake,self.identity_state(intake))
        self.assertEqual(self.qualification_state(intake)['assessment']['classification'],'requires_human_review')
        self.assertEqual(self.sql(f"SELECT (asking_price IS NULL)::text FROM leads WHERE id='{saved['lead_id']}';"),'true')

    def test_qualification_collin_explicit_zero_and_gate_scope_checks(self):
        saved=self.candidate_fixture(asking_price='0'); intake=saved['intake_id']
        self.sql(f"UPDATE wholesale_ingest.properties SET county='Collin' WHERE id='{PROPERTY}';")
        self.identity_review(intake,self.identity_state(intake))
        state=self.qualification_state(intake)
        self.assertEqual(state['assessment']['classification'],'qualified')
        self.qualification_state(intake,user=OTHER,fail=True)
        self.qualification_state(intake,session=False,fail=True)
        self.record_assessment(intake,state,user=OTHER,fail=True)
        self.record_assessment(intake,state,session=False,fail=True)
        self.record_assessment(intake,state,role='service_role',fail=True)
        self.record_assessment(intake,state)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_assessments;',user=OTHER),'0')
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        held=self.qualification_state(intake)
        self.assertFalse(held['assessment_current'])
        self.assertEqual(held['assessment']['classification'],'requires_human_review')
        self.record_assessment(intake,held,request='73000000-0000-4000-8000-000000000002',fail=True)

    def identity_state(self, intake, target=LEAD, user=ADMIN, fail=False, **kwargs):
        target_sql='NULL' if target is None else literal(target)
        result=self.sql(f"SELECT public.acquisition_intake_identity_state('{WORKSPACE}','{intake}',{target_sql});",user=user,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def identity_review(self, intake, state, request='71000000-0000-4000-8000-000000000001', action='link_property', user=ADMIN, fail=False, **overrides):
        values=dict(p_id=request,p_workspace=WORKSPACE,p_intake=intake,p_expected_sequence=state['sequence'],
            p_preparation_hash=state['preparation_hash'],p_action=action,p_target=None if action=='revoke' else LEAD,
            p_target_hash=None if action=='revoke' else state['target_hash'],p_property_basis=None if action=='revoke' else 'parcel_document',
            p_property_evidence_ref=None if action=='revoke' else 'synthetic-parcel-review-42',
            p_seller_evidence_ref='synthetic-seller-identity-review-42' if action=='repeat_inquiry' else None,
            p_note='Synthetic reviewer checked the property and seller evidence.')
        sql_options={k:overrides.pop(k) for k in ('aal','session','role') if k in overrides}
        values.update(overrides)
        args=','.join(f"{key}=>"+('NULL' if value is None else str(value) if isinstance(value,int) else literal(value)) for key,value in values.items())
        result=self.sql(f"SELECT public.review_acquisition_intake_identity({args});",user=user,fail=fail,**sql_options)
        return result if fail else json.loads(result)

    def test_intake_identity_review_concurrent_idempotent_and_non_merging(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']; state=self.identity_state(intake)
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.identity_review(intake,state),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        current=self.identity_state(intake)
        self.assertTrue(current['link_current']); self.assertEqual(current['sequence'],1)
        self.assertEqual(current['latest_review']['target_property_id'],PROPERTY)
        self.assertFalse(current['ownership_verified']); self.assertFalse(current['outreach_authorized'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_identity_reviews;'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake_identity';"),'1')
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspace_leads WHERE lead_id='{saved['lead_id']}' AND property_id IS NULL;"),'1')
        self.identity_review(intake,state,p_note='Changed request must not silently replay.',fail=True)
        self.identity_review(intake,state,request='71000000-0000-4000-8000-000000000002',fail=True)
        self.sql('UPDATE acquisition_intake_identity_reviews SET sequence=99;',user=ADMIN,fail=True)
        self.sql('TRUNCATE acquisition_intake_identity_reviews;',user=ADMIN,role='service_role',fail=True)

    def test_intake_identity_review_invalidates_on_evidence_and_authority_changes(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']; state=self.identity_state(intake)
        self.sql(f"UPDATE leads SET owner_phone_1='+12145550999' WHERE id='{LEAD}';")
        self.identity_review(intake,state,fail=True)
        fresh=self.identity_state(intake); self.identity_review(intake,fresh,action='repeat_inquiry')
        self.assertTrue(self.identity_state(intake)['link_current'])
        self.sql(f"UPDATE wholesale_ingest.properties SET unit='B' WHERE id='{PROPERTY}';")
        self.assertFalse(self.identity_state(intake)['link_current'])
        fresh=self.identity_state(intake)
        self.identity_review(intake,fresh,request='71000000-0000-4000-8000-000000000002')
        self.sql(f"UPDATE workspace_memberships SET updated_at=clock_timestamp() WHERE workspace_id='{WORKSPACE}' AND user_id='{ADMIN}';")
        self.assertFalse(self.identity_state(intake)['link_current'])

    def test_intake_identity_review_requires_scope_mfa_and_documented_evidence(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']; state=self.identity_state(intake)
        for user in (OTHER,OPERATOR): self.identity_review(intake,state,user=user,fail=True)
        self.identity_review(intake,state,aal='aal1',fail=True)
        self.identity_review(intake,state,session=False,fail=True)
        self.identity_review(intake,state,role='service_role',fail=True)
        self.identity_review(intake,state,p_property_basis='phone_match',fail=True)
        self.identity_review(intake,state,p_property_evidence_ref=None,fail=True)
        self.identity_review(intake,state,action='repeat_inquiry',p_seller_evidence_ref=None,fail=True)
        self.identity_review(intake,state,p_target=saved['lead_id'],fail=True)
        self.identity_state(intake,target=LEAD_B,fail=True)
        self.identity_state(intake,user=OTHER,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_identity_reviews;'),'0')

    def test_intake_identity_revocation_preserves_history_and_remains_available_when_held(self):
        saved=self.candidate_fixture(); intake=saved['intake_id']; state=self.identity_state(intake)
        self.identity_review(intake,state,action='revoke',fail=True)
        self.identity_review(intake,state,action='repeat_inquiry')
        self.sql('UPDATE private.acquisition_activation SET enabled=false;')
        self.assertFalse(self.identity_state(intake)['link_current'])
        current=self.identity_state(intake)
        self.identity_review(intake,current,request='71000000-0000-4000-8000-000000000002',fail=True)
        self.identity_review(intake,current,request='71000000-0000-4000-8000-000000000003',action='revoke')
        revoked=self.identity_state(intake)
        self.assertFalse(revoked['link_current']); self.assertEqual(revoked['latest_review']['action'],'revoke')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_identity_reviews;',user=OPERATOR),'2')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_intake_identity_reviews;',user=OTHER),'0')

    def test_intake_candidates_distinguish_contact_from_property(self):
        saved=self.candidate_fixture(property_address='1 Fixture St',city=' Dallas ',state='texas')
        result=self.candidates(saved['intake_id'],user=OPERATOR)
        self.assertEqual(len(result['items']),1)
        match=result['items'][0]
        self.assertEqual(match['lead_id'],LEAD)
        self.assertEqual(match['property_id'],PROPERTY)
        self.assertTrue(match['address_match']); self.assertTrue(match['phone_match'])
        self.assertEqual(match['match_basis'],'EXACT_ADDRESS_TEXT')
        self.assertFalse(result['merge_authorized']); self.assertFalse(result['outreach_authorized'])
        self.assertNotIn('owner_phone_1',json.dumps(result))
        self.assertEqual(self.candidates(saved['intake_id'])['candidate_hash'],result['candidate_hash'])
        self.sql(f"UPDATE leads SET property_address='1 Fixture St Unit B' WHERE id='{LEAD}';")
        changed=self.candidates(saved['intake_id'])
        self.assertFalse(changed['items'][0]['address_match'])
        self.assertEqual(changed['items'][0]['match_basis'],'CONTACT_ONLY')
        self.assertNotEqual(changed['candidate_hash'],result['candidate_hash'])
        self.assertEqual(self.sql('SELECT count(*) FROM seller_intakes;'),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM leads;'),'3')

    def test_intake_candidates_scope_role_session_and_no_global_search(self):
        saved=self.candidate_fixture()
        self.bind(actor=OTHER,workspace=WORKSPACE_B,lead=LEAD_B,property_id=None)
        self.assertEqual([row['lead_id'] for row in self.candidates(saved['intake_id'])['items']],[LEAD])
        self.candidates(saved['intake_id'],user=OTHER,fail=True)
        self.candidates(saved['intake_id'],user=OTHER,workspace=WORKSPACE_B,fail=True)
        self.member(target=CALLER,role='acquisition_caller')
        self.candidates(saved['intake_id'],user=CALLER,fail=True)
        self.candidates(saved['intake_id'],session=False,fail=True)
        self.candidates(saved['intake_id'],role='service_role',fail=True)
        self.candidates(saved['intake_id'],limit=0,fail=True)
        self.candidates(saved['intake_id'],limit=51,fail=True)

    def test_intake_candidates_missing_fields_and_ambiguous_contacts_never_match(self):
        saved=self.candidate_fixture(property_address='',city='',state='',phone='2145550101 ext 9',email='invalid')
        result=self.candidates(saved['intake_id'])
        self.assertEqual(result['items'],[])
        self.assertEqual(result['classification'],'incomplete')
        self.assertFalse(result['truncated'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM workspace_leads WHERE lead_id='{saved['lead_id']}' AND property_id IS NULL;"),'1')

    def test_intake_candidates_bounded_and_deterministic(self):
        saved=self.candidate_fixture()
        self.bind(lead=LEAD_B,property_id=None)
        result=self.candidates(saved['intake_id'],limit=1)
        self.assertEqual(len(result['items']),1); self.assertTrue(result['truncated'])
        self.assertEqual(result['items'][0]['lead_id'],LEAD)
        all_rows=self.candidates(saved['intake_id'],limit=2)
        self.assertEqual(len(all_rows['items']),2); self.assertFalse(all_rows['truncated'])

    def test_intake_atomic_idempotent_and_workspace_scoped(self):
        # Exercise the inspected production retention trigger, not just a stub.
        retention=(ROOT/'frontend/supabase/migrations/20261016230511_protect_website_inquiry_retention.sql').read_text()
        self.sql(retention.split('-- Repair only the display classifications')[0])
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.complete_intake(claim),range(3)))
        self.assertEqual(len({r['lead_id'] for r in results}),1)
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        lead=results[0]['lead_id']
        self.assertNotEqual(lead,LEAD) # Same phone never merges unrelated CRM property.
        self.assertEqual(self.sql(f"SELECT owner_phone_1 FROM leads WHERE id='{lead}';"),'+12145550101')
        self.assertEqual(self.sql(f"SELECT (bound_by IS NULL AND binding_integration_id IS NOT NULL AND property_id IS NULL)::text FROM workspace_leads WHERE lead_id='{lead}';"),'true')
        self.assertEqual(self.sql(f"SELECT (NOT sms_sequence_active AND NOT email_sequence_active AND ai_calling_paused AND NOT retention_deletable)::text FROM leads WHERE id='{lead}';"),'true')
        self.assertEqual(self.sql("SELECT count(*) FROM seller_intakes;",user=ADMIN),'1')
        for actor in (OTHER,CALLER):
            self.assertEqual(self.sql("SELECT count(*) FROM seller_intakes;",user=actor),'0')
        self.assertEqual(self.sql("SELECT state FROM private.acquisition_inbox_processing;"),'completed')
        self.assertEqual(self.inbox_claim(),[])
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='seller_intake';"),'1')
        self.complete_intake(claim,self.prepared_intake(asking_price='1'),fail=True)
        self.complete_intake(claim,role='authenticated',fail=True)
        self.sql("UPDATE seller_intakes SET classification='unqualified';",user=ADMIN,role='service_role',fail=True)

    def test_intake_incomplete_and_invalid_contact_evidence_preserved(self):
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        result=self.complete_intake(claim,self.prepared_intake(property_address='',asking_price='',phone='2145550101 ext 2'))
        self.assertEqual(result['classification'],'incomplete')
        lead=result['lead_id']
        self.assertEqual(self.sql(f"SELECT (property_address='' AND asking_price IS NULL AND owner_phone_1 IS NULL)::text FROM leads WHERE id='{lead}';"),'true')
        self.assertEqual(self.sql("SELECT normalization_notes[1] FROM seller_intakes;"),'PHONE_REVIEW_REQUIRED')
        self.assertEqual(self.sql("SELECT prepared_answers->'answers'->>'phone' FROM seller_intakes;"),'2145550101 ext 2')

    def test_intake_failure_rolls_back_lead_binding_and_completion(self):
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        self.sql("CREATE FUNCTION private.fail_intake_fixture() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture failure'; END $$; "
                 "CREATE TRIGGER fail_intake_fixture BEFORE INSERT ON seller_intakes FOR EACH ROW EXECUTE FUNCTION private.fail_intake_fixture();")
        self.complete_intake(claim,fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM leads WHERE source='facebook_acquisition';"),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM workspace_leads WHERE binding_integration_id IS NOT NULL;"),'0')
        self.assertEqual(self.sql("SELECT state FROM private.acquisition_inbox_processing;"),'leased')
        self.sql("DROP TRIGGER fail_intake_fixture ON seller_intakes;")
        self.assertFalse(self.complete_intake(claim)['duplicate'])

    def test_intake_lease_activation_and_permission_assertions_enforced(self):
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        invalid=self.prepared_intake(); invalid['outreach_authorized']=True
        self.complete_intake(claim,invalid,fail=True)
        invalid=self.prepared_intake(); invalid['external_lead_id']='another-event'
        self.complete_intake(claim,invalid,fail=True)
        invalid=self.prepared_intake(); invalid['classification']='qualified'
        self.complete_intake(claim,invalid,fail=True)
        self.sql("UPDATE private.acquisition_inbox_processing SET lease_expires_at=now()-interval '1 second';")
        self.complete_intake(claim,fail=True)
        fresh=self.inbox_claim()[0]
        self.complete_intake(claim,fail=True)
        self.sql("UPDATE private.acquisition_activation SET enabled=false;")
        self.complete_intake(fresh,fail=True)
        self.activate()
        self.sql("UPDATE private.acquisition_integrations SET enabled=false;")
        self.complete_intake(fresh,fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM seller_intakes;"),'0')

    def batch_accept(self, events, role='service_role', fail=False):
        result=self.sql(f"SELECT public.accept_facebook_acquisition_batch({literal(json.dumps(events))}::jsonb,convert_to('signed fixture','UTF8'));",user=ADMIN,role=role,fail=fail)
        return result if fail else json.loads(result)

    def test_facebook_batch_atomic_rollback_and_replay(self):
        self.inbox_config(account='100')
        first={'page_id':'100','leadgen_id':'1','form_id':'200'}
        second={'page_id':'999','leadgen_id':'2','form_id':'200'}
        self.batch_accept([first,second],fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE workspace_id IS NOT NULL;"),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM private.acquisition_inbox_processing;"),'0')
        self.inbox_config(account='999',workspace=WORKSPACE_B)
        results=self.batch_accept([first,second])
        replay=self.batch_accept([second,first])
        self.assertEqual({r['receipt_id'] for r in results},{r['receipt_id'] for r in replay})
        self.assertTrue(all(r['duplicate'] for r in replay))
        self.assertEqual({r['workspace_id'] for r in results},{WORKSPACE,WORKSPACE_B})
        self.batch_accept([first],role='authenticated',fail=True)

    def test_facebook_batch_parallel_and_conflicting_events(self):
        self.inbox_config(account='100')
        events=[{'page_id':'100','leadgen_id':str(i),'form_id':'200'} for i in (1,2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(self.batch_accept,[events,list(reversed(events))]))
        self.assertEqual(sum(not r['duplicate'] for batch in results for r in batch),2)
        conflicting=dict(events[0],form_id='201')
        self.batch_accept([conflicting],fail=True)
        self.batch_accept([],fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM webhook_jobs WHERE workspace_id IS NOT NULL;"),'2')

    def inquiry_health(self, actor=ADMIN, workspace=WORKSPACE, after=None, limit=20, fail=False):
        cursor=literal(after)+'::uuid' if after else 'NULL'
        result=self.sql(f"SELECT public.acquisition_inquiry_health('{workspace}',{cursor},{limit});",user=actor,fail=fail)
        return result if fail else json.loads(result)

    def test_inquiry_health_workspace_roles_and_safe_summary(self):
        self.inbox_config(); self.inbox_accept(); claim=self.inbox_claim()[0]
        self.inbox_defer(claim,'review','CREDENTIALS_INVALID')
        health=self.inquiry_health()
        self.assertEqual(health['summary']['requires_review'],1)
        self.assertEqual(health['items'][0]['reason_code'],'CREDENTIALS_INVALID')
        self.assertIn('credential',health['items'][0]['guidance'])
        self.assertFalse(health['recovery_authorized'])
        self.assertFalse(health['worker_runtime_verified'])
        encoded=json.dumps(health)
        for value in ('lease_token','payload','fixture-page','external_event_id'):
            self.assertNotIn(value,encoded)
        self.inquiry_health(actor=OTHER,fail=True)
        self.member(target=CALLER,role='acquisition_caller')
        self.inquiry_health(actor=CALLER,fail=True)
        self.member(target=OPERATOR,role='operator')
        self.assertEqual(self.inquiry_health(actor=OPERATOR)['summary']['received'],1)
        self.member(target=OPERATOR,role='operator',status='revoked')
        self.inquiry_health(actor=OPERATOR,fail=True)
        self.assertEqual(self.inquiry_health(actor=OTHER,workspace=WORKSPACE_B)['summary']['received'],0)

    def test_inquiry_health_pagination_gates_and_completion(self):
        self.inbox_config(account='100')
        self.batch_accept([{'page_id':'100','leadgen_id':str(i),'form_id':'200'} for i in (1,2,3)])
        first=self.inquiry_health(limit=2)
        self.assertEqual(len(first['items']),2)
        last=self.inquiry_health(after=first['next_after'],limit=2)
        self.assertEqual(len(last['items']),1)
        self.assertIsNone(last['next_after'])
        self.assertEqual(first['summary'],last['summary'])
        self.assertEqual(len({item['receipt_id'] for item in first['items']+last['items']}),3)
        self.inquiry_health(limit=51,fail=True)
        self.sql("UPDATE private.acquisition_integrations SET enabled=false;")
        self.sql("UPDATE private.acquisition_activation SET enabled=false;")
        held=self.inquiry_health()
        self.assertEqual(held['summary']['disabled_integration_pending'],3)
        self.assertIn('ACQUISITION_ACTIVATION_DISABLED',held['items'][0]['blockers'])
        self.assertIn('INTEGRATION_DISABLED',held['items'][0]['blockers'])
        self.activate()
        self.sql("UPDATE private.acquisition_integrations SET enabled=true;")
        integration=self.sql("SELECT id FROM private.acquisition_integrations WHERE account_id='100';")
        claim=json.loads(self.sql(f"SELECT public.claim_acquisition_events('{integration}',1,120);",user=ADMIN,role='service_role'))[0]
        prepared=self.prepared_intake(); prepared['external_lead_id']=claim['external_event_id']; prepared['provider_form_id']='200'
        self.complete_intake(claim,prepared)
        done=self.inquiry_health()
        self.assertEqual(done['summary']['completed'],1)
        self.assertEqual(len(done['items']),2)

    def recovery(self, claim, snapshot, identity='e0000000-0000-4000-8000-000000000001', actor=ADMIN, aal='aal2', note='Credential replaced and Page access verified in isolated test', fail=False):
        result=self.sql(f"SELECT public.recover_acquisition_inquiry('{identity}','{WORKSPACE}','{claim['receipt_id']}',"
                        f"{literal(snapshot['updated_at'])}::timestamptz,{literal(snapshot['reason_code'])},{literal(note)},'test-evidence/credential-check');",
                        user=actor,aal=aal,fail=fail)
        return result if fail else json.loads(result)

    def test_recovery_exact_review_idempotence_and_stale_worker_denial(self):
        self.inbox_config();self.inbox_accept();claim=self.inbox_claim()[0]
        self.inbox_defer(claim,'review','CREDENTIALS_INVALID'); snapshot=self.inquiry_health()['items'][0]
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.recovery(claim,snapshot),range(3)))
        self.assertEqual(sum(not result['duplicate'] for result in results),1)
        self.assertEqual({result['cycle'] for result in results},{1})
        self.assertFalse(results[0]['outreach_authorized'])
        self.recovery(claim,snapshot,note='Different review evidence must not replace the original',fail=True)
        self.recovery(claim,snapshot,identity='e0000000-0000-4000-8000-000000000002',fail=True)
        self.inbox_defer(claim,'review','CREDENTIALS_INVALID',fail=True)
        fresh=self.inbox_claim()[0]
        self.assertNotEqual(fresh['lease_token'],claim['lease_token'])
        self.assertEqual(fresh['attempt'],1)
        self.complete_intake(claim,fail=True)
        self.complete_intake(fresh)
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='recovery_approved';"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_inquiry_recoveries;',user=OTHER),'0')
        self.sql("DELETE FROM acquisition_inquiry_recoveries;",user=ADMIN,role='service_role',fail=True)

    def test_recovery_role_mfa_and_activation_requirements(self):
        self.inbox_config();self.inbox_accept();claim=self.inbox_claim()[0]
        self.inbox_defer(claim,'review','PERMISSION_DENIED');snapshot=self.inquiry_health()['items'][0]
        self.recovery(claim,snapshot,aal='aal1',fail=True)
        self.recovery(claim,snapshot,actor=OTHER,fail=True)
        self.member(target=OPERATOR,role='operator')
        self.recovery(claim,snapshot,actor=OPERATOR,fail=True)
        self.sql("UPDATE private.acquisition_integrations SET enabled=false;")
        self.recovery(claim,snapshot,fail=True)
        self.sql("UPDATE private.acquisition_integrations SET enabled=true;")
        self.sql("UPDATE private.acquisition_activation SET enabled=false;")
        self.recovery(claim,snapshot,fail=True)
        self.activate()
        self.sql(f"DELETE FROM auth.sessions WHERE user_id='{ADMIN}';")
        self.recovery(claim,snapshot,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_inquiry_recoveries;'),'0')

    def test_recovery_three_cycle_budget_preserves_history(self):
        self.inbox_config();self.inbox_accept()
        for cycle in range(1,5):
            claim=self.inbox_claim()[0]
            self.inbox_defer(claim,'review','CREDENTIALS_INVALID');snapshot=self.inquiry_health()['items'][0]
            identity='e0000000-0000-4000-8000-'+str(cycle).zfill(12)
            if cycle==4:
                self.recovery(claim,snapshot,identity=identity,fail=True)
            else:
                self.assertEqual(self.recovery(claim,snapshot,identity=identity)['cycle'],cycle)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_inquiry_recoveries;'),'3')
        self.assertEqual(self.sql('SELECT sum(previous_attempts) FROM acquisition_inquiry_recoveries;'),'3')
        self.assertEqual(self.sql('SELECT state FROM private.acquisition_inbox_processing;'),'review')

    def test_recovery_expired_payload_and_stale_review_are_blocked(self):
        self.inbox_config();self.inbox_accept();claim=self.inbox_claim()[0]
        self.inbox_defer(claim,'review','CREDENTIALS_INVALID');snapshot=self.inquiry_health()['items'][0]
        stale=dict(snapshot,updated_at='2000-01-01T00:00:00Z')
        self.recovery(claim,stale,fail=True)
        expired=self.sql("INSERT INTO webhook_jobs(source,payload,status,workspace_id,acquisition_integration_id,external_event_id,"
                 "acquisition_event_type,acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,acquisition_expires_at) "
                 "SELECT source,payload,status,workspace_id,acquisition_integration_id,'expired-recovery',acquisition_event_type,"
                 "acquisition_payload_hash,acquisition_raw_body,acquisition_raw_hash,now()-interval '1 day' FROM webhook_jobs WHERE workspace_id IS NOT NULL RETURNING id;")
        self.sql(f"UPDATE private.acquisition_inbox_processing SET state='review',reason_code='CREDENTIALS_INVALID' WHERE receipt_id='{expired}';")
        expired_snapshot=next(item for item in self.inquiry_health()['items'] if item['receipt_id']==expired)
        self.recovery({'receipt_id':expired},expired_snapshot,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_inquiry_recoveries;'),'0')

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
            self.sql(f"INSERT INTO lead_form_configs(id,name,slug,active,send_confirmation_sms) VALUES('{form}','Synthetic permission form','synthetic-permission',false,false);")
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

    def test_inspected_call_event_fixture_preserves_legacy_and_scopes_bound_leads(self):
        event='91000000-0000-4000-8000-000000000001'
        self.sql(f"INSERT INTO call_events(id,lead_id,disposition) VALUES('{event}','{LEAD}','no_answer');",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT dialer||':'||raw_payload::text FROM call_events WHERE id='{event}';",user=ADMIN),'batchdialer:{}')
        self.sql(f"UPDATE call_events SET notes='legacy edit' WHERE id='{event}';",user=OTHER)
        self.assertEqual(self.sql(f"SELECT notes FROM call_events WHERE id='{event}';",user=ADMIN),'legacy edit')
        self.bind()
        self.assertEqual(self.sql('SELECT count(*) FROM call_events;',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM call_events;',user=ADMIN),'1')
        self.sql(f"UPDATE call_events SET notes='blocked' WHERE id='{event}';",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT notes FROM call_events WHERE id='{event}';"),'legacy edit')
        self.sql(f"INSERT INTO call_events(lead_id,disposition) VALUES('{LEAD}','unknown');",user=ADMIN,fail=True)
        self.member(target=CALLER,role='acquisition_caller')
        self.assertEqual(self.sql('SELECT count(*) FROM call_events;',user=CALLER),'0')

    def test_inspected_call_event_fixture_exposes_gaps_for_inbound_extension(self):
        self.sql("INSERT INTO call_events(disposition) VALUES('unknown');",user=ADMIN)
        self.assertEqual(self.sql('SELECT count(*) FROM call_events;',user=OTHER),'1')
        self.assertEqual(self.sql("SELECT has_table_privilege('authenticated','call_events','TRUNCATE');"),'f')
        self.assertEqual(self.sql("SELECT has_table_privilege('service_role','call_events','TRIGGER');"),'f')
        self.sql("INSERT INTO call_events(disposition,lead_id) VALUES('unknown','ffffffff-ffff-4fff-8fff-ffffffffffff');",fail=True)
        self.sql("INSERT INTO call_events(dialer) VALUES('retell');",fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_indexes WHERE tablename='call_events';"),'6')

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
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test', action='append', choices=unittest.defaultTestLoader.getTestCaseNames(WorkspaceTests),
                        help='Run named acceptance cases; default runs the full suite')
    args=parser.parse_args()
    raise SystemExit(main(test_names=args.test))
