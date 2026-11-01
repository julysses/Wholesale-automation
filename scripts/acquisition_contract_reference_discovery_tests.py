"""Bounded original-document references across native, terms and explicit links."""
import json
from acquisition_contract_source_review_tests import ContractSourceReviewTests
from acquisition_contract_document_tests import DOCUMENT,DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101011718_acquisition_contract_reference_discovery.sql'
SECOND_DOCUMENT='ad000000-0000-4000-8000-000000000009'

class ContractReferenceDiscoveryCases:
    def references(self,version=1,purpose='purchase_contract',after=None,limit=20,workspace=WORKSPACE,actor=ADMIN,fail=False,**kwargs):
        cursor='NULL' if after is None else literal(after)
        value=self.sql(f"SELECT public.contract_reference_candidates('{workspace}','{DRAFT}',{version},{literal(purpose)},{cursor},{limit})",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_reference_discovery_original_sources_deduplicate_terms(self):
        native=self.references();self.assertEqual(native['items'][0]['reference_type'],'native')
        self.save_terms();before=self.sql('SELECT count(*) FROM audit_logs')
        page=self.references(version=2)
        self.assertEqual(len(page['items']),1);source=page['items'][0]
        self.assertEqual((source['artifact_id'],source['source_version'],source['contract_version'],source['reference_type']),(DOCUMENT,1,2,'term_source'))
        self.assertFalse(source['review_approved']);self.assertFalse(page['execution_authorized'])
        self.assertEqual(source['checked_at'],page['checked_at'])
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),before)
        self.revoke_document();self.assertEqual(self.references(version=2)['items'][0]['status'],'source_revoked')

    def test_reference_discovery_cursor_scope_and_empty_page_authority(self):
        self.document(identity=SECOND_DOCUMENT)
        page=self.references(limit=1);self.assertEqual(page['next_after'],DOCUMENT)
        page=self.references(after=DOCUMENT,limit=1);self.assertEqual(page['items'][0]['artifact_id'],SECOND_DOCUMENT);self.assertIsNone(page['next_after'])
        self.assertEqual(self.references(after=SECOND_DOCUMENT)['items'],[])
        self.assertEqual(self.references(purpose='title_report')['items'],[])
        for change in ({'actor':OTHER},{'workspace':WORKSPACE_B},{'version':3},{'purpose':'bogus'},{'limit':0},{'limit':51},{'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.references(after=SECOND_DOCUMENT,fail=True,**change)

    def test_reference_discovery_unlinked_excluded_withdrawn_retained(self):
        self.save_terms(self.unknown_terms());self.assertEqual(self.references(version=2)['items'],[])
        self.link_document();self.assertEqual(self.references(version=2)['items'][0]['reference_type'],'linked')
        self.withdraw_link();self.sql('UPDATE private.acquisition_activation SET enabled=false')
        page=self.references(version=2);self.assertEqual(page['items'][0]['status'],'reference_withdrawn')
        self.assertIsNone(page['items'][0]['verification_id']);self.assertFalse(page['items'][0]['review_approved'])

class ContractReferenceDiscoveryTests(ContractReferenceDiscoveryCases,ContractSourceReviewTests):
    def setUp(self):super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ContractReferenceDiscoveryTests,test_names=[n for n in ContractReferenceDiscoveryCases.__dict__ if n.startswith('test_reference_discovery_')]))
