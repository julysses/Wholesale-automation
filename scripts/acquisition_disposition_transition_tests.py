"""Controlled disposition handoff preserves original authority and exact replay."""
import json,subprocess,select,time
from concurrent.futures import ThreadPoolExecutor
from acquisition_disposition_transition_storage_tests import DispositionTransitionStorageTests,TRANSITION
from acquisition_disposition_review_tests import REVIEW,WITHDRAW
from acquisition_disposition_storage_tests import POLICY
from acquisition_disposition_plan_tests import PLAN,SECOND
from acquisition_title_review_tests import TITLE_REVIEW,FINDINGS_POLICY
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,PG
MIGRATION=ROOT/'frontend/supabase/migrations/20261101085535_acquisition_disposition_contract_transition.sql'

class DispositionTransitionCases:
    def handoff_args(self,**changes):
        return self.transition_args(p_id=TRANSITION,p_expected_sequence=3,p_expected_status='title_review',p_target_status='disposition_review',
            p_reason='Enter disposition review with the exact reviewed contract interest and original findings.')|changes

    def prepare_handoff(self,assignment=False):
        self.prepare_disposition_review(assignment);self.disposition_review(self.disposition_review_args())

    def test_signature_disposition_transition_exact_concurrent_replay_and_current_stage(self):
        self.prepare_handoff(True)
        before=self.sql(f"SELECT (to_jsonb(d)-'acquisition_status'-'updated_at') FROM deals d WHERE id='{DRAFT}'")
        versions=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(lambda _:self.transition(self.handoff_args()),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in rows),1)
        self.assertTrue(all(r['recorded_status']=='disposition_review' and r['sequence']==4 and not r['execution_authorized'] for r in rows))
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'disposition_review')
        self.assertEqual(before,self.sql(f"SELECT (to_jsonb(d)-'acquisition_status'-'updated_at') FROM deals d WHERE id='{DRAFT}'"))
        self.assertEqual(versions,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        saved=json.loads(self.sql(f"SELECT to_jsonb(t) FROM acquisition_contract_transitions t WHERE id='{TRANSITION}'"))
        self.assertEqual(saved['disposition_review_id'],REVIEW);self.assertEqual(saved['disposition_plan_id'],PLAN)
        self.assertEqual(saved['disposition_title_review_id'],TITLE_REVIEW);self.assertEqual(saved['execution_review_id'],EXEC_REVIEW)
        self.assertTrue(self.disposition_state()['approval_current'])
        self.assertEqual(self.sql(f"SELECT private.title_review_current('{TITLE_REVIEW}',clock_timestamp()),private.execution_review_current('{EXEC_REVIEW}',clock_timestamp())"),'t|t')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{TRANSITION}'"),'1')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.transition(self.handoff_args())['duplicate']);self.assertFalse(self.disposition_state()['approval_current'])
        self.transition(self.handoff_args(p_reason='Changed reason must not replace the original reviewed handoff.'),fail=True)

    def test_signature_disposition_transition_missing_held_and_replaced_approval(self):
        self.prepare_disposition_review();self.transition(self.handoff_args(),fail=True)
        self.disposition_review(self.disposition_review_args(p_status='requires_resolution',p_expires=None));self.transition(self.handoff_args(),fail=True)
        self.disposition_review(self.disposition_review_args(p_id=WITHDRAW,p_expected_sequence=1))
        self.plan(self.plan_args(p_id=SECOND,p_expected_sequence=1,p_exit_type='wholesale_assignment'))
        self.transition(self.handoff_args(),fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')

    def test_signature_disposition_transition_scope_no_raw_or_skip_or_execution(self):
        self.prepare_handoff()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):self.transition(self.handoff_args(),fail=True,**kwargs)
        for patch in ({'p_workspace':WORKSPACE_B},{'p_expected_version':1},{'p_expected_sequence':2},{'p_expected_status':'executed'},{'p_target_status':'closed'},{'p_target_status':'assigned_or_direct_close'}):self.transition(self.handoff_args(**patch),fail=True)
        self.sql(f"UPDATE deals SET acquisition_status='disposition_review' WHERE id='{DRAFT}'",fail=True)
        self.sql(f"SELECT private.lock_disposition_handoff_authority('{WORKSPACE}','{DRAFT}',2)",user=ADMIN,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')

    def test_signature_disposition_transition_original_withdrawal_after_handoff(self):
        self.prepare_handoff();self.transition(self.handoff_args())
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.disposition_review(self.disposition_review_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_original_review=REVIEW,p_personally_reviewed=False,p_expires=None,p_findings=None))
        self.assertEqual(self.disposition_state()['status'],'withdrawn');self.assertTrue(self.transition(self.handoff_args())['duplicate'])
        self.assertEqual(self.sql(f"SELECT disposition_review_id FROM acquisition_contract_transitions WHERE id='{TRANSITION}'"),REVIEW)

    def handoff_wait(self,table,key,policy):
        self.prepare_handoff();args=self.handoff_args()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.{table} WHERE {key}='{policy}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.transition,args,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_contract_transition%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.{table} SET revoked_at=clock_timestamp() WHERE {key}='{policy}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
        finally:holder.communicate('\\q\n',timeout=5)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'title_review')

    def test_signature_disposition_transition_wait_scope_revocation(self):self.handoff_wait('acquisition_disposition_policy_scopes','policy_id',POLICY)
    def test_signature_disposition_transition_wait_title_revocation(self):self.handoff_wait('acquisition_contract_review_policies','id',FINDINGS_POLICY)
    def test_signature_disposition_transition_wait_deadline_revocation(self):self.handoff_wait('acquisition_contract_review_policies','id',DEADLINE_POLICY)
    def test_signature_disposition_transition_wait_scanner_scope_revocation(self):self.handoff_wait('acquisition_contract_verification_key_scopes','purpose','purchase_contract')

class DispositionTransitionTests(DispositionTransitionCases,DispositionTransitionStorageTests):
    supports_disposition_handoff=True
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionTransitionTests,[n for n in DispositionTransitionCases.__dict__ if n.startswith('test_signature_disposition_transition_')]))
