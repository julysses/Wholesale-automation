"""Execution findings shape, inherited isolation and historical review compatibility."""
import json
from copy import deepcopy
from acquisition_pending_document_tests import PendingDocumentTests
from acquisition_contract_review_tests import REVIEW,POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101030340_acquisition_execution_findings_storage.sql'


class ExecutionStorageCases:
    def execution_findings(self):
        # Existing fixture contains the exact original term-source identities.
        terms=json.loads(self.sql('SELECT terms FROM acquisition_contract_versions WHERE version=2'))
        return {**{name:{'finding':'confirmed','locator':'Page 4, synthetic signatures',
            'note':'Synthetic reviewed finding for storage constraints only.'}
            for name in ('seller_signatures','buyer_signatures','signing_authority','complete_agreement')},'terms':terms}

    def valid_findings(self,value,version=2):
        return self.sql(f'SELECT private.valid_execution_findings({literal(json.dumps(value))}::jsonb,{version})')

    def test_signature_execution_storage_preserves_reviews_and_rejects_old_rpc_kind(self):
        self.signature();self.transition()
        rows=self.sql('SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r')
        self.assertTrue(all(row['execution_findings'] is None for row in json.loads(rows)))
        self.review(self.review_args(p_kind='executed_contract',p_version=2),fail=True)
        self.assertEqual(rows,self.sql('SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r'))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews',user=OPERATOR),'0')
        self.sql('UPDATE acquisition_contract_reviews SET execution_findings=\'{}\'',user=ADMIN,fail=True)
        self.sql('DELETE FROM acquisition_contract_reviews',user=ADMIN,fail=True)
        self.sql("UPDATE acquisition_contract_reviews SET execution_findings='{}'",fail=True)
        self.assertEqual(self.sql("SELECT acquisition_status FROM deals WHERE workspace_id='"+WORKSPACE+"'"),'pending_signature')

    def test_signature_execution_storage_validates_sources_findings_and_precision(self):
        value=self.execution_findings();self.assertEqual(self.valid_findings(value),'t')
        for name in ('seller_signatures','buyer_signatures','signing_authority','complete_agreement'):
            for bad in (None,{}, {'finding':'unknown','locator':'Page 4','note':'Synthetic unresolved signature evidence.'}):
                changed=deepcopy(value);changed[name]=bad
                self.assertEqual(self.valid_findings(changed),'f')
        for field,bad in [('execution_authorized',True),('unknown_field','value')]:
            self.assertEqual(self.valid_findings(value|{field:bad}),'f')
        changed=deepcopy(value);changed['terms']['sources'][0]['artifact_version']=3
        self.assertEqual(self.valid_findings(changed),'f')
        changed=deepcopy(value);changed['terms']['purchase_price_cents']=True
        self.assertEqual(self.valid_findings(changed),'f')
        changed=deepcopy(value);changed['terms']['effective']={'precision':'date','calendar_date':'2026-10-31'}
        self.assertEqual(self.valid_findings(changed),'t')
        changed['terms']['effective']['instant']='2026-10-31T00:00:00Z'
        self.assertEqual(self.valid_findings(changed),'f')
        self.assertEqual(self.valid_findings(None),'f')

    def test_signature_execution_storage_enforces_row_shape_and_immutable_history(self):
        policy_id='af770000-0000-4000-8000-000000000001'
        review_id='af770000-0000-4000-8000-000000000002'
        # Privileged synthetic fixture only: no application provisioning path exists.
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id','{policy_id}','kind','executed_contract'))).* FROM private.acquisition_contract_review_policies p WHERE id='{POLICY}'")
        columns=self.sql("SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.acquisition_contract_reviews'::regclass AND attnum>0 AND NOT attisdropped AND attgenerated=''")
        original=json.loads(self.sql('SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE contract_version=2'))
        original.update(id=review_id,kind='executed_contract',policy_id=policy_id,execution_findings=self.execution_findings())
        if 'execution_sources' in original:
            original['execution_sources']=[{'artifact_id':original['artifact_id'],'source_version':original['source_version'],'verification_id':original['verification_id'],'sha256':original['sha256'],'purpose':original['purpose'],'expires_at':original['expires_at']}]
        def insert(value,fail=False):
            self.sql(f"INSERT INTO acquisition_contract_reviews({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::acquisition_contract_reviews,{literal(json.dumps(value))}::jsonb)",fail=fail)
        insert(original|{'execution_findings':None},fail=True)
        bad=deepcopy(original);bad['execution_findings']['seller_signatures']['finding']='unknown';insert(bad,fail=True)
        insert(original|{'kind':'contract_review','policy_id':POLICY},fail=True)
        insert(original)
        self.assertEqual(self.sql(f"SELECT execution_findings FROM acquisition_contract_reviews WHERE id='{review_id}'",user=OTHER),'')
        self.sql(f"UPDATE acquisition_contract_reviews SET note='Replacement forbidden even for privileged fixture' WHERE id='{review_id}'",fail=True)
        self.sql(f"DELETE FROM acquisition_contract_reviews WHERE id='{review_id}'",fail=True)
        self.assertEqual(self.sql(f"SELECT execution_findings IS NOT NULL FROM acquisition_contract_reviews WHERE id='{review_id}'",user=ADMIN),'t')

    def test_signature_execution_storage_policy_does_not_enable_existing_authority(self):
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET kind='executed_contract' WHERE id='{POLICY}'",fail=True)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET kind='executed_contract' WHERE id='{POLICY}'",user=ADMIN,fail=True)
        self.sql(f"SELECT private.valid_execution_findings('{{}}',2)",user=ADMIN,fail=True)
        self.sql("INSERT INTO acquisition_contract_reviews(id) VALUES(gen_random_uuid())",user=ADMIN,fail=True)
        self.sql("INSERT INTO acquisition_contract_reviews(id) VALUES(gen_random_uuid())",role='service_role',user=ADMIN,fail=True)


class ExecutionStorageTests(ExecutionStorageCases,PendingDocumentTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutionStorageTests,test_names=[n for n in ExecutionStorageCases.__dict__ if n.startswith('test_signature_execution_storage_')]))
