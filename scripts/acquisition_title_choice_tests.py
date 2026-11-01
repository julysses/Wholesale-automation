"""Read-only title entry uses the original still-current execution review."""
import json
from acquisition_title_transition_tests import TitleTransitionTests
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101053450_acquisition_title_review_choices.sql'

class TitleChoiceCases:
    def title_choice(self,actor=ADMIN,workspace=WORKSPACE,version=2,fail=False,**kwargs):
        raw=self.sql(f"SELECT public.contract_transition_choice('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_title_choice_exact_review_no_mutation_and_completed_hold(self):
        self.prepare_title();before=self.sql('SELECT count(*) FROM audit_logs')
        for _ in range(2):
            choice=self.title_choice()
            self.assertEqual(choice['status'],'ready_for_human_review')
            self.assertEqual(choice['candidate']['expected_status'],'executed')
            self.assertEqual(choice['candidate']['target_status'],'title_review')
            self.assertEqual(choice['candidate']['expected_sequence'],2)
            self.assertEqual(choice['candidate']['execution_review_id'],EXEC_REVIEW)
            self.assertFalse(choice['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'2')
        self.transition(self.title_args())
        done=self.title_choice();self.assertEqual(done['status'],'title_review_started')
        self.assertEqual(done['sequence'],3);self.assertIsNone(done['candidate'])

    def test_signature_title_choice_revocation_and_pause_remove_action(self):
        self.prepare_title();self.assertIsNotNone(self.title_choice()['candidate'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        held=self.title_choice();self.assertEqual(held['status'],'title_review_required');self.assertIsNone(held['candidate'])
        self.transition(self.title_args(),fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.title_choice()['status'],'paused');self.assertIsNone(self.title_choice()['candidate'])

    def test_signature_title_choice_scope_and_retained_version(self):
        self.prepare_title()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.title_choice(fail=True,**kwargs)
        prior=self.title_choice(version=1);self.assertEqual(prior['status'],'version_changed');self.assertIsNone(prior['candidate'])

class TitleChoiceTests(TitleChoiceCases,TitleTransitionTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(TitleChoiceTests,test_names=[n for n in TitleChoiceCases.__dict__ if n.startswith('test_signature_title_choice_')]))
