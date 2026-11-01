"""Read-only title choices distinguish approval, resolution and original withdrawal."""
import json
from acquisition_title_review_tests import TitleReviewTests,TITLE_REVIEW,TITLE_WITHDRAW
from acquisition_title_storage_tests import TITLE_FILE,FINDINGS_POLICY,TITLE_POLICY
from acquisition_execution_review_tests import EXEC_POLICY
from acquisition_contract_document_tests import DRAFT,DOCUMENT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101063735_acquisition_title_review_choices.sql'

class TitleCandidateCases:
    def title_candidate(self,artifact=TITLE_FILE,workspace=WORKSPACE,version=2,actor=ADMIN,fail=False,**kwargs):
        selected='NULL' if artifact is None else "'"+artifact+"'"
        value=self.sql(f"SELECT public.title_review_candidate('{workspace}','{DRAFT}',{version},{selected})",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_signature_title_candidate_read_only_exact_original_and_freshness_rules(self):
        self.prepare_title_review();before=self.sql('SELECT count(*) FROM audit_logs')
        for _ in range(2):
            result=self.title_candidate();self.assertEqual(result['status'],'ready_for_human_review')
            self.assertEqual(result['candidate']['artifact_id'],TITLE_FILE);self.assertEqual(result['candidate']['source_version'],2)
            self.assertEqual(result['candidate']['report_policy'],dict(max_age_seconds=86400,max_age_days=1,timezone='UTC'))
            self.assertEqual(result['candidate']['expected_sequence'],0);self.assertIsNone(result['withdrawal'])
            self.assertEqual(result['current_review']['status'],'not_reviewed');self.assertFalse(result['execution_authorized'])
            self.assertEqual({k:v for k,v in result['candidate'].items() if k not in ('max_expires_at','report_policy')},result['resolution'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        self.assertEqual(self.title_candidate(artifact=None)['status'],'document_required')

    def test_signature_title_candidate_original_withdrawal_without_selected_report(self):
        self.prepare_title_review();args=self.title_review_args(p_status='requires_resolution',p_expires=None);self.title_review(args)
        result=self.title_candidate(artifact=None);self.assertIsNone(result['candidate']);self.assertIsNone(result['resolution'])
        self.assertEqual(result['withdrawal']['review_id'],TITLE_REVIEW);self.assertEqual(result['withdrawal']['original_status'],'requires_resolution')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{FINDINGS_POLICY}'")
        result=self.title_candidate(artifact=None);self.assertEqual(result['status'],'paused');self.assertEqual(result['withdrawal']['artifact_id'],TITLE_FILE)
        self.title_review(args|dict(p_id=TITLE_WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_personally_reviewed=False,p_findings=None))
        self.assertIsNone(self.title_candidate(artifact=None)['withdrawal'])

    def test_signature_title_candidate_resolution_only_for_missing_freshness_or_execution(self):
        self.prepare_title_review()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_seconds=NULL,title_report_max_age_days=NULL,title_report_timezone=NULL WHERE id='{FINDINGS_POLICY}'")
        result=self.title_candidate();self.assertEqual(result['status'],'report_freshness_policy_required');self.assertIsNone(result['candidate']);self.assertIsNotNone(result['resolution'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_seconds=86400 WHERE id='{FINDINGS_POLICY}'")
        self.assertEqual(self.title_candidate()['candidate']['report_policy'],dict(max_age_seconds=86400,max_age_days=None,timezone=None))
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        result=self.title_candidate();self.assertEqual(result['status'],'execution_review_required');self.assertIsNone(result['candidate']);self.assertIsNotNone(result['resolution'])
        self.title_review(self.title_review_args(p_status='requires_resolution',p_expires=None))
        self.assertEqual(self.title_candidate()['withdrawal']['original_status'],'requires_resolution')

    def test_signature_title_candidate_scope_session_retained_version_and_source_revocation(self):
        self.prepare_title_review();self.member()
        for kwargs in ({'workspace':WORKSPACE_B},{'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'artifact':DOCUMENT}):self.title_candidate(fail=True,**kwargs)
        self.assertEqual(self.title_candidate(artifact=None,version=1)['status'],'contract_unavailable')
        self.title_candidate(artifact=None,version=9,fail=True)
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{TITLE_POLICY}'")
        result=self.title_candidate();self.assertEqual(result['status'],'evidence_review_required');self.assertIsNone(result['resolution']);self.assertIsNone(result['candidate'])

class TitleCandidateTests(TitleCandidateCases,TitleReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(TitleCandidateTests,[n for n in TitleCandidateCases.__dict__ if n.startswith('test_signature_title_candidate_')]))
