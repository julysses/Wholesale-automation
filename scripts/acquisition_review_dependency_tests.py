"""Immutable supporting identities prevent silent approval carryover."""
import json
from acquisition_review_lineage_head_tests import ReviewLineageHeadTests
from acquisition_disposition_review_tests import REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_REVIEW,WITHDRAW
from test_acquisition_workspace import ROOT,main,ADMIN,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101095023_acquisition_review_renewal_dependencies.sql'

class ReviewDependencyCases:
    def dependencies_match(self,review,**kwargs):
        return self.sql(f"SELECT private.acquisition_review_dependencies_match('{review}',clock_timestamp())",**kwargs)

    def test_signature_review_dependencies_bind_each_personal_renewal_in_order(self):
        self.prepare_handoff()
        for root in (EXEC_REVIEW,TITLE_REVIEW,REVIEW):self.assertEqual(self.dependencies_match(root),'t')
        deadline=self.sql("SELECT id FROM acquisition_contract_reviews WHERE kind='deadline_resolution' AND deadline_term='closing_deadline'")
        ids=[f'af131000-0000-4000-8000-{i:012d}' for i in range(1,6)]
        self.insert_title_fixture(self.renewal_row(deadline,id=ids[0]))
        self.assertEqual(self.dependencies_match(EXEC_REVIEW),'f')
        self.insert_title_fixture(self.renewal_row(EXEC_REVIEW,id=ids[1]))
        self.assertEqual(self.dependencies_match(ids[1]),'t');self.assertEqual(self.dependencies_match(TITLE_REVIEW),'f')
        saved=self.sql(f"SELECT renewal_dependencies FROM acquisition_contract_reviews WHERE id='{ids[1]}'")
        self.insert_title_fixture(self.renewal_row(TITLE_REVIEW,id=ids[2]))
        self.assertEqual(self.dependencies_match(ids[2]),'t');self.assertEqual(self.dependencies_match(REVIEW),'f')
        self.insert_title_fixture(self.renewal_row(REVIEW,id=ids[3]))
        self.assertEqual(self.dependencies_match(ids[3]),'t')
        self.insert_title_fixture(self.renewal_row(deadline,id=ids[4],renewal_previous_id=ids[0]))
        self.assertEqual(self.dependencies_match(ids[1]),'f')
        self.assertEqual(saved,self.sql(f"SELECT renewal_dependencies FROM acquisition_contract_reviews WHERE id='{ids[1]}'"))
        # This helper checks direct bindings only, not transitive authority/expiry.
        self.assertEqual(self.dependencies_match(ids[2]),'t')

    def test_signature_review_dependencies_reject_client_snapshot_and_withdrawn_support(self):
        self.prepare_handoff();row=self.renewal_row()
        self.insert_title_fixture(row|dict(renewal_dependencies=[]),fail=True)
        for role in ('anon','authenticated','service_role'):self.dependencies_match(REVIEW,user=ADMIN,role=role,fail=True)
        self.assertEqual(self.dependencies_match('af131000-0000-4000-8000-999999999999'),'f')
        for root in (EXEC_REVIEW,TITLE_REVIEW,REVIEW):
            self.assertEqual(self.sql(f"SELECT renewal_dependencies IS NULL FROM acquisition_contract_reviews WHERE id='{root}'"),'t')
        self.assertEqual(self.sql(f"SELECT private.acquisition_review_dependency_heads('{WORKSPACE_B}','{row['contract_id']}',2,'{REVIEW}',clock_timestamp()) IS NULL"),'t')
        self.deadline_review(self.deadline_args(p_id=WITHDRAW,p_expected_sequence=2,p_status='withdrawn',p_original=DEADLINE_REVIEW,
            p_resolution=None,p_personally_reviewed=False,p_expires=None))
        self.assertEqual(self.dependencies_match(EXEC_REVIEW),'f')
        error=self.insert_title_fixture(self.renewal_row(EXEC_REVIEW),fail=True)
        self.assertIn('Unwithdrawn original supporting reviews required',error)

class ReviewDependencyTests(ReviewDependencyCases,ReviewLineageHeadTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(ReviewDependencyTests,[n for n in ReviewDependencyCases.__dict__ if n.startswith('test_signature_review_dependencies_')]))
