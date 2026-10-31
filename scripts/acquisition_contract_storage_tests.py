"""Contract Storage RLS and bounded transport against disposable real registry data."""
import asyncio
import os
import hashlib
from uuid import UUID
import httpx
from fastapi import HTTPException
from acquisition_contract_document_tests import ContractDocumentTests, DOCUMENT, DOC_POLICY, DRAFT, SECOND
from test_acquisition_workflow import WorkflowTests, AcquisitionStore, EvidenceUnavailable, EvidenceUploadUnconfirmed
from test_acquisition_workspace import ROOT, main, ADMIN, OTHER, OPERATOR, WORKSPACE, literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261031231025_acquisition_contract_storage_upload.sql'


class ContractStorageCases:
    def contract_object(self, actor=ADMIN, fail=False, operation='object.upload', artifact=DOCUMENT, **kwargs):
        path=f'{WORKSPACE}/{artifact}/'+('b'*64)
        return self.sql(f"SET storage.operation={literal(operation)}; INSERT INTO storage.objects(bucket_id,name) VALUES('acquisition-evidence',{literal(path)})",user=actor,fail=fail,**kwargs)

    def test_contract_storage_requires_exact_live_reservation(self):
        self.document();self.document(identity=SECOND)
        self.contract_object(fail=True)
        self.contract_admission()
        self.contract_object(artifact=SECOND,fail=True)
        self.contract_object(actor=OTHER,fail=True)
        self.member();self.contract_object(actor=OPERATOR,fail=True)
        self.contract_object(aal='aal1',fail=True);self.contract_object(session=False,fail=True)
        for op in ('object.upsert','object.copy','object.move','object.list','object.get_authenticated'):
            self.contract_object(operation=op,fail=True)
        self.contract_object()
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'"),'1')
        self.assertEqual(self.document_state()['status'],'pending_verification')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_document'"),'2')

    def test_contract_storage_expired_capacity_activation_and_policy(self):
        self.document();self.contract_admission();self.expire_slots();self.contract_object(fail=True)
        self.contract_admission()
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.contract_object(fail=True);self.activate()
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        self.contract_object(fail=True)
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL WHERE id='{DOC_POLICY}'")
        self.revoke_document();self.contract_object(fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'"),'0')

    def test_contract_storage_rechecks_session_and_membership_after_admission(self):
        self.document();self.contract_admission()
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.contract_object(fail=True)
        self.sql(f"UPDATE auth.sessions SET not_after=NULL WHERE id='{ADMIN}'")
        self.sql(f"UPDATE workspace_memberships SET status='revoked' WHERE workspace_id='{WORKSPACE}' AND user_id='{ADMIN}'")
        self.contract_object(fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'"),'0')

    def test_contract_storage_no_listing_overwrite_or_delete(self):
        self.document();self.contract_admission();self.contract_object()
        # Even an unrelated broad permissive policy cannot bypass the restrictive guards.
        self.sql('CREATE POLICY synthetic_broad_storage ON storage.objects FOR ALL TO authenticated USING(true) WITH CHECK(true)')
        path=f'{WORKSPACE}/{DOCUMENT}/'+('b'*64)
        self.assertEqual(self.sql("SET storage.operation='object.list'; SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=ADMIN),'0')
        self.assertEqual(self.sql("SET storage.operation='object.get_authenticated'; SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=ADMIN),'1')
        self.sql("SET storage.operation='object.update'; UPDATE storage.objects SET name=name WHERE bucket_id='acquisition-evidence'",user=ADMIN)
        self.sql("SET storage.operation='object.delete'; DELETE FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=ADMIN)
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'"),'1')
        self.assertEqual(self.sql(f"SET storage.operation='object.get_signed'; SELECT private.acquisition_evidence_object_access('{path}',false)",user=ADMIN),'f')
        self.sql(f"UPDATE storage.objects SET archived_at=clock_timestamp() WHERE name='{path}'")
        self.assertEqual(self.sql("SET storage.operation='object.get_authenticated'; SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=ADMIN),'0')

    def contract_transport_fixture(self):
        self.evidence_body=b'Synthetic contract bytes with current registry and real RLS'
        self.evidence_streams=[];self.evidence_uploads=0
        digest=hashlib.sha256(self.evidence_body).hexdigest()
        self.sql(f"SELECT public.register_contract_document('{DOCUMENT}','{WORKSPACE}','{DRAFT}',1,'purchase_contract','{digest}',{len(self.evidence_body)},'text/plain','{DOC_POLICY}','Synthetic transport source document.')",user=ADMIN)

    def upload_contract_fixture(self, after=None, token='synthetic-admin-session'):
        async def source():
            self.contract_source_reads=getattr(self,'contract_source_reads',0)+1
            yield self.evidence_body
            if after:after()
        async def upload():
            async with httpx.AsyncClient(base_url='https://workflow.example.test/rest/v1/',
                    headers={'Authorization':'Bearer '+token,'apikey':'synthetic-public-key'}) as client:
                return await AcquisitionStore(client).upload_contract_document_with_admission(UUID(DOCUMENT),source(),
                    workspace_id=UUID(WORKSPACE),contract_id=UUID(DRAFT),contract_version=1,purpose='purchase_contract')
        return asyncio.run(upload())

    def test_contract_storage_transport_lost_commit_reply_and_exact_retry(self):
        self.contract_transport_fixture();self.lose_evidence_reply_once=True
        result=self.upload_contract_fixture()
        self.assertEqual(result['status'],'stored_unverified');self.assertFalse(result['legal_review_approved'])
        self.assertFalse(result['verification_persisted']);self.assertFalse(result['execution_authorized'])
        with self.assertRaises(HTTPException) as busy:self.upload_contract_fixture()
        self.assertEqual(busy.exception.status_code,429);self.assertEqual(self.contract_source_reads,1)
        self.expire_slots();self.assertEqual(self.upload_contract_fixture()['status'],'stored_unverified')
        self.assertEqual(self.evidence_uploads,1)
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'"),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_document'"),'1')

    def test_contract_storage_transport_revoked_during_read_and_before_write(self):
        self.contract_transport_fixture()
        with self.assertRaises(EvidenceUploadUnconfirmed):
            self.upload_contract_fixture(after=lambda:self.sql('UPDATE private.acquisition_activation SET enabled=false'))
        self.assertEqual(self.evidence_uploads,0)
        self.activate();self.expire_slots()
        self.after_evidence_read=lambda:self.revoke_document()
        with self.assertRaises(EvidenceUploadUnconfirmed):self.upload_contract_fixture()
        self.assertEqual(self.evidence_uploads,1)
        self.assertEqual(self.document_state()['status'],'revoked')

    def test_contract_storage_transport_foreign_session_cannot_read_source(self):
        self.contract_transport_fixture()
        with self.assertRaises(HTTPException):self.upload_contract_fixture(token='synthetic-other-session')
        self.assertEqual(getattr(self,'contract_source_reads',0),0);self.assertEqual(self.evidence_uploads,0)
        self.assertFalse(any(path.startswith('/storage/') for path,auth in self.requests))

    def test_contract_storage_api_closed_gate_scope_and_uncertain_recovery(self):
        self.contract_transport_fixture()
        path=f'{self.base}/contracts/{DRAFT}/versions/1/documents/{DOCUMENT}/bytes?purpose=purchase_contract'
        headers={**self.headers,'Content-Type':'application/octet-stream'}
        self.assertEqual(self.client.post(path,headers=headers,content=self.evidence_body).status_code,404)
        self.assertEqual(self.requests,[])
        os.environ['ACQUISITION_CONTRACT_UPLOAD_ENABLED']='true'
        denied=self.client.post(path,headers={**headers,'Authorization':'Bearer synthetic-other-session'},content=self.evidence_body)
        self.assertEqual(denied.status_code,403)
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_evidence_upload_slots'),'0')
        self.lose_evidence_reply_once=True;self.unavailable_evidence_read_once=True
        uncertain=self.client.post(path,headers=headers,content=self.evidence_body)
        self.assertEqual(uncertain.status_code,503,uncertain.text)
        self.assertEqual(uncertain.json()['detail']['code'],'CONTRACT_DOCUMENT_UPLOAD_UNCONFIRMED')
        self.assertEqual(self.evidence_uploads,1)
        busy=self.client.post(path,headers=headers,content=self.evidence_body)
        self.assertEqual(busy.status_code,429);self.assertIn('retry-after',busy.headers)
        self.expire_slots()
        recovered=self.client.post(path,headers=headers,content=self.evidence_body)
        self.assertEqual(recovered.status_code,200,recovered.text)
        self.assertEqual(recovered.headers['cache-control'],'no-store')
        data=recovered.json()
        self.assertEqual(data['status'],'stored_unverified');self.assertEqual(data['contract_version'],1)
        self.assertFalse(data['verification_persisted']);self.assertFalse(data['legal_review_approved'])
        self.assertFalse(data['execution_authorized']);self.assertEqual(self.evidence_uploads,1)
        self.assertEqual(self.document_state()['status'],'pending_verification')

    def test_contract_storage_api_wrong_file_and_revocation_during_verification(self):
        self.contract_transport_fixture();os.environ['ACQUISITION_CONTRACT_UPLOAD_ENABLED']='true'
        path=f'{self.base}/contracts/{DRAFT}/versions/1/documents/{DOCUMENT}/bytes?purpose=purchase_contract'
        headers={**self.headers,'Content-Type':'application/octet-stream'}
        wrong=self.client.post(path,headers=headers,content=b'wrong file')
        self.assertEqual(wrong.status_code,409)
        self.assertEqual(wrong.json()['detail']['code'],'CONTRACT_DOCUMENT_UPLOAD_NOT_ACCEPTED')
        self.assertEqual(self.evidence_uploads,0)
        self.expire_slots();self.after_evidence_read=lambda:self.revoke_document()
        uncertain=self.client.post(path,headers=headers,content=self.evidence_body)
        self.assertEqual(uncertain.status_code,503,uncertain.text)
        self.assertEqual(uncertain.json()['detail']['code'],'CONTRACT_DOCUMENT_UPLOAD_UNCONFIRMED')
        self.assertEqual(self.document_state()['status'],'revoked')
        self.assertEqual(self.client.post(path,headers=headers,content=self.evidence_body).status_code,403)
        self.assertEqual(self.evidence_uploads,1)


class ContractStorageTests(ContractStorageCases, ContractDocumentTests, WorkflowTests):
    def setUp(self):
        super().setUp()
        self.sql(MIGRATION.read_text())


if __name__=='__main__':
    raise SystemExit(main(ContractStorageTests,test_names=[name for name in ContractStorageCases.__dict__ if name.startswith('test_contract_storage_')]))
