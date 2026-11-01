"""Exact-document review choices; no authority or mutations from discovery."""
import json
from datetime import datetime,timezone
from acquisition_contract_review_tests import ContractReviewTests,POLICY
from acquisition_contract_document_tests import DOCUMENT,DRAFT,SECOND
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101002427_acquisition_contract_review_candidate.sql'

class ContractReviewCandidateCases:
    def candidate(self,actor=ADMIN,workspace=WORKSPACE,contract=DRAFT,version=1,kind='contract_review',artifact=DOCUMENT,fail=False,**kwargs):
        result=self.sql(f"SELECT public.contract_review_candidate('{workspace}','{contract}',{version},{literal(kind)},'{artifact}')",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_contract_review_candidate_exact_scope_and_no_mutation(self):
        before=self.sql('SELECT count(*) FROM audit_logs')
        value=self.candidate(); choice=value['candidate']
        self.assertEqual(value['status'],'ready_for_human_review');self.assertFalse(value['execution_authorized'])
        self.assertEqual(choice['artifact_id'],DOCUMENT);self.assertEqual(choice['policy_id'],POLICY)
        self.assertEqual(choice['expected_sequence'],0);self.assertIsNone(value['withdrawal'])
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),before)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews'),'0')
        for change in ({'actor':OTHER},{'workspace':WORKSPACE_B},{'contract':SECOND},{'version':2},{'artifact':SECOND},
                       {'kind':'title_review'},{'kind':'bogus'},{'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.candidate(fail=True,**change)
        self.member();self.candidate(actor=OPERATOR,fail=True)

    def test_contract_review_candidate_deadline_is_limiting_authority(self):
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()+interval '90 seconds' WHERE id='{ADMIN}'")
        value=self.candidate();deadline=datetime.fromisoformat(value['candidate']['max_expires_at'])
        self.assertGreater(deadline,datetime.now(timezone.utc));self.assertLess((deadline-datetime.now(timezone.utc)).total_seconds(),91)
        self.review(self.review_args(p_expires=value['candidate']['max_expires_at']))
        self.assertTrue(self.candidate()['current_review']['approval_current'])

    def test_contract_review_candidate_policy_and_evidence_revocation(self):
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{POLICY}'")
        value=self.candidate();self.assertEqual(value['status'],'reviewer_policy_required');self.assertIsNone(value['candidate'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=NULL WHERE id='{POLICY}'")
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        value=self.candidate();self.assertEqual(value['status'],'evidence_review_required');self.assertIsNone(value['candidate'])
        self.review(fail=True)

    def test_contract_review_candidate_withdrawal_survives_pause(self):
        self.review();self.sql('UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp()')
        value=self.candidate();self.assertEqual(value['status'],'paused');self.assertIsNone(value['candidate'])
        self.assertEqual(value['withdrawal']['expected_sequence'],1);self.assertFalse(value['current_review']['approval_current'])
        self.withdraw();self.assertIsNone(self.candidate()['withdrawal'])

class ContractReviewCandidateTests(ContractReviewCandidateCases,ContractReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ContractReviewCandidateTests,test_names=[n for n in ContractReviewCandidateCases.__dict__ if n.startswith('test_contract_review_candidate_')]))
