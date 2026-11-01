"""Exact interpretation binding authority preserving original contract terms."""
import json
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from acquisition_deadline_choice_tests import DeadlineChoiceTests
from acquisition_deadline_storage_tests import DeadlineStorageCases
from acquisition_deadline_review_tests import DEADLINE_REVIEW,DEADLINE_POLICY,SECOND_REVIEW,WITHDRAW
from acquisition_execution_review_tests import ExecutionReviewCases, EXEC_REVIEW
from acquisition_executed_transition_tests import ExecutedTransitionCases
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from acquisition_contract_document_tests import DRAFT, DOCUMENT
from test_acquisition_workspace import ROOT,PG,main,ADMIN,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101045444_acquisition_execution_deadline_binding.sql'


class ExecutionDeadlineCases:
    def binding_prepared_terms(self):
        value=ExecutionReviewCases.execution_prepared_terms(self);now=datetime.now(timezone.utc)
        value['effective']={'precision':'date','calendar_date':(now-timedelta(days=1)).date().isoformat()}
        days=1 if self._testMethodName.endswith('invalid_ordering') else 20
        value['closing_deadline']={'precision':'date','calendar_date':(now+timedelta(days=days)).date().isoformat()}
        return value

    def binding_deadline_proposal(self,term='closing_deadline'):
        value=DeadlineStorageCases.deadline_proposal(self)
        prepared=json.loads(self.sql('SELECT terms FROM acquisition_contract_versions WHERE version=2'))
        day=prepared[term]['calendar_date'];clock='00:00:00' if term=='effective' else '17:00:00'
        value.update(term=term,calendar_date=day,local_time=clock,time_zone='UTC',resolved_instant=day+'T'+clock+'+00:00')
        value['source']['term']=term
        return value

    def prepare_execution_bindings(self):
        self.prepare_deadline_review();self.deadline_review()
        self.deadline_review(self.deadline_args(p_id=SECOND_REVIEW,p_expected_sequence=1,p_term='effective',p_resolution=self.deadline_proposal('effective')))
        value=self.execution_findings()
        value['deadline_reviews']=[{'term':'closing_deadline','review_id':DEADLINE_REVIEW},{'term':'effective','review_id':SECOND_REVIEW}]
        return value

    def bindings_match(self,value,workspace=WORKSPACE,contract=DRAFT,version=2):
        return self.sql(f"SELECT private.execution_findings_match('{workspace}','{contract}',{version},{literal(json.dumps(value))}::jsonb,(SELECT terms FROM acquisition_contract_versions WHERE version=2),clock_timestamp())")

    def test_signature_execution_deadline_exact_binding_preserves_dates_and_records_execution(self):
        value=self.prepare_execution_bindings()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        audit=self.sql('SELECT count(*) FROM audit_logs')
        self.assertEqual(self.bindings_match(value),'t')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(audit,self.sql('SELECT count(*) FROM audit_logs'))
        self.assertEqual(value['terms']['effective']['precision'],'date');self.assertNotIn('instant',value['terms']['effective'])
        self.prepare_execution()
        args=self.execution_args(p_findings=value)
        self.assertFalse(self.execution_review(args)['duplicate'])
        self.assertTrue(self.execution_review(args)['duplicate'])
        self.assertEqual(json.loads(self.sql(f"SELECT execution_findings FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'")),value)
        self.assertEqual(self.sql(f"SELECT private.execution_review_current('{EXEC_REVIEW}',clock_timestamp())"),'t')
        transition=ExecutedTransitionCases.executed_args(self)
        self.assertEqual(self.transition(transition)['recorded_status'],'executed')
        self.assertTrue(self.transition(transition)['duplicate'])
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.sql(f"SELECT private.execution_findings_match('{WORKSPACE}','{DRAFT}',2,'{{}}','{{}}',clock_timestamp())",user=ADMIN,fail=True)

    def test_signature_execution_deadline_missing_mixed_and_changed_bindings_hold(self):
        value=self.prepare_execution_bindings()
        for change in (None,[],[value['deadline_reviews'][0]],
                       [value['deadline_reviews'][0],value['deadline_reviews'][0]],
                       [{'term':'closing_deadline','review_id':SECOND_REVIEW},{'term':'effective','review_id':DEADLINE_REVIEW}]):
            bad=deepcopy(value)
            if change is None:bad.pop('deadline_reviews')
            else:bad['deadline_reviews']=change
            self.assertEqual(self.bindings_match(bad),'f')
        changed=deepcopy(value);changed['terms']['closing_deadline']['calendar_date']='2099-01-01'
        self.assertEqual(self.bindings_match(changed),'f')
        self.assertEqual(self.bindings_match(value,workspace=WORKSPACE_B),'f')
        self.assertEqual(self.bindings_match(value,contract=WITHDRAW),'f')
        self.assertEqual(self.bindings_match(value,version=1),'f')

    def test_signature_execution_deadline_replacement_and_withdrawal_invalidate_exact_ids(self):
        value=self.prepare_execution_bindings();self.assertEqual(self.bindings_match(value),'t')
        self.deadline_review(self.deadline_args(p_id=WITHDRAW,p_expected_sequence=2))
        self.assertEqual(self.bindings_match(value),'f')
        updated=deepcopy(value);updated['deadline_reviews'][0]['review_id']=WITHDRAW
        self.assertEqual(self.bindings_match(updated),'t')
        self.deadline_review(self.deadline_args(p_id='af870000-0000-4000-8000-000000000001',p_expected_sequence=3,
            p_status='withdrawn',p_original=WITHDRAW,p_resolution=None,p_personally_reviewed=False,p_expires=None))
        self.assertEqual(self.bindings_match(updated),'f')

    def test_signature_execution_deadline_revoked_policy_keeps_receipt_not_comparison_authority(self):
        value=self.prepare_execution_bindings();self.assertEqual(self.bindings_match(value),'t')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.assertEqual(self.bindings_match(value),'f')
        self.assertTrue(self.deadline_review()['duplicate'])

    def test_signature_execution_deadline_rejects_invalid_ordering(self):
        value=self.prepare_execution_bindings()
        self.assertTrue(self.deadline_state()['approval_current'])
        self.assertTrue(self.deadline_state('effective')['approval_current'])
        self.assertEqual(self.bindings_match(value),'f')

    def test_signature_execution_deadline_withdrawal_blocks_transition_preserves_retry(self):
        value=self.prepare_execution_bindings();self.prepare_execution()
        args=self.execution_args(p_findings=value);self.execution_review(args)
        self.deadline_review(self.deadline_args(p_id=WITHDRAW,p_expected_sequence=2,
            p_status='withdrawn',p_original=DEADLINE_REVIEW,p_resolution=None,p_personally_reviewed=False,p_expires=None))
        self.assertEqual(self.sql(f"SELECT private.execution_review_current('{EXEC_REVIEW}',clock_timestamp())"),'f')
        self.transition(ExecutedTransitionCases.executed_args(self),fail=True)
        self.assertTrue(self.execution_review(args)['duplicate'])
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'pending_signature')

    def test_signature_execution_deadline_expiry_caps_execution(self):
        value=self.prepare_execution_bindings();self.prepare_execution()
        later=(datetime.fromisoformat(self.signature_expiry)+timedelta(seconds=1)).isoformat()
        self.execution_review(self.execution_args(p_findings=value,p_expires=later),fail=True)
        missing=deepcopy(value);missing.pop('deadline_reviews')
        self.execution_review(self.execution_args(p_findings=missing),fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='executed_contract'"),'0')

    def deadline_wait(self,writing=False,title=False):
        value=self.prepare_execution_bindings();self.prepare_execution()
        if not writing:self.execution_review(self.execution_args(p_findings=value))
        action=self.execution_review if writing else self.transition
        args=self.execution_args(p_findings=value) if writing else ExecutedTransitionCases.executed_args(self)
        if title:
            self.transition(args)
            args=self.title_args()
        function='record_execution_review' if writing else 'record_contract_transition'
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id='{DEADLINE_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            limit=time.monotonic()+5;locked=False
            while time.monotonic()<limit:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(action,args,fail=True)
                try:
                    limit=time.monotonic()+5;waiting='0'
                    while time.monotonic()<limit:
                        waiting=self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.{function}%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'2' if title else '1')
            if title:self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'executed')
            if writing:self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='executed_contract'"),'0')
        finally:holder.communicate('\\q\n',timeout=5)

    def test_signature_execution_deadline_wait_rechecks_revoked_policy(self):
        self.deadline_wait()

    def test_signature_execution_deadline_writer_wait_rechecks_revoked_policy(self):
        self.deadline_wait(writing=True)

    def test_signature_execution_deadline_retains_independent_original_sources(self):
        value=self.prepare_execution_bindings();self.prepare_execution()
        document='af880000-0000-4000-8000-000000000001';scan='af880000-0000-4000-8000-000000000002'
        self.document(identity=document,version=2)
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{document}')",user=ADMIN))
        self.record_contract_scan(self.signed_contract(request=scan,artifact_id=document,contract_version=2,
            retain_until=state['retain_until'],checked_at=state['checked_at'],registry_checked_at=state['checked_at'],scan_checked_at=state['checked_at']))
        for source in value['terms']['sources']:source.update(artifact_id=document,artifact_version=2)
        args=self.execution_args(p_findings=value,p_artifact=document,p_verification=scan)
        self.execution_review(args)
        sources=json.loads(self.sql(f"SELECT execution_sources FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"))
        self.assertEqual({row['artifact_id'] for row in sources},{DOCUMENT,document})
        self.assertEqual(self.sql(f"SELECT private.execution_review_current('{EXEC_REVIEW}',clock_timestamp())"),'t')
        self.revoke_document()
        self.assertEqual(self.sql(f"SELECT private.execution_review_current('{EXEC_REVIEW}',clock_timestamp())"),'f')
        self.transition(ExecutedTransitionCases.executed_args(self),fail=True)
        self.assertTrue(self.execution_review(args)['duplicate'])


class ExecutionDeadlineTests(ExecutionDeadlineCases,DeadlineChoiceTests):
    def setUp(self):
        self.deadline_prepared_terms=self.binding_prepared_terms
        self.deadline_proposal=self.binding_deadline_proposal
        super().setUp();self.sql(MIGRATION.read_text());self.sql((ROOT/'frontend/supabase/migrations/20261101050425_acquisition_execution_deadline_authority.sql').read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutionDeadlineTests,test_names=[n for n in ExecutionDeadlineCases.__dict__ if n.startswith('test_signature_execution_deadline_')]))
