"""Executed status requires current sourced human review; exact history survives retries."""
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from acquisition_execution_choice_tests import ExecutionChoiceTests
from acquisition_execution_review_tests import EXEC_REVIEW, EXEC_POLICY, EXEC_WITHDRAW
from acquisition_contract_document_tests import DRAFT, DOCUMENT
from test_acquisition_workspace import ROOT, PG, main, ADMIN, OTHER, OPERATOR, WORKSPACE, WORKSPACE_B

MIGRATION=ROOT/'frontend/supabase/migrations/20261101034450_acquisition_executed_contract_transition.sql'
EXEC_TRANSITION='af800000-0000-4000-8000-000000000001'

class ExecutedTransitionCases:
    def executed_args(self, **changes):
        return self.transition_args(p_id=EXEC_TRANSITION,p_expected_sequence=1,p_expected_status='pending_signature',
            p_target_status='executed',p_reason='Record the independently reviewed returned agreement as executed.') | changes

    def test_signature_executed_transition_exact_parallel_retry_preserves_history(self):
        self.prepare_execution();self.execution_review()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        args=self.executed_args()
        with ThreadPoolExecutor(max_workers=3) as pool:
            receipts=list(pool.map(lambda _:self.transition(args),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in receipts),1)
        self.assertTrue(all(r['sequence']==2 and r['recorded_status']=='executed' and not r['execution_authorized'] for r in receipts))
        self.assertEqual(self.sql(f"SELECT execution_review_id,signature_review_id IS NULL FROM acquisition_contract_transitions WHERE id='{EXEC_TRANSITION}'"),EXEC_REVIEW+'|t')
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version,stage,contract_price IS NULL FROM deals WHERE id='{DRAFT}'"),'executed|2|offer_made|t')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_transition' AND entity_id='{EXEC_TRANSITION}'"),'1')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.transition(args)['duplicate'])
        self.transition(args|{'p_reason':'Changed request bytes must not replace historical execution.'},fail=True)
        self.transition(args|{'p_id':EXEC_WITHDRAW,'p_expected_sequence':2},fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'2')

    def test_signature_executed_transition_requires_review_and_current_source(self):
        self.prepare_execution();self.transition(self.executed_args(),fail=True)
        self.execution_review()
        self.sql(f"SELECT public.revoke_contract_document('{EXEC_WITHDRAW}','{WORKSPACE}','{DRAFT}',1,'{DOCUMENT}','Original returned agreement is no longer current.')",user=ADMIN)
        self.transition(self.executed_args(),fail=True)
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'pending_signature')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'1')

    def test_signature_executed_transition_policy_withdrawal_and_scope(self):
        self.prepare_execution();self.execution_review()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.transition(self.executed_args(),fail=True,**kwargs)
        self.transition(self.executed_args(p_workspace=WORKSPACE_B),fail=True)
        self.transition(self.executed_args(p_expected_version=1),fail=True)
        self.transition(self.executed_args(p_expected_sequence=0),fail=True)
        self.sql(f"DO $$ BEGIN UPDATE deals SET acquisition_status='executed' WHERE id='{DRAFT}'; EXCEPTION WHEN insufficient_privilege THEN NULL; END $$",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'pending_signature')
        self.sql(f"UPDATE deals SET acquisition_status='executed' WHERE id='{DRAFT}'",fail=True)
        self.sql('UPDATE acquisition_contract_transitions SET reason=\'Cannot replace immutable status history\'',fail=True)
        self.execution_review(self.execution_args(p_id=EXEC_WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False,p_findings=None))
        self.transition(self.executed_args(),fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions',user=OTHER),'0')

    def test_signature_executed_transition_wait_rechecks_revoked_policy(self):
        self.prepare_execution();self.execution_review()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id='{EXEC_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.transition,self.executed_args(),fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_contract_transition%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'1')
            self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'pending_signature')
        finally:holder.communicate('\\q\n',timeout=5)


class ExecutedTransitionTests(ExecutedTransitionCases,ExecutionChoiceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutedTransitionTests,test_names=[n for n in ExecutedTransitionCases.__dict__ if n.startswith('test_signature_executed_transition_')]))
