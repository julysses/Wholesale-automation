"""Post-handoff signed-observation rehearsal, not a live scanner/Storage claim."""
import json
from acquisition_downstream_effective_tests import DownstreamEffectiveTests
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_title_storage_tests import TITLE_FILE
from acquisition_disposition_review_tests import REVIEW
from acquisition_contract_document_tests import DOCUMENT,DRAFT
from acquisition_contract_observation_tests import OBS
from test_acquisition_workspace import main,WORKSPACE,ADMIN
SCAN='af135000-0000-4000-8000-000000000001'
SECOND_SCAN='af135000-0000-4000-8000-000000000002'
NEW_FILE='af135000-0000-4000-8000-000000000003'

class RetainedRefreshCases:
    def post_handoff(self):
        self.prepare_handoff(True);self.transition(self.handoff_args())

    def test_signature_retained_refresh_handoff_preserves_history_and_denies_new_upload(self):
        self.post_handoff()
        before=self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r')
        signed=self.signed_contract(request=SCAN)
        saved=self.record_contract_scan(signed);self.assertFalse(saved['duplicate'])
        self.assertEqual((saved['artifact_id'],saved['contract_version']),(DOCUMENT,1))
        self.assertTrue(self.record_contract_scan(signed)['duplicate'])
        self.assertFalse(saved['legal_review_approved']);self.assertFalse(saved['execution_authorized'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_evidence_verification' AND entity_id='{SCAN}'"),'1')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r'))
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'disposition_review')
        self.document(identity=NEW_FILE,version=2,fail=True)
        self.contract_admission(artifact=TITLE_FILE,version=2,purpose='title_report',fail=True)
        self.assertEqual(self.effective_execution(),'f')
        self.assertEqual(self.effective_downstream('disposition'),'f')

    def test_signature_retained_refresh_same_bytes_requires_each_new_personal_review(self):
        self.post_handoff();transitions=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        terms=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.record_contract_scan(self.signed_contract(request=SCAN))
        self.assertEqual(self.effective_downstream('disposition'),'f')
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution' AND status='approved'"))
        roots += [EXEC_REVIEW,TITLE_REVIEW,REVIEW]
        for i,root in enumerate(roots,10):
            row=self.renewal_row(root,id=f'af135000-0000-4000-8000-{i:012d}')
            if row['artifact_id']==DOCUMENT:row['verification_id']=SCAN
            for key in ('deadline_sources','execution_sources','title_sources','disposition_sources'):
                for source in row.get(key) or []:
                    if source['artifact_id']==DOCUMENT:source['verification_id']=SCAN
            self.insert_title_fixture(row) # Privileged synthetic fixture, not a renewal endpoint.
            if root!=REVIEW:self.assertEqual(self.effective_downstream('disposition'),'f')
        self.assertEqual(self.effective_execution(),'t');self.assertEqual(self.effective_downstream(),'t')
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.assertEqual(transitions,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t'))
        self.assertEqual(terms,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql(f"SELECT verification_id FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"),OBS)
        self.record_contract_scan(self.signed_contract(request=SECOND_SCAN,scan_status='detected'))
        self.assertEqual(self.effective_downstream('disposition'),'f')

    def test_signature_retained_refresh_changed_bytes_and_revoked_scanner_rejected_retry_retained(self):
        self.post_handoff();signed=self.signed_contract(request=SCAN);self.record_contract_scan(signed)
        self.record_contract_scan(self.signed_contract(request=SECOND_SCAN,sha256='e'*64),fail=True)
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.record_contract_scan(self.signed_contract(request=SECOND_SCAN),fail=True)
        self.assertTrue(self.record_contract_scan(signed)['duplicate'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_evidence_verifications WHERE id='{SECOND_SCAN}'"),'0')

class RetainedRefreshTests(RetainedRefreshCases,DownstreamEffectiveTests):
    pass

if __name__=='__main__':raise SystemExit(main(RetainedRefreshTests,[n for n in RetainedRefreshCases.__dict__ if n.startswith('test_signature_retained_refresh_')]))
