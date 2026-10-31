"""Bounded contract document discovery over existing retained artifacts."""
import json
from acquisition_contract_storage_tests import ContractStorageTests
from acquisition_contract_document_tests import DOCUMENT, DOC_POLICY, DRAFT, SECOND
from test_acquisition_workspace import ROOT, main, ADMIN, OTHER, OPERATOR, CALLER, WORKSPACE, WORKSPACE_B, literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261031231924_acquisition_contract_document_discovery.sql'

class ContractDiscoveryCases:
    def document_choices(self, actor=ADMIN, workspace=WORKSPACE, contract=DRAFT, version=1,
                         purpose='purchase_contract', after=None, limit=20, fail=False, **kwargs):
        cursor='NULL' if after is None else literal(after)
        result=self.sql(f"SELECT public.contract_document_candidates('{workspace}','{contract}',{version},{literal(purpose)},{cursor},{limit})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_contract_discovery_retained_state_pagination_and_pause(self):
        self.document();self.document(identity=SECOND)
        before=self.sql('SELECT count(*) FROM audit_logs')
        first=self.document_choices(limit=1)
        ids=sorted([DOCUMENT,SECOND])
        self.assertEqual(first['items'][0]['artifact_id'],ids[0]);self.assertEqual(first['next_after'],ids[0])
        second=self.document_choices(limit=1,after=first['next_after'])
        self.assertEqual(second['items'][0]['artifact_id'],ids[1]);self.assertIsNone(second['next_after'])
        self.assertEqual(first['current_policy']['id'],DOC_POLICY)
        self.assertFalse(first['execution_authorized'])
        self.assertNotIn('provenance_note',first['items'][0]);self.assertNotIn('object_name',first['items'][0])
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),before)
        self.revoke_document();self.sql('UPDATE private.acquisition_activation SET enabled=false')
        listed=self.document_choices()
        self.assertEqual(next(row for row in listed['items'] if row['artifact_id']==DOCUMENT)['status'],'revoked')
        self.assertEqual(len(listed['items']),2)

    def test_contract_discovery_exact_target_role_session_and_bounds(self):
        self.document()
        for change in ({'workspace':WORKSPACE_B},{'contract':SECOND},{'version':2},{'version':0},
                       {'purpose':'mail_content'},{'limit':0},{'limit':51},{'actor':OTHER},
                       {'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.document_choices(fail=True,**change)
        self.member(target=CALLER,role='acquisition_caller');self.document_choices(actor=CALLER,fail=True)
        self.member();self.assertEqual(len(self.document_choices(actor=OPERATOR)['items']),1)
        self.member(status='revoked');self.document_choices(actor=OPERATOR,fail=True)
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.document_choices(fail=True)

    def test_contract_discovery_policy_missing_revoked_or_expired_is_not_invented(self):
        self.document()
        missing=self.document_choices(purpose='title_report')
        self.assertIsNone(missing['current_policy']);self.assertEqual(missing['items'],[])
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        page=self.document_choices();self.assertIsNone(page['current_policy'])
        self.assertEqual(page['items'][0]['status'],'policy_review_required')
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL,valid_until=clock_timestamp()-interval '1 second' WHERE id='{DOC_POLICY}'")
        self.assertIsNone(self.document_choices()['current_policy'])

class ContractDiscoveryTests(ContractDiscoveryCases,ContractStorageTests):
    def setUp(self):
        super().setUp()
        self.document()
        before=self.sql('SELECT jsonb_agg(to_jsonb(a)) FROM acquisition_evidence_artifacts a')
        audit=self.sql('SELECT count(*) FROM audit_logs')
        self.sql(MIGRATION.read_text())
        self.assertEqual(self.sql('SELECT jsonb_agg(to_jsonb(a)) FROM acquisition_evidence_artifacts a'),before)
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),audit)

if __name__=='__main__':
    raise SystemExit(main(ContractDiscoveryTests,test_names=[name for name in ContractDiscoveryCases.__dict__ if name.startswith('test_contract_discovery_')]))
