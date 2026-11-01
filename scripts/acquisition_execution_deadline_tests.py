"""Exact interpretation binding comparison without mutating or activating execution."""
import json
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from acquisition_deadline_choice_tests import DeadlineChoiceTests
from acquisition_deadline_storage_tests import DeadlineStorageCases
from acquisition_deadline_review_tests import DEADLINE_REVIEW,DEADLINE_POLICY,SECOND_REVIEW,WITHDRAW
from acquisition_execution_review_tests import ExecutionReviewCases
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,WORKSPACE,WORKSPACE_B,literal
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

    def test_signature_execution_deadline_exact_binding_preserves_dates_and_old_writer_hold(self):
        value=self.prepare_execution_bindings()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        audit=self.sql('SELECT count(*) FROM audit_logs')
        self.assertEqual(self.bindings_match(value),'t')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(audit,self.sql('SELECT count(*) FROM audit_logs'))
        self.assertEqual(value['terms']['effective']['precision'],'date');self.assertNotIn('instant',value['terms']['effective'])
        # Binding support is not activated until all writer/transition locks exist.
        self.prepare_execution()
        rejected=self.execution_review(self.execution_args(p_findings=value),fail=True)
        self.assertIn('Current matching complete execution terms required',rejected)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='executed_contract'"),'0')
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


class ExecutionDeadlineTests(ExecutionDeadlineCases,DeadlineChoiceTests):
    def setUp(self):
        self.deadline_prepared_terms=self.binding_prepared_terms
        self.deadline_proposal=self.binding_deadline_proposal
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutionDeadlineTests,test_names=[n for n in ExecutionDeadlineCases.__dict__ if n.startswith('test_signature_execution_deadline_')]))
