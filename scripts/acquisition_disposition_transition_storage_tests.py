"""Disposition handoff ledger binds the exact approved original dependency chain."""
import json
from acquisition_disposition_candidate_tests import DispositionCandidateTests
from acquisition_disposition_review_tests import REVIEW,HOLD
from acquisition_disposition_plan_tests import PLAN
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101085153_acquisition_disposition_transition_storage.sql'
TRANSITION='af118000-0000-4000-8000-000000000001'

class DispositionTransitionStorageCases:
    def disposition_transition_fixture(self,assignment=False,held=False):
        self.prepare_disposition_review(assignment)
        self.disposition_review(self.disposition_review_args(**(dict(p_status='requires_resolution',p_expires=None) if held else {})))
        row=json.loads(self.sql('SELECT to_jsonb(t) FROM acquisition_contract_transitions t WHERE sequence=3'))
        original=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'"))
        row.update(id=TRANSITION,sequence=4,previous_status='title_review',recorded_status='disposition_review',
            disposition_review_id=REVIEW,disposition_plan_id=PLAN,disposition_exit_type=original['disposition_exit_type'],
            disposition_execution_id=original['disposition_execution_id'],disposition_title_entry_id=original['disposition_title_entry_id'],
            disposition_title_review_id=TITLE_REVIEW)
        return row

    def insert_disposition_transition_fixture(self,row,**kwargs):
        columns=self.sql("SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.acquisition_contract_transitions'::regclass AND attnum>0 AND NOT attisdropped AND attgenerated=''")
        return self.sql(f"INSERT INTO acquisition_contract_transitions({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::acquisition_contract_transitions,{literal(json.dumps(row))}::jsonb)",**kwargs)

    def test_signature_disposition_transition_storage_exact_original_and_no_canonical_change(self):
        row=self.disposition_transition_fixture(True);before=self.sql(f"SELECT to_jsonb(d) FROM deals d WHERE id='{DRAFT}'")
        for key,value in [('disposition_review_id',HOLD),('disposition_plan_id',HOLD),('disposition_exit_type','principal_acquisition'),
            ('disposition_execution_id',row['disposition_title_entry_id']),('disposition_title_entry_id',row['disposition_execution_id']),
            ('disposition_title_review_id',EXEC_REVIEW),('contract_version',1),('workspace_id',WORKSPACE_B),('execution_review_id',TITLE_REVIEW),
            ('sequence',5),('previous_status','executed')]:
            self.insert_disposition_transition_fixture(row|{key:value},fail=True)
        for key in ['disposition_review_id','disposition_plan_id','disposition_exit_type','disposition_execution_id','disposition_title_entry_id','disposition_title_review_id','execution_review_id','execution_review_kind']:
            self.insert_disposition_transition_fixture(row|{key:None},fail=True)
        alternate=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{EXEC_REVIEW}'"))
        self.insert_title_fixture(alternate|dict(id=HOLD,sequence=2))
        self.insert_disposition_transition_fixture(row|dict(execution_review_id=HOLD),fail=True)
        self.insert_disposition_transition_fixture(row)
        stored=json.loads(self.sql(f"SELECT to_jsonb(t) FROM acquisition_contract_transitions t WHERE id='{TRANSITION}'"))
        self.assertEqual(stored['disposition_review_status'],'approved');self.assertEqual(stored['disposition_title_status'],'approved')
        self.assertEqual(stored['disposition_execution_status'],'executed');self.assertEqual(stored['execution_review_id'],EXEC_REVIEW)
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(d) FROM deals d WHERE id='{DRAFT}'"))
        self.sql(f"UPDATE deals SET acquisition_status='disposition_review' WHERE id='{DRAFT}'",fail=True)
        self.sql(f"UPDATE acquisition_contract_transitions SET reason='Replace this original reviewed handoff record' WHERE id='{TRANSITION}'",fail=True)
        self.sql(f"DELETE FROM acquisition_contract_transitions WHERE id='{TRANSITION}'",fail=True)

    def test_signature_disposition_transition_storage_rejects_held_original_and_writer_activation(self):
        row=self.disposition_transition_fixture(held=True);self.insert_disposition_transition_fixture(row,fail=True)
        self.sql(f"SELECT public.record_contract_transition('{TRANSITION}','{WORKSPACE}','{DRAFT}',2,3,'title_review','disposition_review','Attempt handoff without the controlled writer enabled')",user=ADMIN,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.assertEqual(self.sql(f"SELECT acquisition_status FROM deals WHERE id='{DRAFT}'"),'title_review')

    def test_signature_disposition_transition_storage_preserves_rls_and_no_direct_writes(self):
        row=self.disposition_transition_fixture();self.insert_disposition_transition_fixture(row);self.member()
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_transitions WHERE id='{TRANSITION}'",user=ADMIN),'1')
        for actor in (OTHER,OPERATOR):self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_transitions WHERE id='{TRANSITION}'",user=actor),'0')
        for kwargs in ({'aal':'aal1'},{'session':False}):self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_transitions WHERE id='{TRANSITION}'",user=ADMIN,**kwargs),'0')
        for role in ('authenticated','service_role','anon'):
            self.insert_disposition_transition_fixture(row|dict(id=HOLD),user=ADMIN,role=role,fail=True)
            self.sql('TRUNCATE acquisition_contract_transitions',user=ADMIN,role=role,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions WHERE sequence<=3 AND disposition_review_id IS NOT NULL'),'0')

class DispositionTransitionStorageTests(DispositionTransitionStorageCases,DispositionCandidateTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionTransitionStorageTests,[n for n in DispositionTransitionStorageCases.__dict__ if n.startswith('test_signature_disposition_transition_storage_')]))
