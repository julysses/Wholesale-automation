"""Sourced immutable draft versions on an isolated PostgreSQL database."""
import copy
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from acquisition_contract_review_candidate_tests import ContractReviewCandidateTests
from acquisition_contract_document_tests import DOCUMENT, DRAFT, SECOND
from test_acquisition_workspace import ROOT, PG, main, ADMIN, OTHER, WORKSPACE, WORKSPACE_B, literal

MIGRATION = ROOT/'frontend/supabase/migrations/20261101004230_acquisition_contract_terms.sql'
REQUEST = 'af100000-0000-4000-8000-000000000001'

class ContractTermsCases:
    def terms(self):
        return dict(purchase_price_cents=20000000, earnest_money_cents=100000,
                    assignment_allowed=False, assignment_provisions='Assignment requires written consent.',
                    effective={'precision':'date','calendar_date':'2026-11-01'},
                    inspection_deadline={'precision':'unknown'}, closing_deadline={'precision':'unknown'},
                    sources=[dict(term=term,artifact_id=DOCUMENT,artifact_version=1,sha256='b'*64,locator='Section 1')
                             for term in ('purchase_price','earnest_money','assignment','effective')],
                    note='Terms transcribed from the exact synthetic source document.')

    def save_terms(self, terms=None, request=REQUEST, version=1, actor=ADMIN, workspace=WORKSPACE, fail=False, **kwargs):
        value=self.sql(f"SELECT public.save_contract_terms('{request}','{workspace}','{DRAFT}',{version},{literal(json.dumps(self.terms() if terms is None else terms))}::jsonb)",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_terms_exact_concurrent_retry_and_immutable_source(self):
        before=self.sql('SELECT (SELECT count(*) FROM acquisition_evidence_artifacts),(SELECT count(*) FROM acquisition_evidence_verifications)')
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _: self.save_terms(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(r['version']==2 and not r['execution_authorized'] for r in results))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_term_sources'),'4')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_terms'"),'1')
        self.assertEqual(self.sql('SELECT (SELECT count(*) FROM acquisition_evidence_artifacts),(SELECT count(*) FROM acquisition_evidence_verifications)'),before)
        self.save_terms(request=SECOND,fail=True)
        self.assertEqual(self.save_terms(request=SECOND,version=2)['version'],3)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.save_terms()['duplicate'])
        self.assertEqual(self.sql(f"SELECT terms->'inspection_deadline'->>'precision' FROM acquisition_contract_versions WHERE id='{REQUEST}'"),'unknown')

    def test_terms_no_approval_carryover(self):
        self.review();self.assertTrue(self.review_state()['approval_current'])
        self.save_terms()
        self.assertFalse(self.review_state()['approval_current'])
        self.assertTrue(self.review()['duplicate'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews'),'1')

    def test_terms_scope_and_raw_mutation_denied(self):
        for change in ({'actor':OTHER},{'workspace':WORKSPACE_B},{'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.save_terms(fail=True,**change)
        self.save_terms()
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_term_sources',user=OTHER),'0')
        for query in ('DELETE FROM acquisition_contract_term_sources','UPDATE acquisition_contract_versions SET terms=NULL',f"UPDATE deals SET acquisition_version=3 WHERE id='{DRAFT}'"):
            self.sql(query,fail=True)
            self.sql(query,user=ADMIN,role='service_role',fail=True)

    def test_terms_invalid_values_and_source_rejected(self):
        changes=[{'purchase_price_cents':0},{'purchase_price_cents':'20000000'}, {'purchase_price_cents':True},
                 {'purchase_price_cents':9007199254740992},{'sources':[]}, {'note':'short'},
                 {'effective':{'precision':'date','calendar_date':'2026-02-30'}},
                 {'effective':{'precision':'instant','instant':'2026-11-01T12:00:00'}},
                 {'effective':{'precision':None}}]
        for change in changes:
            with self.subTest(change=change): self.save_terms(self.terms()|change,fail=True)
        for change in ({'artifact_id':SECOND},{'artifact_version':2},{'sha256':'c'*64},{'locator':None},{'term':None}):
            value=copy.deepcopy(self.terms());value['sources'][0].update(change)
            self.save_terms(value,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_term_sources'),'0')

    def test_terms_canonical_source_lock_rechecks_revocation(self):
        # UUID spelling must not evade the artifact lock used by revocation.
        terms=self.terms()
        for source in terms['sources']: source['artifact_id']=source['artifact_id'].upper()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
                                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:{DOCUMENT}',0)); END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5; locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED': locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.save_terms,terms,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.save_contract_terms%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write("UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp(); COMMIT;\n");holder.stdin.flush()
                finally:
                    holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_term_sources'),'0')
        finally: holder.communicate('\\q\n',timeout=5)

    def test_terms_revoked_source_rejected(self):
        self.revoke_document();self.save_terms(fail=True)
        self.assertEqual(self.sql(f"SELECT acquisition_version FROM deals WHERE id='{DRAFT}'"),'1')

class ContractTermsTests(ContractTermsCases,ContractReviewCandidateTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ContractTermsTests,test_names=[n for n in ContractTermsCases.__dict__ if n.startswith('test_terms_')]))
