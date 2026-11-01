"""Calendar interpretation storage, original approval integrity and inherited access."""
import json
from copy import deepcopy
from acquisition_executed_choice_tests import ExecutedChoiceTests
from acquisition_contract_review_tests import POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101040743_acquisition_deadline_resolution_storage.sql'
DEADLINE_POLICY='af820000-0000-4000-8000-000000000001'
DEADLINE_REVIEW='af820000-0000-4000-8000-000000000002'


class DeadlineStorageCases:
    def deadline_proposal(self):
        original=json.loads(self.sql('SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE contract_version=2'))
        return dict(term='closing_deadline',calendar_date='2026-11-20',local_time='17:00:00',
            time_zone='America/Chicago',resolved_instant='2026-11-20T17:00:00-06:00',
            basis='explicit_document_time',rationale='Synthetic explicit time interpretation for storage verification only.',
            source=dict(term='closing_deadline',artifact_id=original['artifact_id'],artifact_version=original['source_version'],
                        sha256=original['sha256'],locator='Page 8 closing provision'))

    def valid_deadline(self,value,version=2):
        return self.sql(f'SELECT private.valid_deadline_resolution({literal(json.dumps(value))}::jsonb,{version})')

    def deadline_row(self):
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id','{DEADLINE_POLICY}','kind','deadline_resolution'))).* FROM private.acquisition_contract_review_policies p WHERE id='{POLICY}'")
        row=json.loads(self.sql('SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE contract_version=2'))
        row.update(id=DEADLINE_REVIEW,kind='deadline_resolution',policy_id=DEADLINE_POLICY,sequence=1,
                   deadline_term='closing_deadline',deadline_resolution=self.deadline_proposal(),deadline_original_review_id=None)
        return row

    def insert_deadline_row(self,value,fail=False):
        columns=self.sql("SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.acquisition_contract_reviews'::regclass AND attnum>0 AND NOT attisdropped AND attgenerated=''")
        return self.sql(f"INSERT INTO acquisition_contract_reviews({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::acquisition_contract_reviews,{literal(json.dumps(value))}::jsonb)",fail=fail)

    def test_signature_deadline_storage_validates_offsets_and_dst_without_defaults(self):
        value=self.deadline_proposal();self.assertEqual(self.valid_deadline(value),'t')
        for offset in ('-05:00','-06:00'):
            repeated=value|dict(calendar_date='2026-11-01',local_time='01:30:00',resolved_instant='2026-11-01T01:30:00'+offset)
            self.assertEqual(self.valid_deadline(repeated),'t')
        for change in (
            {'resolved_instant':'2026-11-20T17:00:00-05:00'}, {'resolved_instant':'2026-11-20T17:00:00'},
            {'calendar_date':'2026-03-08','local_time':'02:30:00','resolved_instant':'2026-03-08T02:30:00-06:00'},
            {'calendar_date':'2026-02-30','resolved_instant':'2026-02-30T17:00:00-06:00'},
            {'local_time':'24:00:00'}, {'local_time':'17:00'}, {'time_zone':'Unknown/Zone'},
            {'time_zone':None}, {'basis':None}, {'term':None}, {'rationale':' '*20},
            {'execution_authorized':True}, {'source':None}, {'source':{}},
        ):
            self.assertEqual(self.valid_deadline(value|change),'f',change)
        for change in ({'term':'effective'},{'artifact_version':3},{'artifact_version':True},
                       {'artifact_version':1.5},{'sha256':None},{'locator':'\n'},{'artifact_id':'not-a-uuid'}):
            changed=deepcopy(value);changed['source'].update(change)
            self.assertEqual(self.valid_deadline(changed),'f',change)
        self.assertEqual(self.valid_deadline(None),'f')
        self.assertEqual(self.valid_deadline(value,0),'f')

    def test_signature_deadline_storage_binds_original_approval_to_exact_term(self):
        row=self.deadline_row();self.insert_deadline_row(row)
        second=deepcopy(row);second.update(id='af820000-0000-4000-8000-000000000003',sequence=2,deadline_term='effective')
        second['deadline_resolution']['term']='effective';second['deadline_resolution']['source']['term']='effective'
        self.insert_deadline_row(second)
        withdrawn=row|dict(id='af820000-0000-4000-8000-000000000004',sequence=3,status='withdrawn',
            personally_reviewed=False,expires_at=None,deadline_resolution=None,deadline_original_review_id=DEADLINE_REVIEW)
        self.insert_deadline_row(withdrawn|{'deadline_term':'effective'},fail=True)
        self.insert_deadline_row(withdrawn|{'deadline_original_review_id':withdrawn['id']},fail=True)
        self.insert_deadline_row(withdrawn|{'deadline_original_review_id':None},fail=True)
        self.insert_deadline_row(withdrawn|{'contract_version':1},fail=True)
        self.insert_deadline_row(withdrawn)
        self.insert_deadline_row(withdrawn|dict(id='af820000-0000-4000-8000-000000000005',sequence=4,
            deadline_original_review_id=withdrawn['id']),fail=True)
        self.assertEqual(self.sql(f"SELECT deadline_original_status FROM acquisition_contract_reviews WHERE id='{withdrawn['id']}'"),'approved')
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"),'3')

    def test_signature_deadline_storage_preserves_scope_immutable_history_and_old_rpc(self):
        before=self.sql("SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r")
        self.review(self.review_args(p_kind='deadline_resolution',p_version=2),fail=True)
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r'))
        row=self.deadline_row();self.insert_deadline_row(row)
        for user in (OTHER,OPERATOR):
            self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'",user=user),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'",user=ADMIN,aal='aal1'),'0')
        self.sql(f"UPDATE acquisition_contract_reviews SET deadline_term='effective' WHERE id='{DEADLINE_REVIEW}'",fail=True)
        self.sql(f"DELETE FROM acquisition_contract_reviews WHERE id='{DEADLINE_REVIEW}'",fail=True)
        for role in ('authenticated','service_role','anon'):
            self.sql('INSERT INTO acquisition_contract_reviews(id) VALUES(gen_random_uuid())',user=ADMIN,role=role,fail=True)
            self.sql("SELECT private.valid_deadline_resolution('{}',2)",user=ADMIN,role=role,fail=True)

    def test_signature_deadline_storage_rejects_mixed_row_sources_and_other_kinds(self):
        row=self.deadline_row()
        for change in ({'deadline_term':None},{'deadline_resolution':None}, {'deadline_term':'effective'},
                       {'deadline_original_review_id':DEADLINE_REVIEW}, {'kind':'contract_review','policy_id':POLICY}):
            self.insert_deadline_row(row|change,fail=True)
        for field,value in (('sha256','b'*64),('artifact_id','af820000-0000-4000-8000-000000000099'),('artifact_version',1)):
            changed=deepcopy(row);changed['deadline_resolution']['source'][field]=value
            if value != row['deadline_resolution']['source'][field]:
                self.insert_deadline_row(changed,fail=True)
        self.insert_deadline_row(row)


class DeadlineStorageTests(DeadlineStorageCases,ExecutedChoiceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(DeadlineStorageTests,test_names=[n for n in DeadlineStorageCases.__dict__ if n.startswith('test_signature_deadline_storage_')]))
