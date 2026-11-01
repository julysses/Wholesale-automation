"""New personal findings explicitly bind renewed supporting decisions."""
import json
from datetime import datetime,timedelta,timezone
from acquisition_effective_handoff_tests import EffectiveHandoffTests
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_disposition_review_tests import REVIEW
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,WORKSPACE,ADMIN,literal,main
MIGRATION=ROOT/'frontend/supabase/migrations/20261101113721_acquisition_original_review_support.sql'

def identity(n):return f'af143000-0000-4000-8000-{n:012d}'


class OriginalSupportCases:
    def test_signature_original_support_internal_anchors_keep_exact_currentness_and_revocation(self):
        from acquisition_deadline_review_tests import DEADLINE_REVIEW, DEADLINE_POLICY
        self.prepare_handoff(True)
        mapping = self.renew_state_chain()
        pairs = [('deadline',DEADLINE_REVIEW),('execution',EXEC_REVIEW),
                 ('title',TITLE_REVIEW),('disposition',REVIEW)]
        for kind, root in pairs:
            for anchor in (root,mapping[root]):
                query = f"SELECT private.{kind}_review_effective_current('{anchor}',clock_timestamp())"
                self.assertEqual(self.sql(query),'t')
                for role in ('anon','authenticated','service_role'):
                    self.sql(query,user=ADMIN,role=role,fail=True)
            self.assertEqual(self.existing_current(kind,root),'f')
            self.assertEqual(self.existing_current(kind,mapping[root]),'t')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        for kind,root in pairs:
            for anchor in (root,mapping[root]):
                self.assertEqual(self.sql(f"SELECT private.{kind}_review_effective_current('{anchor}',clock_timestamp())"),'f')
            self.assertEqual(self.existing_current(kind,mapping[root]),'f')

    def test_signature_original_support_renewed_anchor_canonicalizes_without_authority(self):
        self.test_signature_renewal_locks_complete_heads_without_granting_currentness()
        from acquisition_downstream_effective_tests import NEW_DATE
        from acquisition_deadline_review_tests import DEADLINE_REVIEW
        from test_acquisition_workspace import WORKSPACE_B
        self.assertEqual(json.loads(self.renewal_set(root=NEW_DATE)), [dict(
            kind='deadline_resolution', term='closing_deadline',
            root_id=DEADLINE_REVIEW, review_id=NEW_DATE)])
        self.assertEqual(self.renewal_set(root=NEW_DATE, workspace=WORKSPACE_B), '')
        for role in ('anon','authenticated','service_role'):
            self.renewal_set(root=NEW_DATE, user=ADMIN, role=role, fail=True)
        self.assertEqual(self.effective_downstream('disposition'), 'f')

    def support_expiry(self):return (datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat()
    def renew_support(self,root,n,expires):
        self.renewal_save_rpc(self.renewal_command(root,identity=identity(n),expires=expires));return identity(n)

    def test_signature_original_support_execution_binds_selected_renewed_dates_and_can_renew(self):
        findings=self.prepare_execution_bindings();self.prepare_execution();expiry=self.support_expiry()
        roots=[b['review_id'] for b in findings['deadline_reviews']]
        for n,binding in enumerate(findings['deadline_reviews'],1):binding['review_id']=self.renew_support(binding['review_id'],n,expiry)
        self.execution_review(self.execution_args(p_findings=findings,p_expires=expiry))
        self.assertTrue(self.existing_state('execution')['approval_current'])
        self.assertEqual(json.loads(self.sql(f"SELECT execution_findings FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'")),findings)
        # Another renewal cannot silently change the personal execution approval.
        self.renew_support(roots[0],3,expiry)
        self.assertFalse(self.existing_state('execution')['approval_current'])
        self.renewal_choice(EXEC_REVIEW)  # Actual SQL projection must pass typed validation.
        self.renew_support(EXEC_REVIEW,4,expiry)
        self.assertTrue(self.existing_state('execution')['approval_current'])
        self.assertEqual(self.sql(f"SELECT renewal_root_id FROM acquisition_contract_reviews WHERE id='{identity(4)}'"),EXEC_REVIEW)

    def test_signature_original_support_title_records_effective_execution_and_preserves_snapshot(self):
        self.prepare_title_review();expiry=self.support_expiry()
        execution=self.renew_support(EXEC_REVIEW,10,expiry)
        self.title_review(self.title_review_args(p_expires=expiry))
        self.assertTrue(self.existing_state('title')['approval_current'])
        original=self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{TITLE_REVIEW}'")
        deps=json.loads(original)['original_review_dependencies']
        self.assertEqual(deps,[dict(root_id=EXEC_REVIEW,review_id=execution,kind='executed_contract',term=None)])
        self.renew_support(EXEC_REVIEW,11,expiry)
        self.assertFalse(self.existing_state('title')['approval_current'])
        self.renewal_choice(TITLE_REVIEW)
        self.renew_support(TITLE_REVIEW,12,expiry)
        self.assertTrue(self.existing_state('title')['approval_current'])
        self.assertEqual(original,self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{TITLE_REVIEW}'"))
        self.assertEqual(self.sql(f"SELECT original_review_dependencies IS NULL FROM acquisition_contract_reviews WHERE id='{identity(12)}'"),'t')

    def test_signature_original_support_disposition_binds_renewed_title_and_keeps_handoff_anchor(self):
        self.prepare_disposition_review(True);expiry=self.support_expiry()
        self.renew_support(EXEC_REVIEW,20,expiry);title=self.renew_support(TITLE_REVIEW,21,expiry)
        args=self.disposition_review_args();self.disposition_review(args)
        self.assertTrue(self.existing_state('disposition')['approval_current'])
        original=self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'")
        self.assertEqual(json.loads(original)['disposition_title_review_id'],title)
        self.assertTrue(json.loads(original)['original_review_dependencies'])
        self.renew_support(TITLE_REVIEW,22,expiry)
        self.assertFalse(self.existing_state('disposition')['approval_current'])
        self.renewal_choice(REVIEW);self.renew_support(REVIEW,23,args['p_expires'])
        self.assertTrue(self.existing_state('disposition')['approval_current'])
        self.transition(self.handoff_args())
        self.assertEqual(self.sql('SELECT disposition_title_review_id FROM acquisition_contract_transitions WHERE sequence=4'),title)
        self.assertEqual(original,self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'"))

    def test_signature_original_support_rejects_supplied_snapshot_and_preserves_legacy_null(self):
        self.prepare_handoff(True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE original_review_dependencies IS NOT NULL'),'0')
        row=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{TITLE_REVIEW}'"))
        row.update(id=identity(30),sequence=2,original_review_dependencies=[dict(root_id=EXEC_REVIEW,review_id=EXEC_REVIEW,kind='executed_contract',term=None)])
        columns=self.sql("SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.acquisition_contract_reviews'::regclass AND attnum>0 AND NOT attisdropped AND attgenerated=''")
        self.sql(f"INSERT INTO acquisition_contract_reviews({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::acquisition_contract_reviews,{literal(json.dumps(row))}::jsonb)",fail=True)
        self.sql(f"UPDATE acquisition_contract_reviews SET original_review_dependencies='[]' WHERE id='{TITLE_REVIEW}'",fail=True)
        self.sql(f"SELECT private.acquisition_review_dependencies_for(r,clock_timestamp()) FROM acquisition_contract_reviews r WHERE id='{TITLE_REVIEW}'",user=ADMIN,fail=True)


class OriginalSupportTests(OriginalSupportCases,EffectiveHandoffTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(OriginalSupportTests,[n for n in OriginalSupportCases.__dict__ if n.startswith('test_signature_original_support_')]))
