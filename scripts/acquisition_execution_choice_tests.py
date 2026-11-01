"""Read-only execution choices preserve exact source and independent withdrawal."""
import json
from acquisition_execution_state_tests import ExecutionStateTests
from acquisition_execution_review_tests import EXEC_REVIEW,EXEC_POLICY
from acquisition_contract_document_tests import DRAFT,DOCUMENT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101032437_acquisition_execution_review_choices.sql'
NEW_DOC='af790000-0000-4000-8000-000000000001'


class ExecutionChoiceCases:
    def execution_choice(self,artifact=DOCUMENT,workspace=WORKSPACE,version=2,actor=ADMIN,fail=False,**kwargs):
        value=self.sql(f"SELECT public.execution_review_candidate('{workspace}','{DRAFT}',{version},'{artifact}')",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_signature_execution_choice_exact_source_and_readonly_prepared_terms(self):
        self.prepare_execution()
        before=self.sql('SELECT count(*) FROM audit_logs')
        for _ in range(2):
            value=self.execution_choice();self.assertEqual(value['status'],'ready_for_human_review')
            self.assertEqual(value['candidate']['artifact_id'],DOCUMENT)
            self.assertEqual(value['candidate']['source_version'],1)
            self.assertEqual(value['candidate']['policy_id'],EXEC_POLICY)
            self.assertEqual(value['candidate']['expected_sequence'],0)
            self.assertEqual(value['prepared_terms'],self.execution_findings()['terms'])
            self.assertFalse(value['execution_authorized']);self.assertIsNone(value['withdrawal'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='executed_contract'"),'0')

    def test_signature_execution_choice_original_withdrawal_survives_new_selection_and_pause(self):
        self.prepare_execution();self.execution_review()
        self.document(identity=NEW_DOC,version=2)
        choice=self.execution_choice(artifact=NEW_DOC)
        self.assertEqual(choice['status'],'evidence_review_required');self.assertIsNone(choice['candidate'])
        self.assertEqual(choice['withdrawal']['review_id'],EXEC_REVIEW)
        self.assertEqual(choice['withdrawal']['artifact_id'],DOCUMENT)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        choice=self.execution_choice(artifact=NEW_DOC)
        self.assertEqual(choice['status'],'paused');self.assertEqual(choice['withdrawal']['artifact_id'],DOCUMENT)
        self.assertEqual(choice['current_review']['status'],'requires_review')

    def test_signature_execution_choice_policy_and_source_holds(self):
        self.prepare_execution()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        value=self.execution_choice();self.assertEqual(value['status'],'reviewer_policy_required');self.assertIsNone(value['candidate'])
        self.assertIsNone(value['withdrawal'])

    def test_signature_execution_choice_scope_session_version_and_reviewer_isolation(self):
        self.prepare_execution()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},
                       {'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.execution_choice(fail=True,**kwargs)
        retained=self.execution_choice(version=1)
        self.assertEqual(retained['status'],'contract_unavailable');self.assertIsNone(retained['candidate'])


class ExecutionChoiceTests(ExecutionChoiceCases,ExecutionStateTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutionChoiceTests,test_names=[n for n in ExecutionChoiceCases.__dict__ if n.startswith('test_signature_execution_choice_')]))
