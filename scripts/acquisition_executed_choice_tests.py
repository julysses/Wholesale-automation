"""Read-only exact executed handoff; no authority from a stale discovery result."""
import json
from acquisition_executed_transition_tests import ExecutedTransitionTests
from acquisition_execution_review_tests import EXEC_REVIEW,EXEC_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B

MIGRATION=ROOT/'frontend/supabase/migrations/20261101035403_acquisition_executed_transition_choices.sql'

class ExecutedChoiceCases:
    def executed_choice(self,actor=ADMIN,workspace=WORKSPACE,version=2,fail=False,**kwargs):
        raw=self.sql(f"SELECT public.contract_transition_choice('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_executed_choice_requires_fresh_review_and_removes_completed_action(self):
        self.prepare_execution()
        held=self.executed_choice();self.assertEqual(held['status'],'execution_review_required');self.assertIsNone(held['candidate'])
        self.execution_review()
        before=self.sql('SELECT count(*) FROM audit_logs')
        ready=self.executed_choice();self.assertEqual(ready['status'],'ready_for_human_review')
        self.assertEqual(ready['candidate']['execution_review_id'],EXEC_REVIEW)
        self.assertEqual(ready['candidate']['expected_sequence'],1)
        self.assertEqual(ready['candidate']['expected_status'],'pending_signature')
        self.assertNotIn('signature_review_id',ready['candidate']);self.assertFalse(ready['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        self.transition(self.executed_args())
        done=self.executed_choice();self.assertEqual(done['status'],'execution_recorded');self.assertEqual(done['sequence'],2);self.assertIsNone(done['candidate'])

    def test_signature_executed_choice_revocation_and_pause_remove_ready_state(self):
        self.prepare_execution();self.execution_review()
        self.assertEqual(self.executed_choice()['status'],'ready_for_human_review')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        self.assertEqual(self.executed_choice()['status'],'execution_review_required')
        self.transition(self.executed_args(),fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.executed_choice()['status'],'paused')
        self.assertIsNone(self.executed_choice()['candidate'])

    def test_signature_executed_choice_scope_and_retained_version(self):
        self.prepare_execution();self.execution_review()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.executed_choice(fail=True,**kwargs)
        prior=self.executed_choice(version=1);self.assertEqual(prior['status'],'version_changed');self.assertIsNone(prior['candidate'])

class ExecutedChoiceTests(ExecutedChoiceCases,ExecutedTransitionTests):
    def setUp(self):
        super().setUp()
        self.sql((ROOT/'frontend/supabase/migrations/20261101024344_acquisition_transition_choices.sql').read_text())
        self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutedChoiceTests,test_names=[n for n in ExecutedChoiceCases.__dict__ if n.startswith('test_signature_executed_choice_')]))
