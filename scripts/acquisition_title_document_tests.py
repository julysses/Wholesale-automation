"""Original title evidence intake, without title clearance or disposition authority."""
import json
from concurrent.futures import ThreadPoolExecutor
from acquisition_title_choice_tests import TitleChoiceTests
from acquisition_contract_document_tests import DRAFT,DOC_POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,CALLER,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101054305_acquisition_title_contract_documents.sql'
TITLE_FILE='af940000-0000-4000-8000-000000000001'
TITLE_POLICY='af940000-0000-4000-8000-000000000002'

class TitleDocumentCases:
    def title_capture(self,enter=True):
        self.prepare_title()
        self.sql(f"INSERT INTO private.acquisition_evidence_policies(id,workspace_id,purpose,version,retention_seconds,valid_from,valid_until,approval_ref,reviewed_by,reviewed_at) SELECT '{TITLE_POLICY}',workspace_id,'title_report',1,retention_seconds,valid_from,valid_until,approval_ref,reviewed_by,reviewed_at FROM private.acquisition_evidence_policies WHERE id='{DOC_POLICY}'")
        if enter:self.transition(self.title_args())

    def title_document(self,**kwargs):
        return self.document(**(dict(identity=TITLE_FILE,version=2,purpose='title_report',policy=TITLE_POLICY)|kwargs))

    def test_signature_title_document_exact_capture_preserves_execution_and_terms(self):
        self.title_capture()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        reviews=self.sql('SELECT count(*) FROM acquisition_contract_reviews')
        with ThreadPoolExecutor(max_workers=3) as pool:receipts=list(pool.map(lambda _:self.title_document(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in receipts),1)
        self.assertTrue(all(not r['bytes_verified'] and not r['execution_authorized'] for r in receipts))
        self.contract_object(artifact=TITLE_FILE,fail=True)
        self.assertTrue(self.contract_admission(artifact=TITLE_FILE,version=2,purpose='title_report')['admitted'])
        self.contract_object(artifact=TITLE_FILE)
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{TITLE_FILE}')",user=ADMIN))
        self.assertFalse(state['bytes_verified']);self.assertFalse(state['legal_review_approved']);self.assertFalse(state['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(reviews,self.sql('SELECT count(*) FROM acquisition_contract_reviews'))
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version,stage FROM deals WHERE id='{DRAFT}'"),'title_review|2|offer_made')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id='{TITLE_FILE}'"),'1')

    def test_signature_title_document_requires_title_entry_current_version_and_scope(self):
        self.title_capture(enter=False);self.title_document(fail=True)
        self.transition(self.title_args());self.member(target=CALLER,role='acquisition_caller')
        for kwargs in ({'version':1},{'workspace':WORKSPACE_B},{'actor':OTHER},{'actor':CALLER},{'role':'service_role'},{'aal':'aal1'},{'session':False},{'policy':DOC_POLICY}):
            self.title_document(fail=True,**kwargs)
        self.title_document()
        self.contract_admission(artifact=TITLE_FILE,version=1,purpose='title_report',fail=True)
        self.contract_admission(artifact=TITLE_FILE,version=2,purpose='purchase_contract',fail=True)
        self.contract_admission(artifact=TITLE_FILE,version=2,purpose='title_report',actor=OTHER,fail=True)
        self.contract_object(artifact=TITLE_FILE,fail=True)

    def test_signature_title_document_pause_and_retention_rechecked_at_storage(self):
        self.title_capture();self.title_document()
        self.assertTrue(self.contract_admission(artifact=TITLE_FILE,version=2,purpose='title_report')['admitted'])
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{TITLE_POLICY}'")
        self.contract_object(artifact=TITLE_FILE,fail=True)
        self.assertTrue(self.title_document()['duplicate'])
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL WHERE id='{TITLE_POLICY}'")
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.title_document()['duplicate'])
        self.contract_admission(artifact=TITLE_FILE,version=2,purpose='title_report',fail=True)
        self.contract_object(artifact=TITLE_FILE,fail=True)

    def test_signature_title_document_operator_capture_does_not_grant_review_or_export(self):
        self.title_capture();self.member();self.title_document(actor=OPERATOR)
        self.assertTrue(self.contract_admission(artifact=TITLE_FILE,version=2,purpose='title_report',actor=OPERATOR)['admitted'])
        self.contract_object(artifact=TITLE_FILE,actor=OTHER,fail=True)
        self.contract_object(artifact=TITLE_FILE,actor=OPERATOR)
        self.assertEqual(self.sql("SET storage.operation='object.list'; SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=OPERATOR),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews',user=OPERATOR),'0')
        self.title_choice(actor=OPERATOR,fail=True)

class TitleDocumentTests(TitleDocumentCases,TitleChoiceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(TitleDocumentTests,test_names=[n for n in TitleDocumentCases.__dict__ if n.startswith('test_signature_title_document_')]))
