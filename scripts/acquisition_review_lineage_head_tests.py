"""Private lineage identity never asserts current transaction authorization."""
from acquisition_review_renewal_storage_tests import ReviewRenewalStorageTests,FIRST,SECOND
from acquisition_disposition_review_tests import REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,WORKSPACE,WORKSPACE_B,ADMIN,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101094232_acquisition_review_lineage_head.sql'

class ReviewLineageHeadCases:
    def lineage_head(self,root=REVIEW,workspace=WORKSPACE,contract=DRAFT,version=2,at='clock_timestamp()',**kwargs):
        return self.sql(f"SELECT coalesce(private.acquisition_review_lineage_head('{workspace}','{contract}',{version},'{root}',{at})::text,'none')",**kwargs)

    def test_signature_review_lineage_head_original_and_multiple_renewals(self):
        self.prepare_handoff();self.assertEqual(self.lineage_head(),REVIEW)
        row=self.renewal_row();self.insert_title_fixture(row)
        self.assertEqual(self.lineage_head(),FIRST)
        self.insert_title_fixture(row|dict(id=SECOND,sequence=row['sequence']+1,renewal_previous_id=FIRST))
        self.assertEqual(self.lineage_head(),SECOND)
        self.assertEqual(self.lineage_head(root=FIRST),'none')
        self.assertEqual(self.lineage_head(root=EXEC_REVIEW),EXEC_REVIEW)
        # Identity can remain resolvable after expiry; this helper grants no authority.
        self.assertEqual(self.lineage_head(at="clock_timestamp()+interval '1 day'"),SECOND)

    def test_signature_review_lineage_head_scope_time_and_private_access(self):
        self.prepare_handoff()
        for kwargs in (dict(workspace=WORKSPACE_B),dict(contract=FIRST),dict(version=1),dict(root=FIRST),
            dict(at='NULL'),dict(at="'infinity'::timestamptz"),dict(at="clock_timestamp()-interval '1 day'")):
            self.assertEqual(self.lineage_head(**kwargs),'none')
        for role in ('anon','authenticated','service_role'):
            self.lineage_head(user=ADMIN,role=role,fail=True)

    def test_signature_review_lineage_head_supersession_withdrawal_never_revives(self):
        self.prepare_handoff()
        self.disposition_review(self.disposition_review_args(p_id=SECOND,p_expected_sequence=1))
        self.assertEqual(self.lineage_head(),'none');self.assertEqual(self.lineage_head(root=SECOND),SECOND)
        self.disposition_review(self.disposition_review_args(p_id=FIRST,p_expected_sequence=2,p_status='withdrawn',p_expires=None,
            p_personally_reviewed=False,p_original_review=SECOND,p_findings=None))
        self.assertEqual(self.lineage_head(root=SECOND),'none')
        self.assertEqual(self.lineage_head(),'none')

class ReviewLineageHeadTests(ReviewLineageHeadCases,ReviewRenewalStorageTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(ReviewLineageHeadTests,[n for n in ReviewLineageHeadCases.__dict__ if n.startswith('test_signature_review_lineage_')]))
