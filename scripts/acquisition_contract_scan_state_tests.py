"""Current contract scan assessment over shared immutable evidence, on a disposable DB."""
import json
from acquisition_contract_observation_tests import ContractObservationTests, OBS, KEY
from acquisition_contract_document_tests import DOCUMENT, DRAFT, SECOND, DOC_POLICY
from test_acquisition_workspace import ROOT, main, ADMIN, OTHER, OPERATOR, CALLER, WORKSPACE, WORKSPACE_B, literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261031235803_acquisition_contract_scan_state.sql'

class ContractScanStateCases:
    def contract_scan_state(self, actor=ADMIN, workspace=WORKSPACE, contract=DRAFT, version=1,
                            purpose='purchase_contract', artifact=DOCUMENT, fail=False, **kwargs):
        result=self.sql(f"SELECT public.contract_document_scan_state('{workspace}','{contract}',{version},{literal(purpose)},'{artifact}')",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_contract_scan_state_current_read_has_no_write_or_approval(self):
        self.assertEqual(self.contract_scan_state()['status'],'not_scanned')
        self.record_contract_scan(self.signed_contract())
        counts=self.sql('SELECT (SELECT count(*) FROM audit_logs),(SELECT count(*) FROM acquisition_evidence_verifications)')
        state=self.contract_scan_state()
        self.assertEqual((state['status'],state['observation_id']),('no_detection_observed',OBS))
        self.assertEqual((state['contract_id'],state['contract_version'],state['purpose']),(DRAFT,1,'purchase_contract'))
        self.assertEqual(set(state),{'workspace_id','contract_id','contract_version','purpose','artifact_id','status','quarantined','observation_id','preview_authorized','legal_review_approved','execution_authorized','checked_at'})
        self.assertTrue(all(state[k] is False for k in ('preview_authorized','legal_review_approved','execution_authorized','quarantined')))
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.contract_scan_state()['status'],'no_detection_observed')
        self.assertEqual(self.sql('SELECT (SELECT count(*) FROM audit_logs),(SELECT count(*) FROM acquisition_evidence_verifications)'),counts)

    def test_contract_scan_state_exact_scope_roles_and_session(self):
        self.record_contract_scan(self.signed_contract())
        for change in ({'workspace':WORKSPACE_B},{'contract':SECOND},{'version':2},{'purpose':'title_report'},
                       {'artifact':SECOND},{'actor':OTHER},{'role':'service_role'},{'role':'anon'},{'aal':'aal1'},{'session':False}):
            self.contract_scan_state(fail=True,**change)
        self.member();self.contract_scan_state(actor=OPERATOR,fail=True)
        self.member(target=CALLER,role='acquisition_caller');self.contract_scan_state(actor=CALLER,fail=True)
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.contract_scan_state(fail=True)

    def test_contract_scan_state_current_authority_required(self):
        self.record_contract_scan(self.signed_contract())
        # Each mutation is rolled back to test independently without modifying
        # immutable evidence or fabricating a replacement clean observation.
        mutations=[
            "UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()",
            "UPDATE private.acquisition_contract_verification_key_scopes SET valid_until=clock_timestamp()-interval '1 second'",
            "UPDATE private.acquisition_contract_verification_key_scopes SET valid_from=clock_timestamp()",
            "UPDATE private.acquisition_evidence_verification_keys SET revoked_at=clock_timestamp()",
            "UPDATE private.acquisition_evidence_verification_keys SET valid_until=clock_timestamp()-interval '1 second'",
            "UPDATE private.acquisition_evidence_verification_keys SET scanner_version='ClamAV 1.4.3/12346/Thu Oct 29 00:00:00 2026'",
            "UPDATE private.acquisition_evidence_verification_keys SET scan_policy_version='synthetic-v2'",
            f"UPDATE workspace_memberships SET updated_at=updated_at+interval '1 second' WHERE user_id='{ADMIN}'",
        ]
        for mutation in mutations:
            # Same authenticated reader after owner-only fixture mutation.
            result=self.sql('BEGIN; '+mutation+'; SET LOCAL ROLE authenticated; '+
                f"SELECT set_config('request.jwt.claims',jsonb_build_object('sub','{ADMIN}','role','authenticated','aal','aal2','session_id','{ADMIN}')::text,true); "+
                f"SELECT public.contract_document_scan_state('{WORKSPACE}','{DRAFT}',1,'purchase_contract','{DOCUMENT}'); ROLLBACK;")
            state=json.loads(result.splitlines()[-1])
            self.assertEqual(state['status'],'requires_review',mutation)
            self.assertIsNone(state['observation_id'])
        self.assertEqual(self.contract_scan_state()['status'],'no_detection_observed')

    def test_contract_scan_state_original_actor_can_lose_authority(self):
        self.member(target=OTHER,role='admin')
        self.record_contract_scan(self.signed_contract())
        for mutation in (
            f"UPDATE workspace_memberships SET status='revoked' WHERE workspace_id='{WORKSPACE}' AND user_id='{ADMIN}'",
            f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'",
            f"DELETE FROM auth.sessions WHERE id='{ADMIN}'",
            f"UPDATE profiles SET status='pending' WHERE id='{ADMIN}'",
        ):
            result=self.sql('BEGIN; '+mutation+'; SET LOCAL ROLE authenticated; '+
                f"SELECT set_config('request.jwt.claims',jsonb_build_object('sub','{OTHER}','role','authenticated','aal','aal2','session_id','{OTHER}')::text,true); "+
                f"SELECT public.contract_document_scan_state('{WORKSPACE}','{DRAFT}',1,'purchase_contract','{DOCUMENT}'); ROLLBACK;")
            state=json.loads(result.splitlines()[-1])
            self.assertEqual(state['status'],'requires_review',mutation)
            self.assertIsNone(state['observation_id'])
        self.assertEqual(self.contract_scan_state(actor=OTHER)['status'],'no_detection_observed')

    def test_contract_scan_state_mail_detection_remains_after_clean_and_revoke(self):
        self.record_contract_scan(self.signed_contract())
        self.evidence_register(request=SECOND,digest='b'*64)
        self.record_observation(self.signed_observation(request=SECOND,artifact=SECOND,scan_status='detected'))
        state=self.contract_scan_state()
        self.assertEqual(state['status'],'quarantined');self.assertTrue(state['quarantined']);self.assertIsNone(state['observation_id'])
        self.record_contract_scan(self.signed_contract(request='ae000000-0000-4000-8000-000000000003'))
        self.assertEqual(self.contract_scan_state()['status'],'quarantined')
        self.revoke_document()
        state=self.contract_scan_state();self.assertEqual(state['status'],'revoked');self.assertTrue(state['quarantined'])

    def test_contract_scan_state_retention_policy_and_revocation(self):
        self.record_contract_scan(self.signed_contract())
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        state=self.contract_scan_state();self.assertEqual(state['status'],'policy_review_required');self.assertIsNone(state['observation_id'])
        self.revoke_document()
        self.assertEqual(self.contract_scan_state()['status'],'revoked')


class ContractScanStateTests(ContractScanStateCases,ContractObservationTests):
    def setUp(self):
        super().setUp()
        history=self.sql('SELECT jsonb_agg(to_jsonb(v)) FROM acquisition_evidence_verifications v')
        audit=self.sql('SELECT count(*) FROM audit_logs')
        self.sql(MIGRATION.read_text())
        self.assertEqual(self.sql('SELECT jsonb_agg(to_jsonb(v)) FROM acquisition_evidence_verifications v'),history)
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),audit)

if __name__=='__main__':
    raise SystemExit(main(ContractScanStateTests,test_names=[n for n in ContractScanStateCases.__dict__ if n.startswith('test_contract_scan_state_')]))
