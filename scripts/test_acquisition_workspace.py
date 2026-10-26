"""Real PostgreSQL acceptance in a disposable Unix-socket-only cluster.

Uses only stdlib + local PostgreSQL binaries, no inherited credentials, dotenv,
TCP listener, provider SDK, cron, pg_net, or production database connection.
This verifies the migration's touched dependencies; full upgrade QA is separate.
"""
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
        for schema, table in (('public','profiles'), ('public','audit_logs'), ('public','leads'),
                              ('wholesale_ingest','properties'), ('public','campaigns'),
                              ('public','buyer_import_log'), ('public','buyers'), ('public','deals'), ('public','deal_matches'),
                              ('wholesale_ingest','property_aliases')):
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
        self.sql(MIGRATION.read_text())
        if self._testMethodName == 'test_migration_scopes_preexisting_memberships':
            self.create(ADMIN, WORKSPACE)
            self.member()
        self.sql(BOUNDARY_MIGRATION.read_text())
        self.sql(RELATED_MIGRATION.read_text())
        self.create(ADMIN, WORKSPACE)
        self.create(OTHER, WORKSPACE_B)
        self.sql(f"INSERT INTO leads(id,property_address,city,owner_phone_1) VALUES ('{LEAD}','1 Fixture St','Dallas','+12145550101'),('{LEAD_B}','2 Fixture St','Plano','+12145550101'); "
                 f"INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES('{PROPERTY}','TX','Dallas','fixture-parcel','{LEAD}'); "
                 "INSERT INTO campaigns(name) VALUES('legacy-sentinel');")

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


def main():
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
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkspaceTests)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            return 0 if result.wasSuccessful() else 1
        finally:
            if started:
                run([PG/'pg_ctl','-D',data,'-m','immediate','-w','stop'])


if __name__ == '__main__':
    raise SystemExit(main())
