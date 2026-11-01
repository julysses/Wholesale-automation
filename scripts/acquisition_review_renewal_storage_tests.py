"""Renewal storage preserves immutable roots, exact streams and client isolation."""
import json,subprocess,select,time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from acquisition_disposition_transition_choice_tests import DispositionTransitionChoiceTests
from acquisition_disposition_review_tests import REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,WORKSPACE_B,PG,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101093742_acquisition_review_renewal_lineage.sql'
FIRST='af128000-0000-4000-8000-000000000001'
SECOND='af128000-0000-4000-8000-000000000002'

class ReviewRenewalStorageCases:
    def renewal_row(self,root=REVIEW,**changes):
        row=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{root}'"))
        seq=int(self.sql(f"SELECT max(sequence) FROM acquisition_contract_reviews WHERE contract_id='{row['contract_id']}' AND kind='{row['kind']}'"))
        return row|dict(id=FIRST,sequence=seq+1,renewal_root_id=root,renewal_previous_id=root)|changes

    def test_signature_review_renewal_storage_keeps_originals_and_rejects_forks(self):
        self.prepare_handoff()
        before=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        original=self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'")
        row=self.renewal_row();self.insert_title_fixture(row)
        self.insert_title_fixture(row|dict(id=SECOND,sequence=row['sequence']+1),fail=True)
        self.insert_title_fixture(row|dict(id=SECOND,sequence=row['sequence']+1,renewal_previous_id=FIRST))
        self.assertEqual(original,self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'"))
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t'))
        self.sql(f"UPDATE acquisition_contract_reviews SET renewal_root_id=id WHERE id='{FIRST}'",fail=True)
        self.sql(f"DELETE FROM acquisition_contract_reviews WHERE id='{FIRST}'",fail=True)

    def test_signature_review_renewal_storage_rejects_scope_kind_partial_lineage_and_changed_facts(self):
        self.prepare_handoff();row=self.renewal_row()
        for patch in ({'workspace_id':WORKSPACE_B},{'contract_version':1},{'renewal_root_id':TITLE_REVIEW},
            {'renewal_previous_id':EXEC_REVIEW},{'renewal_previous_id':None},{'renewal_root_id':None},
            {'renewal_root_id':FIRST},{'sequence':row['sequence']+1},{'renewal_previous_id':SECOND}):
            self.insert_title_fixture(row|patch,fail=True)
        bad=deepcopy(row);bad['disposition_findings']['contractual_interest']['note']='Changed substantive conclusion for this original property agreement.'
        self.insert_title_fixture(bad,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL'),'0')

    def test_signature_review_renewal_storage_rejects_superseded_or_withdrawn_chain(self):
        self.prepare_handoff();row=self.renewal_row()
        self.disposition_review(self.disposition_review_args(p_id=SECOND,p_expected_sequence=1))
        self.insert_title_fixture(row|dict(sequence=3),fail=True)
        self.disposition_review(self.disposition_review_args(p_id=FIRST,p_expected_sequence=2,p_status='withdrawn',p_expires=None,p_personally_reviewed=False,p_original_review=SECOND,p_findings=None))
        self.insert_title_fixture(row|dict(id='af128000-0000-4000-8000-000000000003',sequence=4,renewal_root_id=SECOND,renewal_previous_id=SECOND),fail=True)

    def test_signature_review_renewal_storage_all_kinds_and_shared_deadline_sequence(self):
        self.prepare_handoff()
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution' AND status='approved'"))
        self.assertGreaterEqual(len(roots),2)
        roots += [EXEC_REVIEW,TITLE_REVIEW]
        for i,root in enumerate(roots,10):
            row=self.renewal_row(root,id=f'af128000-0000-4000-8000-{i:012d}')
            if row['kind']=='deadline_resolution':
                wrong='effective' if row['deadline_term']!='effective' else 'closing_deadline'
                self.insert_title_fixture(row|dict(deadline_term=wrong),fail=True)
            self.insert_title_fixture(row)
        self.assertEqual(int(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL')),len(roots))

    def test_signature_review_renewal_storage_wait_observes_withdrawal(self):
        self.prepare_handoff();row=self.renewal_row()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,'-U','test_admin',
            '-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            claims=json.dumps(dict(sub=ADMIN,aal='aal2',role='authenticated',session_id=ADMIN))
            holder.stdin.write(f"BEGIN; SET ROLE authenticated; SET request.jwt.claims={literal(claims)}; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:{row['contract_id']}',0)); END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.insert_title_fixture,row,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE 'INSERT INTO acquisition_contract_reviews%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    args=self.disposition_review_args(p_id=SECOND,p_expected_sequence=1,p_status='withdrawn',p_expires=None,
                        p_personally_reviewed=False,p_original_review=REVIEW,p_findings=None)
                    holder.stdin.write(self.disposition_review_query(args)+"; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                self.assertIn('Latest unsuperseded review',future.result(timeout=5))
        finally:holder.communicate('\\q\n',timeout=5)
        self.assertEqual(self.sql(f"SELECT status FROM acquisition_contract_reviews WHERE id='{SECOND}'"),'withdrawn')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL'),'0')

    def test_signature_review_renewal_storage_client_cannot_insert(self):
        self.prepare_handoff();row=self.renewal_row()
        for role in ('anon','authenticated','service_role'):
            self.insert_title_fixture(row,fail=True,role=role,user=ADMIN)

class ReviewRenewalStorageTests(ReviewRenewalStorageCases,DispositionTransitionChoiceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(ReviewRenewalStorageTests,[n for n in ReviewRenewalStorageCases.__dict__ if n.startswith('test_signature_review_renewal_')]))
