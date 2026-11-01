"""Entering title review retains exact execution authority without claiming title clearance."""
from concurrent.futures import ThreadPoolExecutor
from acquisition_execution_deadline_tests import ExecutionDeadlineTests
from acquisition_executed_transition_tests import ExecutedTransitionCases
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_POLICY
from acquisition_contract_document_tests import DRAFT,DOCUMENT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101052408_acquisition_title_review_transition.sql'
TITLE='af920000-0000-4000-8000-000000000001'

class TitleTransitionCases:
    def title_args(self,**changes):
        return self.transition_args(p_id=TITLE,p_expected_sequence=2,p_expected_status='executed',p_target_status='title_review',
            p_reason='Begin review of the title evidence without claiming clear title or ownership.')|changes

    def prepare_title(self):
        value=self.prepare_execution_bindings();self.prepare_execution()
        self.execution_review(self.execution_args(p_findings=value))
        self.transition(ExecutedTransitionCases.executed_args(self))

    def test_signature_title_transition_exact_retry_preserves_terms_and_legacy_stage(self):
        self.prepare_title();before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(lambda _:self.transition(self.title_args()),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in rows),1)
        self.assertTrue(all(row['recorded_status']=='title_review' and row['sequence']==3 and not row['execution_authorized'] for row in rows))
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version,stage,buyer_id IS NULL FROM deals WHERE id='{DRAFT}'"),'title_review|2|offer_made|t')
        self.assertEqual(self.sql(f"SELECT execution_review_id FROM acquisition_contract_transitions WHERE id='{TITLE}'"),EXEC_REVIEW)
        self.assertEqual(self.sql(f"SELECT private.execution_review_current('{EXEC_REVIEW}',clock_timestamp())"),'t')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_transition' AND entity_id='{TITLE}'"),'1')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.transition(self.title_args())['duplicate'])
        self.assertEqual(self.sql(f"SELECT public.execution_review_candidate('{WORKSPACE}','{DRAFT}',2,'{DOCUMENT}')->'withdrawal'->>'review_id'",user=ADMIN),EXEC_REVIEW)
        self.transition(self.title_args(p_reason='Changed explanation cannot replace the historical review handoff.'),fail=True)

    def test_signature_title_transition_requires_current_exact_execution(self):
        self.prepare_title()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.transition(self.title_args(),fail=True)
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'executed')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'2')

    def test_signature_title_transition_scope_and_raw_changes_denied(self):
        self.prepare_title()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'}):
            self.transition(self.title_args(),fail=True,**kwargs)
        self.transition(self.title_args(p_workspace=WORKSPACE_B),fail=True)
        self.transition(self.title_args(p_expected_version=1),fail=True)
        self.transition(self.title_args(p_expected_sequence=1),fail=True)
        self.sql(f"UPDATE deals SET acquisition_status='title_review' WHERE id='{DRAFT}'",fail=True)
        self.sql(f"DO $$ BEGIN UPDATE deals SET acquisition_status='title_review' WHERE id='{DRAFT}'; EXCEPTION WHEN insufficient_privilege THEN NULL; END $$",user=ADMIN)
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'executed')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'2')

    def test_signature_title_transition_wait_rechecks_deadline_authority(self):
        self.deadline_wait(title=True)

    def test_signature_title_transition_does_not_skip_review_or_allow_disposition(self):
        value=self.prepare_execution_bindings();self.prepare_execution();self.execution_review(self.execution_args(p_findings=value))
        self.transition(self.title_args(p_expected_sequence=1,p_expected_status='pending_signature'),fail=True)
        self.transition(ExecutedTransitionCases.executed_args(self));self.transition(self.title_args())
        self.transition(self.title_args(p_id='af920000-0000-4000-8000-000000000002',p_expected_sequence=3,
            p_expected_status='title_review',p_target_status='disposition_review'),fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')

class TitleTransitionTests(TitleTransitionCases,ExecutionDeadlineTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(TitleTransitionTests,test_names=[n for n in TitleTransitionCases.__dict__ if n.startswith('test_signature_title_transition_')]))
