"""Read-only lifecycle handoff reports independent current version/sequence."""
import json
from acquisition_contract_transition_tests import ContractTransitionTests
from acquisition_contract_document_tests import DRAFT, SECOND
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101024344_acquisition_transition_choices.sql'


class TransitionChoiceCases:
    def transition_choice(self,actor=ADMIN,workspace=WORKSPACE,version=2,fail=False,**kwargs):
        raw=self.sql(f"SELECT public.contract_transition_choice('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_transition_choice_current_release_read_only_and_recorded_state(self):
        self.assertEqual(self.transition_choice()['status'],'signature_review_required')
        self.signature()
        before=self.sql('SELECT (SELECT count(*) FROM audit_logs),(SELECT count(*) FROM acquisition_contract_transitions)')
        choice=self.transition_choice();self.transition_choice()
        self.assertEqual(choice['status'],'ready_for_human_review')
        self.assertEqual(choice['candidate']['expected_version'],2)
        self.assertEqual(choice['candidate']['expected_sequence'],0)
        self.assertFalse(choice['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT (SELECT count(*) FROM audit_logs),(SELECT count(*) FROM acquisition_contract_transitions)'))
        self.transition();saved=self.transition_choice()
        self.assertEqual(saved['current_status'],'pending_signature');self.assertEqual(saved['sequence'],1)
        self.assertIn(saved['status'],('awaiting_signature','execution_review_required'));self.assertIsNone(saved['candidate'])

    def test_signature_transition_choice_pause_revocation_and_version_change(self):
        self.signature();self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.transition_choice()['status'],'paused')
        self.sql('UPDATE private.acquisition_activation SET enabled=true');self.revoke_document()
        self.assertEqual(self.transition_choice()['status'],'signature_review_required')

    def test_signature_transition_choice_later_terms_do_not_reuse_old_choice(self):
        self.signature();self.save_terms(request=SECOND,version=2)
        old=self.transition_choice()
        self.assertEqual(old['status'],'version_changed');self.assertEqual(old['current_version'],3)
        self.assertEqual(old['contract_version'],2);self.assertIsNone(old['candidate'])
        self.assertEqual(self.transition_choice(version=3)['status'],'signature_review_required')

    def test_signature_transition_choice_workspace_session_and_role_isolation(self):
        self.member()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},
                       {'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.transition_choice(fail=True,**kwargs)


class TransitionChoiceTests(TransitionChoiceCases,ContractTransitionTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(TransitionChoiceTests,test_names=[n for n in TransitionChoiceCases.__dict__ if n.startswith('test_signature_transition_choice_')]))
