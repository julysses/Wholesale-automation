"""Current term-specific interpretation authority with a shared concurrency cursor."""
import json
from acquisition_deadline_review_tests import DeadlineReviewTests,DEADLINE_REVIEW,DEADLINE_POLICY,SECOND_REVIEW,WITHDRAW
from acquisition_contract_document_tests import DOCUMENT,DRAFT
from acquisition_contract_observation_tests import OBS
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101043729_acquisition_deadline_resolution_state.sql'


class DeadlineStateCases:
    def deadline_state(self,term='closing_deadline',workspace=WORKSPACE,version=2,actor=ADMIN,fail=False,**kwargs):
        raw=self.sql(f"SELECT public.deadline_review_state('{workspace}','{DRAFT}',{version},'{term}')",user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_deadline_state_separate_terms_shared_sequence_and_original_withdrawal(self):
        self.prepare_deadline_review()
        initial=self.deadline_state();self.assertEqual(initial['status'],'not_reviewed');self.assertEqual(initial['sequence'],0)
        self.deadline_review()
        before=self.sql('SELECT count(*) FROM audit_logs')
        closing=self.deadline_state();self.assertTrue(closing['approval_current']);self.assertEqual(closing['review_sequence'],1)
        empty=self.deadline_state('effective');self.assertEqual(empty['sequence'],1);self.assertEqual(empty['status'],'not_reviewed');self.assertIsNone(empty['review_sequence'])
        self.assertEqual(before,self.sql('SELECT count(*) FROM audit_logs'))
        effective=self.deadline_proposal();effective.update(term='effective',calendar_date='2026-11-01',resolved_instant='2026-11-01T17:00:00-06:00');effective['source']['term']='effective'
        self.deadline_review(self.deadline_args(p_id=SECOND_REVIEW,p_expected_sequence=1,p_term='effective',p_resolution=effective))
        state=self.deadline_state();self.assertEqual(state['sequence'],2);self.assertEqual(state['review_sequence'],1);self.assertTrue(state['approval_current'])
        self.deadline_review(self.deadline_args(p_id=WITHDRAW,p_expected_sequence=2,p_status='withdrawn',p_original=DEADLINE_REVIEW,
            p_resolution=None,p_expires=None,p_personally_reviewed=False))
        removed=self.deadline_state();self.assertEqual(removed['status'],'withdrawn');self.assertEqual(removed['review_sequence'],3)
        self.assertEqual(removed['interpretation_review_id'],DEADLINE_REVIEW);self.assertEqual(removed['resolution'],closing['resolution']);self.assertIsNone(removed['expires_at'])
        self.assertTrue(self.deadline_state('effective')['approval_current'])
        self.assertEqual(self.deadline_state('effective')['review_sequence'],2)

    def test_signature_deadline_state_policy_pause_and_expiry_remove_current_authority(self):
        self.prepare_deadline_review();self.deadline_review();self.assertTrue(self.deadline_state()['approval_current'])
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.deadline_state()['status'],'requires_review')
        self.sql('UPDATE private.acquisition_activation SET enabled=true')
        self.assertTrue(self.deadline_state()['approval_current'])
        self.assertEqual(self.sql(f"SELECT private.deadline_review_current('{DEADLINE_REVIEW}',clock_timestamp()+interval '1 day')"),'f')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        state=self.deadline_state();self.assertFalse(state['approval_current']);self.assertIsNone(state['expires_at'])
        self.assertEqual(state['review_id'],DEADLINE_REVIEW);self.assertTrue(self.deadline_review()['duplicate'])

    def test_signature_deadline_state_original_source_revocation_keeps_history(self):
        self.test_signature_deadline_write_requires_both_original_and_interpretation_sources()
        state=self.deadline_state();self.assertEqual(state['status'],'requires_review');self.assertIsNotNone(state['resolution'])
        self.assertEqual(state['original_term']['calendar_date'],'2026-11-20')

    def test_signature_deadline_state_interpretation_source_revocation_independently_holds(self):
        self.prepare_deadline_review()
        document='af850000-0000-4000-8000-000000000001';scan='af850000-0000-4000-8000-000000000002'
        self.document(identity=document,version=2)
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{document}')",user=ADMIN))
        self.record_contract_scan(self.signed_contract(request=scan,artifact_id=document,contract_version=2,retain_until=state['retain_until']))
        proposal=self.deadline_proposal();proposal['source'].update(artifact_id=document,artifact_version=2)
        self.deadline_review(self.deadline_args(p_artifact=document,p_verification=scan,p_resolution=proposal))
        self.assertTrue(self.deadline_state()['approval_current'])
        self.sql(f"SELECT public.revoke_contract_document('{WITHDRAW}','{WORKSPACE}','{DRAFT}',2,'{document}','Supplemental time interpretation evidence withdrawn.')",user=ADMIN)
        self.assertFalse(self.deadline_state()['approval_current'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_evidence_revocations WHERE artifact_id='{DOCUMENT}'"),'0')

    def test_signature_deadline_state_scan_replacement_and_scanner_authority_hold(self):
        self.prepare_deadline_review();self.deadline_review()
        self.record_contract_scan(self.signed_contract(request=WITHDRAW))
        self.assertFalse(self.deadline_state()['approval_current'])
        self.assertEqual(self.sql(f"SELECT verification_id FROM acquisition_contract_reviews WHERE id='{DEADLINE_REVIEW}'"),OBS)
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.assertFalse(self.deadline_state()['approval_current'])

    def test_signature_deadline_state_scope_session_and_original_version(self):
        self.prepare_deadline_review();self.deadline_review()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},
                       {'role':'anon'},{'workspace':WORKSPACE_B},{'version':3},{'term':'purchase_price'}):
            self.deadline_state(fail=True,**kwargs)
        historical=self.deadline_state(version=1);self.assertEqual(historical['status'],'not_reviewed');self.assertEqual(historical['original_term']['precision'],'unknown')
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.deadline_state(fail=True)


class DeadlineStateTests(DeadlineStateCases,DeadlineReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(DeadlineStateTests,test_names=[n for n in DeadlineStateCases.__dict__ if n.startswith('test_signature_deadline_state_')]))
