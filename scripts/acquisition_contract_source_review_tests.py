"""Fresh human reviews bind changed targets to original retained evidence."""
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from acquisition_contract_document_link_tests import ContractDocumentLinkTests,LINK
from acquisition_contract_document_tests import DOCUMENT,DRAFT,SECOND
from acquisition_contract_review_tests import REVIEW
from test_acquisition_workspace import ROOT,PG,main,ADMIN,OTHER,WORKSPACE,WORKSPACE_B,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101010937_acquisition_contract_review_source_versions.sql'
NEW_REVIEW='af300000-0000-4000-8000-000000000001'
WITHDRAWAL='af300000-0000-4000-8000-000000000002'
NEXT_REVIEW='af300000-0000-4000-8000-000000000003'

class ContractSourceReviewCases:
    def source_review_args(self,**changes):
        return self.review_args(p_id=NEW_REVIEW,p_version=2)|changes

    def test_source_review_terms_require_new_decision_and_keep_old_retry(self):
        self.review();self.save_terms()
        self.assertEqual(self.review_state(version=2)['status'],'not_reviewed')
        choice=self.candidate(version=2)
        self.assertEqual(choice['status'],'ready_for_human_review')
        result=self.review(self.source_review_args())
        self.assertEqual(result['contract_version'],2);self.assertFalse(result['approval_current']);self.assertFalse(result['execution_authorized'])
        self.assertTrue(self.review_state(version=2)['approval_current']);self.assertFalse(self.review_state()['approval_current'])
        self.assertEqual(self.sql(f"SELECT contract_version,source_version FROM acquisition_contract_reviews WHERE id='{NEW_REVIEW}'"),'2|1')
        self.assertTrue(self.review()['duplicate']);self.assertTrue(self.review(self.source_review_args())['duplicate'])
        self.save_terms(request=SECOND,version=2)
        self.assertFalse(self.review_state(version=2)['approval_current']);self.assertEqual(self.review_state(version=3)['status'],'not_reviewed')
        self.assertEqual(self.candidate(version=3)['status'],'ready_for_human_review')
        self.review(self.source_review_args(p_id=NEXT_REVIEW,p_version=3))
        self.assertTrue(self.review_state(version=3)['approval_current'])
        self.assertEqual(self.sql(f"SELECT source_version FROM acquisition_contract_reviews WHERE id='{NEXT_REVIEW}'"),'1')

    def test_source_review_withdrawn_link_removes_approval_not_history(self):
        self.review();self.save_terms(self.unknown_terms());self.link_document()
        self.review(self.source_review_args());self.assertTrue(self.review_state(version=2)['approval_current'])
        self.withdraw_link()
        self.assertFalse(self.review_state(version=2)['approval_current'])
        choice=self.candidate(version=2)
        self.assertEqual(choice['status'],'evidence_review_required');self.assertIsNone(choice['candidate'])
        self.assertEqual(choice['withdrawal']['review_id'],NEW_REVIEW)
        self.review(self.source_review_args(p_id=NEXT_REVIEW,p_expected_sequence=1),fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        withdrawal=self.source_review_args(p_id=WITHDRAWAL,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False)
        self.assertEqual(self.review(withdrawal)['status'],'withdrawn');self.assertTrue(self.review(withdrawal)['duplicate'])
        self.assertTrue(self.review(self.source_review_args())['duplicate'])
        self.assertEqual(self.review_state(version=2)['status'],'withdrawn')
        self.assertEqual(self.sql(f"SELECT source_version FROM acquisition_contract_reviews WHERE id='{WITHDRAWAL}'"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_revocations'),'0')

    def test_source_review_latest_scan_and_revocation_rechecked(self):
        self.review();self.save_terms();self.review(self.source_review_args())
        self.record_contract_scan(self.signed_contract(request=SECOND))
        self.assertFalse(self.review_state(version=2)['approval_current'])
        self.assertEqual(self.candidate(version=2)['candidate']['verification_id'],SECOND)
        self.review(self.source_review_args(p_id=NEXT_REVIEW,p_expected_sequence=1),fail=True)
        self.review(self.source_review_args(p_id=NEXT_REVIEW,p_expected_sequence=1,p_verification=SECOND))
        self.assertTrue(self.review_state(version=2)['approval_current'])
        self.revoke_document()
        self.assertFalse(self.review_state(version=2)['approval_current']);self.assertIsNone(self.candidate(version=2)['candidate'])

    def test_source_review_unlinked_and_foreign_sources_denied(self):
        self.review();self.save_terms(self.unknown_terms())
        self.candidate(version=2,fail=True);self.review(self.source_review_args(),fail=True)
        self.link_document()
        for change in ({'p_workspace':WORKSPACE_B},{'p_artifact':SECOND},{'p_verification':SECOND},{'p_kind':'title_review'}):
            self.review(self.source_review_args(**change),fail=True)
        for change in ({'actor':OTHER},{'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.review(self.source_review_args(),fail=True,**change)
        self.review(self.source_review_args())
        self.sql(f"UPDATE acquisition_contract_reviews SET evidence_version=2 WHERE id='{NEW_REVIEW}'",fail=True)
        self.sql(f"UPDATE acquisition_contract_reviews SET source_version=2 WHERE id='{NEW_REVIEW}'",fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews',user=OTHER),'0')

    def test_source_review_wait_observes_link_withdrawal(self):
        self.review();self.save_terms(self.unknown_terms());self.link_document()
        before=self.sql('SELECT count(*) FROM acquisition_contract_reviews')
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
                                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:{DRAFT}',0)); END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.review,self.source_review_args(),fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.record_contract_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    claims=literal(json.dumps({'sub':ADMIN,'role':'authenticated','aal':'aal2','session_id':ADMIN}))
                    holder.stdin.write(f"SET LOCAL ROLE authenticated; SET LOCAL request.jwt.claims={claims}; SELECT public.revoke_contract_document_link('{WITHDRAWAL}','{WORKSPACE}','{DRAFT}',2,'{LINK}','Synthetic reference withdrawn while review was waiting.'); COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews'),before)
            self.assertEqual(self.reference_state()['status'],'reference_withdrawn')
        finally:holder.communicate('\\q\n',timeout=5)

class ContractSourceReviewTests(ContractSourceReviewCases,ContractDocumentLinkTests):
    def setUp(self):
        super().setUp()
        self.review()
        before=self.sql('SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r')
        self.sql(MIGRATION.read_text())
        after=self.sql("SELECT jsonb_agg(to_jsonb(r)-'evidence_version'-'source_version') FROM acquisition_contract_reviews r")
        self.assertEqual(before,after)
        self.assertEqual(self.sql(f"SELECT evidence_version IS NULL,source_version FROM acquisition_contract_reviews WHERE id='{REVIEW}'"),'t|1')
        self.assertTrue(self.review()['duplicate'])

if __name__=='__main__':
    raise SystemExit(main(ContractSourceReviewTests,test_names=[n for n in ContractSourceReviewCases.__dict__ if n.startswith('test_source_review_')]))
