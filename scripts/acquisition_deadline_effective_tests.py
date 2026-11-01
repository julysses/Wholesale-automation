"""Root-aware deadline support keeps history and requires current evidence."""
import json
from acquisition_review_dependency_tests import ReviewDependencyTests
from acquisition_deadline_review_tests import DEADLINE_REVIEW,DEADLINE_POLICY,WITHDRAW
from acquisition_contract_observation_tests import OBS
from test_acquisition_workspace import ROOT,main,ADMIN
MIGRATION=ROOT/'frontend/supabase/migrations/20261101095505_acquisition_deadline_effective_review.sql'
NEW_SCAN='af132000-0000-4000-8000-000000000001'

class DeadlineEffectiveCases:
    def effective_deadline(self,root=DEADLINE_REVIEW,at='clock_timestamp()',**kwargs):
        return self.sql(f"SELECT private.deadline_review_effective_current('{root}',{at})",**kwargs)

    def test_signature_deadline_effective_expiry_uses_renewal_preserves_original(self):
        self.prepare_deadline_review();short=self.sql("SELECT clock_timestamp()+interval '2 seconds'")
        self.deadline_review(self.deadline_args(p_expires=short))
        before=self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{DEADLINE_REVIEW}'")
        row=self.renewal_row(DEADLINE_REVIEW,expires_at=self.sql("SELECT clock_timestamp()+interval '20 seconds'"))
        self.insert_title_fixture(row)
        self.assertEqual(self.effective_deadline(at=f"'{short}'::timestamptz+interval '1 second'"),'t')
        self.assertEqual(self.effective_deadline(at="clock_timestamp()+interval '1 day'"),'f')
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{DEADLINE_REVIEW}'"))
        # Migration115 separately tests renewed-anchor lookup and exact-ID currentness.

    def test_signature_deadline_effective_fresh_scan_same_bytes_and_scanner_revocation(self):
        self.prepare_deadline_review();self.deadline_review()
        self.assertEqual(self.effective_deadline(),'t')
        self.record_contract_scan(self.signed_contract(request=NEW_SCAN))
        self.assertEqual(self.effective_deadline(),'f')
        row=self.renewal_row(DEADLINE_REVIEW,verification_id=NEW_SCAN)
        for source in row['deadline_sources']:
            if source['artifact_id']==row['artifact_id']:source['verification_id']=NEW_SCAN
        self.insert_title_fixture(row)
        self.assertEqual(self.effective_deadline(),'t')
        self.assertEqual(self.sql(f"SELECT verification_id FROM acquisition_contract_reviews WHERE id='{DEADLINE_REVIEW}'"),OBS)
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.assertEqual(self.effective_deadline(),'f')

    def test_signature_deadline_effective_pause_policy_session_and_private_access(self):
        self.prepare_deadline_review();self.deadline_review();self.insert_title_fixture(self.renewal_row(DEADLINE_REVIEW))
        self.assertEqual(self.effective_deadline(),'t')
        for at in ('NULL',"'infinity'::timestamptz"):self.assertEqual(self.effective_deadline(at=at),'f')
        for role in ('anon','authenticated','service_role'):self.effective_deadline(user=ADMIN,role=role,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.assertEqual(self.effective_deadline(),'f')
        self.sql('UPDATE private.acquisition_activation SET enabled=true');self.assertEqual(self.effective_deadline(),'t')
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.assertEqual(self.effective_deadline(),'f')

    def test_signature_deadline_effective_withdrawal_and_policy_revocation(self):
        self.prepare_deadline_review();self.deadline_review()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.assertEqual(self.effective_deadline(),'f')
        self.deadline_review(self.deadline_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_original=DEADLINE_REVIEW,
            p_resolution=None,p_personally_reviewed=False,p_expires=None))
        self.assertEqual(self.effective_deadline(),'f')

class DeadlineEffectiveTests(DeadlineEffectiveCases,ReviewDependencyTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DeadlineEffectiveTests,[n for n in DeadlineEffectiveCases.__dict__ if n.startswith('test_signature_deadline_effective_')]))
