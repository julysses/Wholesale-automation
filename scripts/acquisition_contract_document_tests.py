"""Disposable contract document registry: no live uploads, signatures or legal findings."""
import json
import select
import subprocess
import time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from acquisition_contract_tests import ContractDraftTests, DRAFT, SECOND
from test_acquisition_workspace import main, ROOT, PG, ADMIN, OTHER, OPERATOR, CALLER, WORKSPACE, WORKSPACE_B, literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261031224723_acquisition_contract_document_registry.sql'
DOCUMENT='ad000000-0000-4000-8000-000000000001'
DOC_POLICY='ad000000-0000-4000-8000-000000000002'
REVOCATION='ad000000-0000-4000-8000-000000000003'

class ContractDocumentCases:
    def prepare_document_fixture(self):
        self.draft()
        self.sql(f"INSERT INTO private.acquisition_evidence_policies(id,workspace_id,purpose,version,retention_seconds,valid_from,valid_until,approval_ref,reviewed_by,reviewed_at) VALUES('{DOC_POLICY}','{WORKSPACE}','purchase_contract',1,86400,'2026-01-01','2099-01-01','{REVOCATION}','{ADMIN}','2026-01-01')")

    def document(self, actor=ADMIN, identity=DOCUMENT, workspace=WORKSPACE, contract=DRAFT, version=1, purpose='purchase_contract', note='Synthetic contract source document provenance.', fail=False, **kwargs):
        result=self.sql(f"SELECT public.register_contract_document('{identity}','{workspace}','{contract}',{version},{literal(purpose)},'{ 'b'*64 }',123,'application/pdf','{DOC_POLICY}',{literal(note)})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def document_state(self, actor=ADMIN, workspace=WORKSPACE, contract=DRAFT, version=1, fail=False, **kwargs):
        result=self.sql(f"SELECT public.contract_document_state('{workspace}','{contract}',{version},'{DOCUMENT}')",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def revoke_document(self, actor=ADMIN, fail=False, **kwargs):
        result=self.sql(f"SELECT public.revoke_contract_document('{REVOCATION}','{WORKSPACE}','{DRAFT}',1,'{DOCUMENT}','Document no longer applies to this review.')",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_contract_document_exact_concurrent_retry_and_atomic_audit(self):
        with ThreadPoolExecutor(max_workers=3) as pool: receipts=list(pool.map(lambda _:self.document(),range(3)))
        self.assertEqual(sum(not row['duplicate'] for row in receipts),1)
        self.assertTrue(all(row['execution_authorized'] is False and row['bytes_verified'] is False for row in receipts))
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_document'"),'1')
        self.document(note='Different provenance must not overwrite metadata.',fail=True)
        self.assertEqual(self.document_state()['status'],'pending_verification')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.document()['duplicate'])
        self.document(identity=SECOND,fail=True)
        self.revoke_document();self.assertEqual(self.document_state()['status'],'revoked')
        self.assertTrue(self.revoke_document()['duplicate'])
        self.assertTrue(self.document()['duplicate'])

    def test_contract_document_target_role_and_session_isolation(self):
        for change in ({'workspace':WORKSPACE_B},{'contract':SECOND},{'version':2},{'purpose':'mail_content'},
                       {'actor':OTHER},{'aal':'aal1'},{'session':False},{'role':'service_role'}):
            self.document(fail=True,**change)
        self.member(target=CALLER,role='acquisition_caller');self.document(actor=CALLER,fail=True)
        self.member(target=CALLER,role='agency_manager');self.document(actor=CALLER,fail=True)
        self.member();self.document(actor=OPERATOR)
        self.revoke_document(actor=OPERATOR,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_artifacts WHERE contract_id IS NOT NULL',user=OTHER),'0')
        self.document_state(actor=OTHER,fail=True);self.document_state(version=2,fail=True)
        self.document_state(role='service_role',fail=True)
        self.member(status='revoked');self.document_state(actor=OPERATOR,fail=True)
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.document_state(fail=True);self.document(fail=True)

    def test_contract_document_preserves_mail_and_rejects_legacy_routes(self):
        self.mail_campaign();self.evidence_policy();self.evidence_register()
        self.document()
        self.assertEqual(self.evidence_state()['status'],'pending_verification')
        self.evidence_register(request=DOCUMENT,fail=True)
        self.evidence_state(artifact=DOCUMENT,fail=True)
        self.evidence_revoke(artifact=DOCUMENT,fail=True)
        self.assertIsNone(self.sql(f"SELECT campaign_id FROM acquisition_evidence_artifacts WHERE id='{DOCUMENT}'") or None)
        self.evidence_revoke();self.assertEqual(self.evidence_state()['status'],'revoked')
        self.assertEqual(self.document_state()['status'],'pending_verification')

    def test_contract_document_retention_and_raw_mutations(self):
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        self.document(fail=True)
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL WHERE id='{DOC_POLICY}'")
        self.document()
        self.assertEqual(self.sql(f"SELECT extract(epoch FROM retain_until-created_at)::int FROM acquisition_evidence_artifacts WHERE id='{DOCUMENT}'"),'86400')
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        self.assertEqual(self.document_state()['status'],'policy_review_required')
        self.assertTrue(self.document()['duplicate'])
        for table in ('acquisition_evidence_artifacts','acquisition_evidence_revocations'):
            for command in (f'DELETE FROM {table}',f'TRUNCATE {table}',f'UPDATE {table} SET contract_id=contract_id'):
                self.sql(command,user=ADMIN,fail=True);self.sql(command,user=ADMIN,role='service_role',fail=True)
        self.sql(f"SELECT * FROM private.lock_contract_document_context('{WORKSPACE}','{DRAFT}',1,ARRAY['owner'])",user=ADMIN,fail=True)

    def test_contract_document_storage_no_upload_and_current_read_guard(self):
        self.document();path=f'{WORKSPACE}/{DOCUMENT}/'+('b'*64)
        # Platform-owned synthetic fixture bytes; application upload remains unavailable.
        self.sql(f"INSERT INTO storage.objects(bucket_id,name) VALUES('acquisition-evidence','{path}')")
        query=f"SET storage.operation='object.get_authenticated'; SELECT count(*) FROM storage.objects WHERE name='{path}'"
        self.assertEqual(self.sql(query,user=ADMIN),'1');self.assertEqual(self.sql(query,user=OTHER),'0')
        self.member();self.assertEqual(self.sql(query,user=OPERATOR),'0')
        self.sql(f"SET storage.operation='object.upload'; SELECT CASE WHEN private.acquisition_evidence_object_access('{path}',true) THEN 1 ELSE 0 END",user=ADMIN)
        self.assertEqual(self.sql(f"SET storage.operation='object.upload'; SELECT private.acquisition_evidence_object_access('{path}',true)",user=ADMIN),'f')
        self.revoke_document();self.assertEqual(self.sql(query,user=ADMIN),'0')

    def blocked_document(self, change):
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,
            '-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:{DRAFT}',0)); END $$;\n\\echo locked\n")
            holder.stdin.flush()
            self.assertTrue(select.select([holder.stdout],[],[],5)[0]);self.assertEqual(holder.stdout.readline().strip(),'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.document,fail=True)
                try:
                    end=time.monotonic()+5;waiting='0'
                    while time.monotonic()<end:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.register_contract_document%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0','Registration must actually wait before authority changes')
                    change()
                finally:
                    holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                error=future.result(timeout=5)
            self.assertIn('authority changed',error)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_artifacts WHERE contract_id IS NOT NULL'),'0')
        finally:
            holder.communicate('\\q\n',timeout=5)

    def test_contract_document_wait_rechecks_session(self):
        self.blocked_document(lambda:self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE user_id='{ADMIN}'"))

    def test_contract_document_wait_rechecks_membership(self):
        self.blocked_document(lambda:self.sql(f"UPDATE workspace_memberships SET status='revoked' WHERE user_id='{ADMIN}'"))

class ContractUploadAdmissionCases:
    def contract_admission(self, actor=ADMIN, attempt=None, workspace=WORKSPACE, contract=DRAFT,
                           version=1, artifact=DOCUMENT, purpose='purchase_contract', fail=False, **kwargs):
        result=self.sql(f"SELECT public.admit_contract_document_upload('{attempt or uuid4()}','{workspace}','{contract}',{version},'{artifact}',{literal(purpose)})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def expire_slots(self):
        self.sql("UPDATE private.acquisition_evidence_upload_slots SET started_at=started_at-interval '121 seconds',expires_at=expires_at-interval '121 seconds'")

    def test_contract_upload_mixed_capacity_and_bidirectional_reuse(self):
        self.document();self.mail_campaign();self.evidence_policy();self.evidence_register()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda n:self.contract_admission() if n%2 else self.upload_admission(),range(6)))
        self.assertEqual(sum(r['admitted'] for r in results),1)
        self.assertTrue(all(r['execution_authorized'] is False for r in results))
        first=next(r for r in results if r['admitted'])
        self.contract_admission(attempt=first['attempt_id'],fail=True)
        self.member();self.document(actor=OPERATOR,identity=SECOND)
        self.assertTrue(self.contract_admission(actor=OPERATOR,artifact=SECOND)['admitted'])
        third='ad000000-0000-4000-8000-000000000009'
        self.member(target=OTHER);self.evidence_register(actor=OTHER,request=third)
        self.assertFalse(self.upload_admission(actor=OTHER,artifact=third)['admitted'])
        self.expire_slots();self.assertTrue(self.contract_admission()['admitted'])
        self.assertEqual(self.sql("SELECT count(*) FROM private.acquisition_evidence_upload_slots WHERE slot=1 AND campaign_id IS NULL AND contract_id IS NOT NULL"),'1')
        self.expire_slots();self.assertTrue(self.upload_admission()['admitted'])
        self.assertEqual(self.sql("SELECT count(*) FROM private.acquisition_evidence_upload_slots WHERE slot=1 AND campaign_id IS NOT NULL AND contract_id IS NULL AND contract_version IS NULL"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_evidence_upload_slots'),'2')
        path=f'{WORKSPACE}/{DOCUMENT}/'+('b'*64)
        self.assertEqual(self.sql(f"SET storage.operation='object.upload'; SELECT private.acquisition_evidence_object_access('{path}',true)",user=ADMIN),'f')

    def test_contract_upload_current_authority_and_private_capacity(self):
        self.document();self.member()
        for change in ({'actor':OTHER},{'actor':OPERATOR},{'workspace':WORKSPACE_B},{'contract':SECOND},
                       {'version':2},{'version':0},{'artifact':SECOND},{'purpose':'mail_content'},
                       {'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.contract_admission(fail=True,**change)
        for column,value in (('acquisition_version','2'),('acquisition_status',"'pending_signature'")):
            # The current draft-only schema itself rejects these future states.
            self.sql(f"UPDATE deals SET {column}={value} WHERE id='{DRAFT}'",fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.contract_admission(fail=True);self.activate()
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'")
        self.contract_admission(fail=True)
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL WHERE id='{DOC_POLICY}'")
        self.assertTrue(self.contract_admission()['admitted'])
        self.revoke_document();self.contract_admission(fail=True)
        for role in ('authenticated','service_role'):
            for command in ('SELECT * FROM','DELETE FROM','TRUNCATE'):
                self.sql(command+' private.acquisition_evidence_upload_slots',user=ADMIN,role=role,fail=True)

    def blocked_contract_admission(self, change):
        self.document()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,
            '-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('evidence-upload-admission:{WORKSPACE}',0)); END $$;\n\\echo locked\n")
            holder.stdin.flush()
            self.assertTrue(select.select([holder.stdout],[],[],5)[0]);self.assertEqual(holder.stdout.readline().strip(),'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.contract_admission,fail=True)
                try:
                    end=time.monotonic()+5;waiting='0'
                    while time.monotonic()<end:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.admit_contract_document_upload%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0','Admission must actually wait before authority changes')
                    change()
                finally:
                    holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                error=future.result(timeout=5)
            self.assertIn('Current evidence upload authority required',error)
            self.assertEqual(self.sql('SELECT count(*) FROM private.acquisition_evidence_upload_slots'),'0')
        finally:
            holder.communicate('\\q\n',timeout=5)

    def test_contract_upload_wait_rechecks_session(self):
        self.blocked_contract_admission(lambda:self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE user_id='{ADMIN}'"))

    def test_contract_upload_wait_rechecks_membership(self):
        self.blocked_contract_admission(lambda:self.sql(f"UPDATE workspace_memberships SET status='revoked' WHERE user_id='{ADMIN}'"))

    def test_contract_upload_wait_rechecks_retention(self):
        self.blocked_contract_admission(lambda:self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{DOC_POLICY}'"))

class ContractDocumentTests(ContractUploadAdmissionCases,ContractDocumentCases,ContractDraftTests):
    def setUp(self):
        super().setUp()
        if self._testMethodName=='test_contract_document_populated_mail_upgrade':
            self.mail_campaign();self.evidence_policy();self.evidence_register()
            self.saved_mail=self.sql("SELECT row_to_json(a)::text FROM acquisition_evidence_artifacts a")
        self.sql(MIGRATION.read_text())
        self.prepare_document_fixture()
        if self._testMethodName=='test_contract_document_populated_mail_upgrade':
            self.upload_admission()
            self.saved_slot=json.loads(self.sql('SELECT row_to_json(s) FROM private.acquisition_evidence_upload_slots s'))
        self.sql((ROOT/'frontend/supabase/migrations/20261031225950_acquisition_contract_upload_admission.sql').read_text())

    def test_contract_document_populated_mail_upgrade(self):
        slot=json.loads(self.sql('SELECT row_to_json(s) FROM private.acquisition_evidence_upload_slots s'))
        self.assertEqual({key:slot[key] for key in self.saved_slot},self.saved_slot)
        self.assertIsNone(slot['contract_id']);self.assertIsNone(slot['contract_version'])
        self.assertFalse(self.upload_admission()['admitted'])
        before=json.loads(self.saved_mail)
        after=json.loads(self.sql("SELECT row_to_json(a)::text FROM acquisition_evidence_artifacts a WHERE campaign_id IS NOT NULL"))
        self.assertEqual({key:after[key] for key in before},before)
        self.assertIsNone(after['contract_id']);self.assertIsNone(after['contract_version'])
        self.assertEqual(self.evidence_state()['status'],'pending_verification')
        self.document()
        for change in ({'contract_version':99},{'contract_id':SECOND},{'workspace_id':WORKSPACE_B},
                       {'campaign_id':'91000000-0000-4000-8000-000000000001'},{'contract_id':None,'contract_version':None}):
            patch={'id':SECOND,**change}
            self.sql(f"INSERT INTO acquisition_evidence_artifacts SELECT (jsonb_populate_record(NULL::acquisition_evidence_artifacts,to_jsonb(a)||{literal(json.dumps(patch))}::jsonb)).* FROM acquisition_evidence_artifacts a WHERE id='{DOCUMENT}'",fail=True)

if __name__=='__main__':
    raise SystemExit(main(ContractDocumentTests,test_names=[name for name in ContractDocumentCases.__dict__ if name.startswith('test_contract_document_')]+[name for name in ContractUploadAdmissionCases.__dict__ if name.startswith('test_contract_upload_')]+['test_contract_document_populated_mail_upgrade']))
