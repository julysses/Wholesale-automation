"""Read-only signature choices preserve original evidence and independent withdrawal."""
import json
from acquisition_signature_review_tests import SignatureReviewTests, RELEASE, RELEASE_POLICY
from acquisition_contract_source_review_tests import NEW_REVIEW
from acquisition_contract_document_tests import DOCUMENT,DRAFT,SECOND
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B

MIGRATION=ROOT/'frontend/supabase/migrations/20261101022040_acquisition_signature_candidates.sql'


class SignatureCandidateCases:
    def signature_candidate(self,actor=ADMIN,workspace=WORKSPACE,version=2,fail=False,**kwargs):
        raw=self.sql(f"SELECT public.signature_review_candidate('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_candidate_exact_source_and_no_write(self):
        before=self.sql('SELECT (SELECT count(*) FROM audit_logs),(SELECT count(*) FROM acquisition_signature_reviews)')
        choice=self.signature_candidate();again=self.signature_candidate()
        self.assertEqual(choice['status'],'ready_for_human_review');self.assertFalse(choice['execution_authorized'])
        self.assertEqual(choice['candidate']['basis_review_id'],NEW_REVIEW)
        self.assertEqual(choice['candidate']['artifact_id'],DOCUMENT)
        self.assertEqual(choice['candidate']['source_version'],1)
        self.assertEqual(choice['candidate']['policy_id'],RELEASE_POLICY)
        self.assertEqual(choice['candidate']['expected_sequence'],0)
        self.assertEqual(choice['checked_at'],choice['current_review']['checked_at'])
        self.assertIsNone(again['withdrawal']);self.assertFalse(again['current_review']['approval_current'])
        self.assertEqual(before,self.sql('SELECT (SELECT count(*) FROM audit_logs),(SELECT count(*) FROM acquisition_signature_reviews)'))

    def test_signature_candidate_pause_revocation_preserves_original_withdrawal(self):
        self.signature();self.revoke_document()
        choice=self.signature_candidate()
        self.assertEqual(choice['status'],'contract_review_required');self.assertIsNone(choice['candidate'])
        self.assertEqual(choice['withdrawal']['review_id'],RELEASE)
        self.assertEqual(choice['withdrawal']['basis_review_id'],NEW_REVIEW)
        self.sql('UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_signature_policies SET revoked_at=clock_timestamp()')
        paused=self.signature_candidate()
        self.assertEqual(paused['status'],'paused');self.assertEqual(paused['withdrawal'],choice['withdrawal'])

    def test_signature_candidate_new_basis_does_not_replace_withdrawal_identity(self):
        self.signature();self.review(self.source_review_args(p_id=SECOND,p_expected_sequence=1))
        choice=self.signature_candidate()
        self.assertEqual(choice['candidate']['basis_review_id'],SECOND)
        self.assertEqual(choice['candidate']['expected_sequence'],1)
        self.assertEqual(choice['withdrawal']['basis_review_id'],NEW_REVIEW)
        self.assertFalse(choice['current_review']['approval_current'])

    def test_signature_candidate_policy_scope_session_and_deadline(self):
        self.member()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},
                       {'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.signature_candidate(fail=True,**kwargs)
        self.sql(f"UPDATE private.acquisition_signature_policies SET valid_until=clock_timestamp()+interval '10 seconds' WHERE id='{RELEASE_POLICY}'")
        choice=self.signature_candidate()
        from datetime import datetime
        self.assertLessEqual((datetime.fromisoformat(choice['candidate']['max_expires_at'])-datetime.fromisoformat(choice['checked_at'])).total_seconds(),10)
        self.sql(f"UPDATE private.acquisition_signature_policies SET revoked_at=clock_timestamp() WHERE id='{RELEASE_POLICY}'")
        choice=self.signature_candidate()
        self.assertEqual(choice['status'],'reviewer_policy_required');self.assertIsNone(choice['candidate'])


class SignatureCandidateTests(SignatureCandidateCases,SignatureReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())


if __name__=='__main__':
    raise SystemExit(main(SignatureCandidateTests,test_names=[n for n in SignatureCandidateCases.__dict__ if n.startswith('test_signature_candidate_')]))
