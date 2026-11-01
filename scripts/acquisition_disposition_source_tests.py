"""Derive executed originals from the current proposal; never grant exit authority."""
import json,subprocess,select,time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from acquisition_disposition_storage_tests import DispositionStorageTests
from acquisition_disposition_plan_tests import PLAN,SECOND,WITHDRAW
from acquisition_title_storage_tests import TITLE_FILE,TITLE_SCAN,TITLE_POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,PG,literal
from acquisition_contract_document_tests import DRAFT
MIGRATION=ROOT/'frontend/supabase/migrations/20261101074845_acquisition_disposition_source_resolution.sql'

class DispositionSourceCases:
    def disposition_sources(self,findings,plan=PLAN,workspace=WORKSPACE,version=2,actor=ADMIN,aal='aal2',session=True,fail=False):
        claims=dict(sub=actor,role='authenticated',aal=aal)
        if session:claims['session_id']=actor
        query=f"SET request.jwt.claims={literal(json.dumps(claims))}; SELECT private.resolve_disposition_review_sources('{workspace}','{DRAFT}',{version},'{plan}',{literal(json.dumps(findings))}::jsonb)"
        result=self.sql(query,fail=fail)
        return result if fail else json.loads(result)

    def test_signature_disposition_sources_derive_executed_root_and_preserve_originals(self):
        row=self.prepare_disposition_storage(True);value=row['disposition_findings']
        before=self.sql('SELECT count(*) FROM acquisition_contract_reviews')
        result=self.disposition_sources(value)
        for name in ('artifact_id','source_version','verification_id','sha256'):self.assertEqual(result[name],row[name])
        self.assertEqual(result['plan_id'],PLAN);self.assertEqual(result['execution_transition_id'],row['disposition_execution_id'])
        self.assertEqual(result['title_entry_id'],row['disposition_title_entry_id']);self.assertEqual(len(result['sources']),1)
        for key in ('legal_review_approved','disposition_approved','marketing_authorized','execution_authorized'):self.assertFalse(result[key])
        value['closing_structure']['sources']=[dict(artifact_id=TITLE_FILE,artifact_version=2,sha256='b'*64,locator='Title report original schedule A')]
        result=self.disposition_sources(value);self.assertEqual(len(result['sources']),2)
        self.assertEqual({source['source_version'] for source in result['sources']},{1,2})
        self.assertEqual(before,self.sql('SELECT count(*) FROM acquisition_contract_reviews'))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans'),'1')

    def test_signature_disposition_sources_require_current_exact_plan_and_contract_clauses(self):
        row=self.prepare_disposition_storage(True);value=row['disposition_findings']
        for name in ('contractual_interest','assignment_provisions'):
            bad=deepcopy(value);target=bad[name] if name=='contractual_interest' else bad['assignment'][name]
            target['sources']=[dict(artifact_id=TITLE_FILE,artifact_version=2,sha256='b'*64,locator='Unrelated title clause')]
            self.disposition_sources(bad,fail=True)
        self.plan(self.plan_args(p_id=SECOND,p_expected_sequence=1,p_exit_type='wholesale_assignment'))
        self.disposition_sources(value,fail=True)
        self.assertEqual(self.disposition_sources(value,plan=SECOND)['plan_id'],SECOND)
        self.plan(self.plan_args(p_id=WITHDRAW,p_expected_sequence=2,p_status='withdrawn',p_exit_type='wholesale_assignment',p_original_plan=SECOND))
        self.disposition_sources(value,plan=SECOND,fail=True)

    def test_signature_disposition_sources_scope_source_mismatch_and_private_boundary(self):
        row=self.prepare_disposition_storage();value=row['disposition_findings'];self.member()
        for patch in ({'workspace':WORKSPACE_B},{'version':1},{'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'plan':SECOND}):
            self.disposition_sources(value,fail=True,**patch)
        for patch in ({'sha256':'e'*64},{'artifact_version':3-row['source_version']}):
            bad=deepcopy(value)
            for name in ('contractual_interest','closing_structure','remaining_obligations'):bad[name]['sources'][0].update(patch)
            self.disposition_sources(bad,fail=True)
        for role in ('authenticated','service_role','anon'):
            self.sql(f"SELECT private.resolve_disposition_review_sources('{WORKSPACE}','{DRAFT}',2,'{PLAN}','{{}}')",user=ADMIN,role=role,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.disposition_sources(value,fail=True)

    def test_signature_disposition_sources_revoked_scanner_retention_and_session(self):
        row=self.prepare_disposition_storage();value=row['disposition_findings']
        policy=self.sql(f"SELECT retention_policy_id FROM acquisition_evidence_artifacts WHERE id='{row['artifact_id']}'")
        self.sql("UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp() WHERE purpose='purchase_contract'");self.disposition_sources(value,fail=True)
        self.sql("UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=NULL WHERE purpose='purchase_contract'")
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{policy}'");self.disposition_sources(value,fail=True)
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL WHERE id='{policy}'")
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'");self.disposition_sources(value,fail=True)

    def test_signature_disposition_sources_wait_rechecks_retention_revocation(self):
        row=self.prepare_disposition_storage();value=row['disposition_findings']
        policy=self.sql(f"SELECT retention_policy_id FROM acquisition_evidence_artifacts WHERE id='{row['artifact_id']}'")
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_evidence_policies WHERE id='{policy}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.disposition_sources,value,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%private.resolve_disposition_review_sources%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{policy}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                self.assertIn('Disposition source authority changed while waiting',future.result(timeout=5))
        finally:holder.communicate('\\q\n',timeout=5)

class DispositionSourceTests(DispositionSourceCases,DispositionStorageTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionSourceTests,[n for n in DispositionSourceCases.__dict__ if n.startswith('test_signature_disposition_sources_')]))
