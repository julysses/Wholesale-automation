"""Current execution authority must follow retained sources, never just saved status."""
import json
from acquisition_execution_review_tests import ExecutionReviewTests,EXEC_REVIEW,EXEC_POLICY,EXEC_WITHDRAW
from acquisition_contract_document_tests import DRAFT,DOCUMENT
from acquisition_contract_observation_tests import OBS
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101031709_acquisition_execution_review_state.sql'


class ExecutionStateCases:
    def execution_state(self,workspace=WORKSPACE,version=2,actor=ADMIN,fail=False,**kwargs):
        value=self.sql(f"SELECT public.execution_review_state('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_signature_execution_state_readonly_history_and_withdrawal(self):
        self.prepare_execution()
        self.assertEqual(self.execution_state()['status'],'not_reviewed')
        self.execution_review()
        before=self.sql('SELECT count(*) FROM audit_logs')
        for _ in range(2):
            state=self.execution_state();self.assertTrue(state['approval_current'])
            self.assertEqual(state['review_id'],EXEC_REVIEW);self.assertFalse(state['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        self.execution_review(self.execution_args(p_id=EXEC_WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False,p_findings=None))
        state=self.execution_state();self.assertEqual(state['status'],'withdrawn');self.assertFalse(state['approval_current'])
        self.assertIsNone(state['expires_at']);self.assertEqual(state['sequence'],2)

    def test_signature_execution_state_source_revocation_preserves_receipt_not_authority(self):
        self.prepare_execution();self.execution_review();self.assertTrue(self.execution_state()['approval_current'])
        self.revoke_document()
        state=self.execution_state();self.assertEqual(state['status'],'requires_review');self.assertIsNone(state['expires_at'])
        self.assertEqual(state['review_id'],EXEC_REVIEW);self.assertTrue(self.execution_review()['duplicate'])
        self.assertEqual(self.sql(f"SELECT status FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"),'approved')

    def test_signature_execution_state_scan_supersession_and_revoked_policy(self):
        self.prepare_execution();self.execution_review()
        self.record_contract_scan(self.signed_contract(request=EXEC_WITHDRAW))
        self.assertFalse(self.execution_state()['approval_current'])
        # New scan cannot silently replace the original saved identity.
        self.assertEqual(self.sql(f"SELECT verification_id FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"),OBS)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        self.assertFalse(self.execution_state()['approval_current'])

    def test_signature_execution_state_pause_reviewer_and_source_authority(self):
        self.prepare_execution();self.execution_review()
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertFalse(self.execution_state()['approval_current'])
        self.sql('UPDATE private.acquisition_activation SET enabled=true')
        self.assertTrue(self.execution_state()['approval_current'])
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.assertFalse(self.execution_state()['approval_current'])
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.execution_state(fail=True)

    def test_signature_execution_state_policy_revocation_independently_removes_authority(self):
        self.prepare_execution();self.execution_review()
        self.assertTrue(self.execution_state()['approval_current'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        self.assertFalse(self.execution_state()['approval_current'])
        self.assertTrue(self.execution_review()['duplicate'])

    def test_signature_execution_state_supplemental_source_revocation_removes_authority(self):
        # Reuse the real two-source capture journey; only the supplemental source is
        # revoked there. The main agreement and its scan remain current.
        self.test_signature_execution_write_additional_term_source_is_independently_verified()
        self.assertEqual(self.execution_state()['status'],'requires_review')
        self.assertFalse(self.execution_state()['approval_current'])

    def test_signature_execution_state_tenant_role_session_and_original_version(self):
        self.prepare_execution();self.execution_review()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}, {'workspace':WORKSPACE_B},{'version':3}):
            self.execution_state(fail=True,**kwargs)
        self.assertEqual(self.execution_state(version=1)['status'],'not_reviewed')


class ExecutionStateTests(ExecutionStateCases,ExecutionReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutionStateTests,test_names=[n for n in ExecutionStateCases.__dict__ if n.startswith('test_signature_execution_state_')]))
