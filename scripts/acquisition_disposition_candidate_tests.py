"""Current disposition choices preserve independent original withdrawal."""
import json
from acquisition_disposition_review_tests import DispositionReviewTests,REVIEW,WITHDRAW
from acquisition_disposition_storage_tests import POLICY
from acquisition_disposition_plan_tests import PLAN,SECOND
from acquisition_title_storage_tests import FINDINGS_POLICY,TITLE_FILE
from acquisition_execution_review_tests import EXEC_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101082423_acquisition_disposition_review_choices.sql'

class DispositionCandidateCases:
    def disposition_candidate(self,workspace=WORKSPACE,version=2,actor=ADMIN,fail=False,**kwargs):
        result=self.sql(f"SELECT public.disposition_review_candidate('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_signature_disposition_candidate_exact_roots_read_only_and_expiry(self):
        row=self.prepare_disposition_review(True);before=self.sql('SELECT count(*) FROM audit_logs')
        choice=self.disposition_candidate();self.assertEqual(choice['status'],'ready_for_human_review')
        candidate=choice['candidate'];self.assertEqual(candidate['plan_id'],PLAN);self.assertEqual(candidate['exit_type'],'wholesale_assignment')
        self.assertEqual(candidate['executed_source']['artifact_id'],row['artifact_id']);self.assertEqual(candidate['executed_source']['source_version'],1)
        self.assertEqual(candidate['legal_source'],candidate['executed_source']);self.assertEqual(candidate['title_review_id'],row['disposition_title_review_id'])
        self.assertEqual({k:v for k,v in candidate.items() if k!='max_expires_at'},choice['resolution'])
        self.assertEqual(candidate['expected_sequence'],0);self.assertFalse(choice['execution_authorized']);self.assertIsNone(choice['withdrawal'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        args=self.disposition_review_args(p_expires=candidate['max_expires_at']);self.disposition_review(args)
        self.assertTrue(self.disposition_state()['approval_current'])

    def test_signature_disposition_candidate_resolution_holds_without_approval(self):
        self.prepare_disposition_review(True,title_held=True)
        choice=self.disposition_candidate();self.assertEqual(choice['status'],'title_review_required');self.assertIsNone(choice['candidate']);self.assertIsNotNone(choice['resolution'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        choice=self.disposition_candidate();self.assertEqual(choice['status'],'execution_review_required');self.assertIsNotNone(choice['resolution'])
        self.disposition_review(self.disposition_review_args(p_status='requires_resolution',p_expires=None))
        self.assertEqual(self.disposition_candidate()['withdrawal']['original_status'],'requires_resolution')

    def test_signature_disposition_candidate_legal_evidence_distinct_from_resolution(self):
        self.prepare_disposition_review(True)
        unverified='af112000-0000-4000-8000-000000000001'
        self.title_document(identity=unverified)
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET legal_source_id='{unverified}' WHERE policy_id='{POLICY}'")
        missing=self.disposition_candidate();self.assertEqual(missing['status'],'legal_evidence_required')
        self.assertIsNone(missing['candidate']);self.assertIsNotNone(missing['resolution'])
        self.assertIsNone(missing['resolution']['legal_source'])
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET legal_source_id='{TITLE_FILE}' WHERE policy_id='{POLICY}'")
        self.assertEqual(self.disposition_candidate()['candidate']['legal_source']['artifact_id'],TITLE_FILE)
        # Revoking the title scanner also removes current title approval; holds remain available.
        self.sql(f"UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp() WHERE purpose='title_report'")
        choice=self.disposition_candidate();self.assertIsNone(choice['candidate']);self.assertIsNotNone(choice['resolution']);self.assertIsNone(choice['resolution']['legal_source'])
        self.assertEqual(choice['status'],'title_review_required')
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET revoked_at=clock_timestamp() WHERE policy_id='{POLICY}'")
        self.assertEqual(self.disposition_candidate()['status'],'reviewer_policy_required')

    def test_signature_disposition_candidate_original_withdrawal_after_pause_and_replaced_plan(self):
        self.prepare_disposition_review();args=self.disposition_review_args();self.disposition_review(args)
        self.plan(self.plan_args(p_id=SECOND,p_expected_sequence=1,p_exit_type='wholesale_assignment'))
        choice=self.disposition_candidate();self.assertEqual(choice['status'],'reviewer_policy_required')
        self.assertEqual(choice['withdrawal']['review_id'],REVIEW);self.assertEqual(choice['withdrawal']['plan_id'],PLAN)
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.sql('UPDATE private.acquisition_disposition_policy_scopes SET revoked_at=clock_timestamp()')
        choice=self.disposition_candidate();self.assertEqual(choice['status'],'paused');self.assertIsNone(choice['candidate']);self.assertIsNotNone(choice['withdrawal'])
        self.disposition_review(self.disposition_review_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_original_review=REVIEW,p_personally_reviewed=False,p_findings=None,p_expires=None))
        self.assertIsNone(self.disposition_candidate()['withdrawal'])

    def test_signature_disposition_candidate_scope_session_version_and_source_holds(self):
        self.prepare_disposition_review();self.member()
        for patch in ({'workspace':WORKSPACE_B},{'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):self.disposition_candidate(fail=True,**patch)
        self.assertEqual(self.disposition_candidate(version=1)['status'],'contract_unavailable')
        self.disposition_candidate(version=9,fail=True)
        self.sql("UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp() WHERE purpose='purchase_contract'")
        choice=self.disposition_candidate();self.assertEqual(choice['status'],'evidence_review_required');self.assertIsNone(choice['resolution'])
        self.sql(f"SELECT private.disposition_source_choice('{WORKSPACE}','{DRAFT}',2,'{TITLE_FILE}',NULL,clock_timestamp())",user=ADMIN,fail=True)

class DispositionCandidateTests(DispositionCandidateCases,DispositionReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionCandidateTests,[n for n in DispositionCandidateCases.__dict__ if n.startswith('test_signature_disposition_candidate_')]))
