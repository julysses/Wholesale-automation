"""Source-backed deadline actions and independent original-term withdrawal."""
import json
from datetime import datetime
from acquisition_deadline_state_tests import DeadlineStateTests
from acquisition_deadline_review_tests import DEADLINE_POLICY,DEADLINE_REVIEW,SECOND_REVIEW
from acquisition_contract_document_tests import DRAFT,DOCUMENT
from acquisition_contract_observation_tests import OBS
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101044534_acquisition_deadline_resolution_choices.sql'
NEW_DOCUMENT='af860000-0000-4000-8000-000000000001'


class DeadlineChoiceCases:
    def deadline_choice(self,term='closing_deadline',artifact=DOCUMENT,workspace=WORKSPACE,version=2,actor=ADMIN,fail=False,**kwargs):
        raw=self.sql(f"SELECT public.deadline_review_candidate('{workspace}','{DRAFT}',{version},'{term}','{artifact}')",user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_deadline_choice_exact_original_and_selected_source_without_writes(self):
        self.prepare_deadline_review();before=self.sql('SELECT count(*) FROM audit_logs')
        for _ in range(2):
            value=self.deadline_choice();self.assertEqual(value['status'],'ready_for_human_review')
            self.assertEqual(value['candidate']['artifact_id'],DOCUMENT);self.assertEqual(value['candidate']['source_version'],1)
            self.assertEqual(value['candidate']['policy_id'],DEADLINE_POLICY);self.assertEqual(value['candidate']['expected_sequence'],0)
            self.assertEqual(value['original_source']['verification_id'],OBS);self.assertEqual(value['original_source']['term'],'closing_deadline')
            self.assertEqual(value['current_review']['original_term']['calendar_date'],'2026-11-20')
            self.assertIsNone(value['withdrawal']);self.assertFalse(value['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"),'0')
        held=self.deadline_choice(term='inspection_deadline');self.assertEqual(held['status'],'original_date_required');self.assertIsNone(held['candidate'])

    def test_signature_deadline_choice_other_term_and_unverified_selection_preserve_original_withdrawal(self):
        self.prepare_deadline_review();self.deadline_review()
        effective=self.deadline_proposal();effective.update(term='effective',calendar_date='2026-11-01',resolved_instant='2026-11-01T17:00:00-06:00');effective['source']['term']='effective'
        self.deadline_review(self.deadline_args(p_id=SECOND_REVIEW,p_expected_sequence=1,p_term='effective',p_resolution=effective))
        self.document(identity=NEW_DOCUMENT,version=2)
        choice=self.deadline_choice(artifact=NEW_DOCUMENT)
        self.assertEqual(choice['status'],'evidence_review_required');self.assertIsNone(choice['candidate'])
        self.assertEqual(choice['withdrawal']['review_id'],DEADLINE_REVIEW);self.assertEqual(choice['withdrawal']['artifact_id'],DOCUMENT)
        self.assertEqual(choice['withdrawal']['expected_sequence'],2);self.assertEqual(choice['current_review']['review_sequence'],1)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        paused=self.deadline_choice(artifact=NEW_DOCUMENT);self.assertEqual(paused['status'],'paused')
        self.assertEqual(paused['withdrawal'],choice['withdrawal']);self.assertFalse(paused['current_review']['approval_current'])

    def test_signature_deadline_choice_policy_expiry_and_original_evidence_holds(self):
        self.prepare_deadline_review()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET max_review_seconds=30 WHERE id='{DEADLINE_POLICY}'")
        ready=self.deadline_choice();seconds=(datetime.fromisoformat(ready['candidate']['max_expires_at'])-datetime.fromisoformat(ready['checked_at'])).total_seconds()
        self.assertGreater(seconds,0);self.assertLessEqual(seconds,30)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.assertEqual(self.deadline_choice()['status'],'reviewer_policy_required')
        self.record_contract_scan(self.signed_contract(request=SECOND_REVIEW))
        original=self.deadline_choice();self.assertEqual(original['status'],'original_evidence_review_required');self.assertIsNone(original['candidate'])
        self.assertEqual(original['original_source']['verification_id'],OBS)

    def test_signature_deadline_choice_scope_session_retained_version_and_revocation(self):
        self.prepare_deadline_review();self.deadline_review()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'version':3},
                       {'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'},{'term':'purchase_price'}):
            self.deadline_choice(fail=True,**kwargs)
        retained=self.deadline_choice(version=1);self.assertEqual(retained['status'],'contract_unavailable');self.assertIsNone(retained['candidate'])
        self.revoke_document()
        held=self.deadline_choice();self.assertEqual(held['status'],'original_evidence_review_required')
        self.assertEqual(held['withdrawal']['review_id'],DEADLINE_REVIEW);self.assertIsNone(held['candidate'])


class DeadlineChoiceTests(DeadlineChoiceCases,DeadlineStateTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(DeadlineChoiceTests,test_names=[n for n in DeadlineChoiceCases.__dict__ if n.startswith('test_signature_deadline_choice_')]))
