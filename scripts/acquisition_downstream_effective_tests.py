"""Recursive title/disposition authority never carries approval forward silently."""
import json
from acquisition_execution_effective_tests import ExecutionEffectiveTests,NEW_DATE,NEW_EXEC
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_REVIEW,DEADLINE_POLICY
from acquisition_title_review_tests import TITLE_REVIEW,FINDINGS_POLICY
from acquisition_disposition_review_tests import REVIEW
from acquisition_disposition_storage_tests import POLICY
from acquisition_disposition_plan_tests import SECOND
from test_acquisition_workspace import ROOT,main,ADMIN
MIGRATION=ROOT/'frontend/supabase/migrations/20261101101358_acquisition_downstream_effective_reviews.sql'
NEW_TITLE='af134000-0000-4000-8000-000000000001'
NEW_DISPO='af134000-0000-4000-8000-000000000002'
NEXT_DATE='af134000-0000-4000-8000-000000000003'

class DownstreamEffectiveCases:
    def effective_downstream(self,kind='title',root=None,**kwargs):
        root=root or (TITLE_REVIEW if kind=='title' else REVIEW)
        return self.sql(f"SELECT private.{kind}_review_effective_current('{root}',clock_timestamp())",**kwargs)

    def test_signature_downstream_effective_explicit_chain_and_transitive_revocation(self):
        self.prepare_handoff(True)
        originals=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        self.assertEqual(self.effective_downstream(),'t');self.assertEqual(self.effective_downstream('disposition'),'t')
        self.insert_title_fixture(self.renewal_row(DEADLINE_REVIEW,id=NEW_DATE))
        self.assertEqual(self.effective_downstream(),'f');self.assertEqual(self.effective_downstream('disposition'),'f')
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEW_EXEC))
        self.assertEqual(self.effective_downstream(),'f')
        self.insert_title_fixture(self.renewal_row(TITLE_REVIEW,id=NEW_TITLE))
        self.assertEqual(self.effective_downstream(),'t');self.assertEqual(self.effective_downstream('disposition'),'f')
        self.insert_title_fixture(self.renewal_row(REVIEW,id=NEW_DISPO))
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.assertEqual(originals,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t'))
        self.insert_title_fixture(self.renewal_row(DEADLINE_REVIEW,id=NEXT_DATE,renewal_previous_id=NEW_DATE))
        self.assertEqual(self.dependencies_match(NEW_TITLE),'t')
        self.assertEqual(self.effective_downstream(),'f');self.assertEqual(self.effective_downstream('disposition'),'f')

    def test_signature_downstream_effective_expiry_caps_follow_effective_support(self):
        self.prepare_handoff()
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEW_EXEC,expires_at=self.sql("SELECT clock_timestamp()+interval '30 seconds'")))
        self.insert_title_fixture(self.renewal_row(TITLE_REVIEW,id=NEW_TITLE))
        self.assertEqual(self.effective_downstream(),'f')
        self.insert_title_fixture(self.renewal_row(TITLE_REVIEW,id=NEXT_DATE,renewal_previous_id=NEW_TITLE,
            expires_at=self.sql("SELECT clock_timestamp()+interval '20 seconds'")))
        self.assertEqual(self.effective_downstream(),'t')
        self.insert_title_fixture(self.renewal_row(REVIEW,id=NEW_DISPO))
        self.assertEqual(self.effective_downstream('disposition'),'f')
        self.insert_title_fixture(self.renewal_row(REVIEW,id=NEW_DATE,renewal_previous_id=NEW_DISPO,
            expires_at=self.sql("SELECT clock_timestamp()+interval '10 seconds'")))
        self.assertEqual(self.effective_downstream('disposition'),'t')

    def test_signature_downstream_effective_disposition_policy_and_plan_remain_exact(self):
        self.prepare_handoff(True);self.insert_title_fixture(self.renewal_row(REVIEW,id=NEW_DISPO))
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.plan(self.plan_args(p_id=SECOND,p_expected_sequence=1))
        self.assertEqual(self.effective_downstream('disposition'),'f')
        self.assertEqual(self.effective_downstream(),'t')

    def test_signature_downstream_effective_title_policy_and_freshness_cannot_be_bypassed(self):
        self.prepare_handoff()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=NULL,title_report_timezone=NULL WHERE id='{FINDINGS_POLICY}'")
        snapshot=json.loads(self.sql(f"SELECT to_jsonb(p) FROM private.acquisition_contract_review_policies p WHERE id='{FINDINGS_POLICY}'"))
        self.insert_title_fixture(self.renewal_row(TITLE_REVIEW,id=NEW_TITLE,title_policy_snapshot=snapshot))
        self.assertEqual(self.effective_downstream(),'f')
        self.assertEqual(self.effective_downstream('disposition'),'f')

    def test_signature_downstream_effective_private_roles_and_scope_revocation(self):
        self.prepare_handoff(True);self.insert_title_fixture(self.renewal_row(REVIEW,id=NEW_DISPO))
        for kind in ('title','disposition'):
            for role in ('anon','authenticated','service_role'):self.effective_downstream(kind,user=ADMIN,role=role,fail=True)
        self.assertEqual(self.effective_downstream(root=REVIEW),'f')
        self.assertEqual(self.effective_downstream('disposition',root=NEW_DISPO),'f')
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET revoked_at=clock_timestamp() WHERE policy_id='{POLICY}'")
        self.assertEqual(self.effective_downstream('disposition'),'f');self.assertEqual(self.effective_downstream(),'t')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.assertEqual(self.effective_downstream(),'f')

class DownstreamEffectiveTests(DownstreamEffectiveCases,ExecutionEffectiveTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DownstreamEffectiveTests,[n for n in DownstreamEffectiveCases.__dict__ if n.startswith('test_signature_downstream_effective_')]))
