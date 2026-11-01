"""Private exit-specific policy binding without changing historical title policy."""
import json
from acquisition_disposition_source_tests import DispositionSourceTests
from acquisition_disposition_storage_tests import POLICY
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_title_storage_tests import TITLE_POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101080541_acquisition_disposition_policy_scope.sql'

class DispositionPolicyCases:
    def disposition_scope(self,row,assignment=False,**changes):
        value=dict(policy_id=POLICY,workspace_id=WORKSPACE,reviewer_id=ADMIN,
            exit_type='wholesale_assignment' if assignment else 'principal_acquisition',
            legal_source_id=row['artifact_id'] if assignment else None,reviewed_by=ADMIN,approval_ref=POLICY,
            valid_from=self.sql("SELECT clock_timestamp()-interval '1 minute'"),
            valid_until=self.sql("SELECT clock_timestamp()+interval '1 hour'"),revoked_at=None)
        return value|changes

    def insert_disposition_scope(self,value,fail=False):
        return self.sql('INSERT INTO private.acquisition_disposition_policy_scopes ('+','.join(value)+') VALUES ('+
            ','.join('NULL' if x is None else literal(x) for x in value.values())+')',fail=fail)

    def disposition_policy_snapshot(self):
        return self.sql(f"SELECT jsonb_build_object('reviewer',to_jsonb(p),'scope',to_jsonb(s)) FROM private.acquisition_contract_review_policies p JOIN private.acquisition_disposition_policy_scopes s ON s.policy_id=p.id WHERE p.id='{POLICY}'")

    def policy_current(self,snapshot,workspace=WORKSPACE,actor=ADMIN,exit_type='principal_acquisition',at='clock_timestamp()'):
        return self.sql(f"SELECT private.disposition_policy_current('{workspace}','{POLICY}','{actor}',{literal(exit_type)},{at},{literal(snapshot)}::jsonb)")

    def test_signature_disposition_policy_preserves_existing_title_and_requires_exact_scope(self):
        row=self.prepare_disposition_storage()
        before=self.sql(f"SELECT to_jsonb(p) FROM private.acquisition_contract_review_policies p WHERE id='{TITLE_POLICY}'")
        self.assertEqual(self.sql(f"SELECT private.title_review_current('{TITLE_REVIEW}',clock_timestamp())"),'t')
        self.assertEqual(self.policy_current('{}'),'f')
        self.insert_disposition_scope(self.disposition_scope(row))
        snapshot=self.disposition_policy_snapshot();self.assertEqual(self.policy_current(snapshot),'t')
        for patch in ({'workspace':WORKSPACE_B},{'actor':OTHER},{'exit_type':'wholesale_assignment'},{'at':"'infinity'::timestamptz"},{'at':'NULL::timestamptz'}):
            self.assertEqual(self.policy_current(snapshot,**patch),'f')
        self.assertEqual(self.policy_current(json.dumps(json.loads(snapshot)|{'extra':True})),'f')
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(p) FROM private.acquisition_contract_review_policies p WHERE id='{TITLE_POLICY}'"))
        self.assertEqual(self.sql(f"SELECT private.title_review_current('{TITLE_REVIEW}',clock_timestamp())"),'t')

    def test_signature_disposition_policy_assignment_source_and_tenant_constraints(self):
        row=self.prepare_disposition_storage(True);value=self.disposition_scope(row,True)
        for patch in ({'legal_source_id':None},{'legal_source_id':POLICY},{'exit_type':'principal_acquisition'},
            {'workspace_id':WORKSPACE_B},{'reviewer_id':OTHER},{'policy_id':TITLE_POLICY},
            {'valid_from':'infinity'},{'valid_until':'infinity'},{'valid_until':value['valid_from']}):
            self.insert_disposition_scope(value|patch,fail=True)
        self.insert_disposition_scope(value)
        self.assertEqual(self.policy_current(self.disposition_policy_snapshot(),exit_type='wholesale_assignment'),'t')
        # Existing original findings remain valid; a policy selector alone grants no review.
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='disposition_findings'"),'0')

    def test_signature_disposition_policy_revocation_changes_and_time_bounds(self):
        row=self.prepare_disposition_storage();self.insert_disposition_scope(self.disposition_scope(row))
        snapshot=self.disposition_policy_snapshot()
        for table in ('acquisition_contract_review_policies','acquisition_disposition_policy_scopes'):
            key='id' if table=='acquisition_contract_review_policies' else 'policy_id'
            self.sql(f"UPDATE private.{table} SET revoked_at=clock_timestamp() WHERE {key}='{POLICY}'")
            self.assertEqual(self.policy_current(snapshot),'f');self.assertEqual(self.policy_current(self.disposition_policy_snapshot()),'f')
            self.sql(f"UPDATE private.{table} SET revoked_at=NULL WHERE {key}='{POLICY}'")
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET approval_ref='{OTHER}' WHERE policy_id='{POLICY}'")
        self.assertEqual(self.policy_current(snapshot),'f')
        current=self.disposition_policy_snapshot();self.assertEqual(self.policy_current(current),'t')
        self.assertEqual(self.policy_current(current,at="clock_timestamp()+interval '2 hours'"),'f')
        self.assertEqual(self.policy_current(current,at="clock_timestamp()-interval '2 hours'"),'f')

    def test_signature_disposition_policy_private_access_and_snapshot_shape(self):
        row=self.prepare_disposition_storage();self.insert_disposition_scope(self.disposition_scope(row))
        snapshot=self.disposition_policy_snapshot()
        for role in ('anon','authenticated','service_role'):
            for command in ('SELECT * FROM','DELETE FROM','TRUNCATE'):
                self.sql(f'{command} private.acquisition_disposition_policy_scopes',user=ADMIN,role=role,fail=True)
            self.sql(f"SELECT private.disposition_policy_current('{WORKSPACE}','{POLICY}','{ADMIN}','principal_acquisition',clock_timestamp(),'{snapshot}'::jsonb)",user=ADMIN,role=role,fail=True)
        self.assertEqual(self.sql("SELECT relrowsecurity FROM pg_class WHERE oid='private.acquisition_disposition_policy_scopes'::regclass"),'t')
        for bad in ([],{},dict(reviewer={},scope=None),dict(reviewer=[],scope={})):
            self.insert_title_fixture(row|dict(disposition_policy_snapshot=bad),fail=True)
        self.insert_title_fixture(row|dict(disposition_policy_snapshot=json.loads(snapshot)))

class DispositionPolicyTests(DispositionPolicyCases,DispositionSourceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionPolicyTests,[n for n in DispositionPolicyCases.__dict__ if n.startswith('test_signature_disposition_policy_')]))
