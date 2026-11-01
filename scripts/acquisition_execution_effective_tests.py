"""Execution support follows explicitly bound fresh deadline decisions."""
import json
from acquisition_deadline_effective_tests import DeadlineEffectiveTests
from acquisition_deadline_review_tests import DEADLINE_REVIEW,DEADLINE_POLICY
from acquisition_execution_review_tests import EXEC_REVIEW,EXEC_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,WORKSPACE
MIGRATION=ROOT/'frontend/supabase/migrations/20261101101024_acquisition_execution_effective_review.sql'
NEW_DATE='af133000-0000-4000-8000-000000000001'
NEW_EXEC='af133000-0000-4000-8000-000000000002'
NEXT_EXEC='af133000-0000-4000-8000-000000000003'

class ExecutionEffectiveCases:
    def effective_execution(self,root=EXEC_REVIEW,at='clock_timestamp()',**kwargs):
        return self.sql(f"SELECT private.execution_review_effective_current('{root}',{at})",**kwargs)

    def test_signature_execution_effective_requires_personal_rebinding_and_preserves_history(self):
        self.prepare_handoff();self.assertEqual(self.effective_execution(),'t')
        before=self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{EXEC_REVIEW}'")
        transitions=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        self.insert_title_fixture(self.renewal_row(DEADLINE_REVIEW,id=NEW_DATE))
        self.assertEqual(self.effective_execution(),'f')
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEW_EXEC))
        self.assertEqual(self.effective_execution(),'t')
        self.assertEqual(self.effective_execution(root=NEW_EXEC),'f')
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{EXEC_REVIEW}'"))
        self.assertEqual(transitions,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t'))
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.assertEqual(self.effective_execution(),'f')

    def test_signature_execution_effective_caps_expiry_to_bound_renewed_deadline(self):
        self.prepare_handoff()
        self.insert_title_fixture(self.renewal_row(DEADLINE_REVIEW,id=NEW_DATE,expires_at=self.sql("SELECT clock_timestamp()+interval '20 seconds'")))
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEW_EXEC))
        self.assertEqual(self.effective_execution(),'f')
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEXT_EXEC,renewal_previous_id=NEW_EXEC,
            expires_at=self.sql("SELECT clock_timestamp()+interval '10 seconds'")))
        self.assertEqual(self.effective_execution(),'t')
        self.assertEqual(self.effective_execution(at="clock_timestamp()+interval '1 day'"),'f')

    def test_signature_execution_effective_rejects_missing_source_and_current_policy(self):
        self.prepare_handoff();row=self.renewal_row(EXEC_REVIEW,id=NEW_EXEC)
        row['execution_sources'][0]['verification_id']=NEW_DATE
        self.insert_title_fixture(row);self.assertEqual(self.effective_execution(),'f')
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEXT_EXEC,renewal_previous_id=NEW_EXEC))
        self.assertEqual(self.effective_execution(),'t')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        self.assertEqual(self.effective_execution(),'f')

    def test_signature_execution_effective_private_scope_pause_and_session(self):
        self.prepare_handoff();self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEW_EXEC))
        self.assertEqual(self.effective_execution(),'t')
        self.assertEqual(self.effective_execution(root=DEADLINE_REVIEW),'f')
        for at in ('NULL',"'infinity'::timestamptz"):self.assertEqual(self.effective_execution(at=at),'f')
        for role in ('anon','authenticated','service_role'):self.effective_execution(user=ADMIN,role=role,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.assertEqual(self.effective_execution(),'f')
        self.sql('UPDATE private.acquisition_activation SET enabled=true');self.assertEqual(self.effective_execution(),'t')
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.assertEqual(self.effective_execution(),'f')

    def test_signature_execution_effective_suspended_workspace_instant(self):
        self.prepare_execution();self.execution_review()
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=NEW_EXEC))
        self.assertEqual(self.effective_execution(),'t')
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"),'0')
        self.sql(f"UPDATE workspaces SET status='suspended' WHERE id='{WORKSPACE}'")
        self.assertEqual(self.effective_execution(),'f')
        self.sql(f"UPDATE workspaces SET status='active' WHERE id='{WORKSPACE}'")
        self.assertEqual(self.effective_execution(),'t')

class ExecutionEffectiveTests(ExecutionEffectiveCases,DeadlineEffectiveTests):
    def setUp(self):
        if self._testMethodName.endswith('_workspace_instant'):self.binding_prepared_terms=self.execution_prepared_terms
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(ExecutionEffectiveTests,[n for n in ExecutionEffectiveCases.__dict__ if n.startswith('test_signature_execution_effective_')]))
