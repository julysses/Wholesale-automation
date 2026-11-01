"""Evidence capture after release never confirms execution or changes reviewed terms."""
import json
from concurrent.futures import ThreadPoolExecutor
from acquisition_contract_transition_tests import ContractTransitionTests
from acquisition_contract_document_tests import DRAFT,DOCUMENT,DOC_POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,CALLER,WORKSPACE,WORKSPACE_B
MIGRATION=ROOT/'frontend/supabase/migrations/20261101025323_acquisition_pending_contract_documents.sql'
SIGNED_FILE='af600000-0000-4000-8000-000000000001'
ATTEMPT='af600000-0000-4000-8000-000000000002'


class PendingDocumentCases:
    def pending_capture(self):
        self.signature();self.transition()

    def test_signature_pending_document_exact_capture_preserves_terms_and_lifecycle(self):
        self.pending_capture()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        reviews=self.sql('SELECT count(*) FROM acquisition_contract_reviews')
        with ThreadPoolExecutor(max_workers=3) as pool:
            receipts=list(pool.map(lambda _:self.document(identity=SIGNED_FILE,version=2),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in receipts),1)
        self.assertTrue(all(not r['bytes_verified'] and not r['execution_authorized'] for r in receipts))
        self.contract_object(artifact=SIGNED_FILE,fail=True)
        self.assertTrue(self.contract_admission(artifact=SIGNED_FILE,version=2,attempt=ATTEMPT)['admitted'])
        self.contract_object(artifact=SIGNED_FILE)
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{SIGNED_FILE}')",user=ADMIN))
        self.assertFalse(state['bytes_verified']);self.assertFalse(state['legal_review_approved']);self.assertFalse(state['execution_authorized'])
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(reviews,self.sql('SELECT count(*) FROM acquisition_contract_reviews'))
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version,stage FROM deals WHERE id='{DRAFT}'"),'pending_signature|2|offer_made')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id='{SIGNED_FILE}'"),'1')
        self.assertEqual(self.sql(f"SELECT contract_version FROM acquisition_evidence_artifacts WHERE id='{DOCUMENT}'"),'1')

    def test_signature_pending_document_rejects_foreign_stale_unreserved_and_session_inputs(self):
        self.pending_capture();self.member(target=CALLER,role='acquisition_caller')
        for change in ({'version':1},{'workspace':WORKSPACE_B},{'actor':OTHER},{'actor':CALLER},{'role':'service_role'}, {'aal':'aal1'},{'session':False}):
            self.document(identity=SIGNED_FILE,fail=True,**({'version':2}|change))
        self.document(identity=SIGNED_FILE,version=2)
        self.contract_admission(artifact=SIGNED_FILE,version=1,fail=True)
        self.contract_admission(artifact=SIGNED_FILE,version=2,actor=OTHER,fail=True)
        self.contract_object(artifact=SIGNED_FILE,fail=True)
        self.contract_admission(artifact=SIGNED_FILE,version=2);self.contract_object(artifact=SIGNED_FILE,actor=OTHER,fail=True)
        self.save_terms(version=2,request=ATTEMPT,fail=True)

    def test_signature_pending_document_pause_and_retention_preserve_historical_retry(self):
        self.pending_capture();self.document(identity=SIGNED_FILE,version=2)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.document(identity=SIGNED_FILE,version=2)['duplicate'])
        self.contract_admission(artifact=SIGNED_FILE,version=2,fail=True);self.contract_object(artifact=SIGNED_FILE,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=true')
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        self.contract_admission(artifact=SIGNED_FILE,version=2,fail=True)
        self.assertTrue(self.document(identity=SIGNED_FILE,version=2)['duplicate'])

    def test_signature_pending_document_operator_capture_does_not_grant_review_or_export(self):
        self.pending_capture();self.member()
        self.document(identity=SIGNED_FILE,version=2,actor=OPERATOR)
        self.contract_admission(artifact=SIGNED_FILE,version=2,actor=OPERATOR)
        self.contract_object(artifact=SIGNED_FILE,actor=OPERATOR)
        self.assertEqual(self.sql("SET storage.operation='object.list'; SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=OPERATOR),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions',user=OPERATOR),'0')
        self.transition(actor=OPERATOR,fail=True)


class PendingDocumentTests(PendingDocumentCases,ContractTransitionTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(PendingDocumentTests,test_names=[n for n in PendingDocumentCases.__dict__ if n.startswith('test_signature_pending_document_')]))
