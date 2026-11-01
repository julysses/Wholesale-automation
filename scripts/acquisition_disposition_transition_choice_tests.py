"""Fresh non-executing handoff choices derive the original disposition chain."""
from acquisition_disposition_transition_tests import DispositionTransitionTests
from acquisition_disposition_review_tests import REVIEW
from acquisition_disposition_storage_tests import POLICY
from acquisition_disposition_plan_tests import PLAN,SECOND
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101090156_acquisition_disposition_transition_choices.sql'

class DispositionTransitionChoiceCases:
    def test_signature_disposition_handoff_choice_exact_roots_no_mutation_and_completed_state(self):
        self.prepare_handoff(True);before=self.sql('SELECT count(*) FROM audit_logs')
        choice=self.title_choice();self.assertEqual(choice['status'],'ready_for_human_review');c=choice['candidate']
        self.assertEqual(c['target_status'],'disposition_review');self.assertEqual(c['expected_status'],'title_review');self.assertEqual(c['expected_sequence'],3)
        self.assertEqual(c['disposition_review_id'],REVIEW);self.assertEqual(c['plan_id'],PLAN);self.assertEqual(c['exit_type'],'wholesale_assignment')
        self.assertEqual(c['title_review_id'],TITLE_REVIEW);self.assertEqual(c['execution_review_id'],EXEC_REVIEW)
        self.assertEqual(c['expires_at'],self.disposition_state()['expires_at']);self.assertFalse(choice['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'));self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.transition(self.handoff_args());done=self.title_choice();self.assertEqual(done['status'],'disposition_review_started');self.assertEqual(done['current_status'],'disposition_review');self.assertEqual(done['sequence'],4);self.assertIsNone(done['candidate'])
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.assertEqual(self.title_choice()['status'],'paused')

    def test_signature_disposition_handoff_choice_requires_review_and_current_dependencies(self):
        self.prepare_disposition_review();self.assertEqual(self.title_choice()['status'],'disposition_review_required')
        self.disposition_review(self.disposition_review_args(p_status='requires_resolution',p_expires=None));self.assertIsNone(self.title_choice()['candidate'])
        self.disposition_review(self.disposition_review_args(p_id=SECOND,p_expected_sequence=1));self.assertEqual(self.title_choice()['candidate']['disposition_review_id'],SECOND)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        held=self.title_choice();self.assertEqual(held['status'],'disposition_review_required');self.assertIsNone(held['candidate'])
        self.transition(self.handoff_args(),fail=True)

    def test_signature_disposition_handoff_choice_scope_version_and_no_policy_provisioning(self):
        self.prepare_handoff();before=self.sql('SELECT count(*) FROM private.acquisition_disposition_policy_scopes')
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):self.title_choice(fail=True,**kwargs)
        old=self.title_choice(version=1);self.assertEqual(old['status'],'version_changed');self.assertIsNone(old['candidate'])
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET revoked_at=clock_timestamp() WHERE policy_id='{POLICY}'")
        self.assertIsNone(self.title_choice()['candidate']);self.assertEqual(before,self.sql('SELECT count(*) FROM private.acquisition_disposition_policy_scopes'))

class DispositionTransitionChoiceTests(DispositionTransitionChoiceCases,DispositionTransitionTests):
    supports_disposition_choice=True
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionTransitionChoiceTests,[n for n in DispositionTransitionChoiceCases.__dict__ if n.startswith('test_signature_disposition_handoff_choice_')]))
