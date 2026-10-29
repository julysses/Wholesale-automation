"""Storage policy integration cases on real disposable PostgreSQL; no stored bytes."""
from acquisition_storage_fixture import STORAGE_MIGRATION

ADMIN='00000000-0000-4000-8000-000000000001'
OTHER='00000000-0000-4000-8000-000000000002'
CALLER='00000000-0000-4000-8000-000000000003'
OPERATOR='00000000-0000-4000-8000-000000000004'
WORKSPACE='10000000-0000-4000-8000-000000000001'
ARTIFACT='99200000-0000-4000-8000-000000000002'
KEY=f'{WORKSPACE}/{ARTIFACT}/'+('a'*64)


def quoted(value):
    return "'"+value.replace("'","''")+"'"


class StorageTests:
    def storage_ready(self, actor=ADMIN):
        self.mail_campaign();self.evidence_policy()
        self.member(target=OPERATOR,role='operator');self.member(target=CALLER,role='acquisition_caller')
        self.evidence_register(actor=actor)

    def storage_upload(self, actor=ADMIN, key=KEY, operation='object.upload', **kwargs):
        return self.sql(f"SET storage.operation={quoted(operation)}; INSERT INTO storage.objects(bucket_id,name) "
                        f"VALUES('acquisition-evidence',{quoted(key)})",user=actor,**kwargs)

    def storage_read(self, actor=ADMIN, operation='object.get_authenticated', **kwargs):
        return self.sql(f"SET storage.operation={quoted(operation)}; SELECT count(*) FROM storage.objects "
                        "WHERE bucket_id='acquisition-evidence'",user=actor,**kwargs)

    def broad_storage_policies(self):
        # Deliberately hostile permissive policies: restrictive guards must win.
        self.sql("CREATE POLICY broad_fixture ON storage.objects TO PUBLIC USING(true) WITH CHECK(true); "
                 "CREATE POLICY broad_fixture ON storage.buckets TO PUBLIC USING(true) WITH CHECK(true)")

    def test_evidence_storage_exact_upload_and_authenticated_read(self):
        self.storage_upload(fail=True)  # No registry identity exists yet.
        self.storage_ready(actor=OPERATOR)
        self.storage_upload(actor=ADMIN,fail=True)  # Only the registering person uploads.
        self.storage_upload(actor=OPERATOR,operation='storage.object.upload')
        self.storage_upload(actor=OPERATOR,fail=True)  # No overwrite on retry.
        self.assertEqual(self.storage_read(actor=OPERATOR),'1')
        self.assertEqual(self.storage_read(operation='object.get_authenticated_info'),'1')
        self.assertEqual(self.storage_read(operation='storage.object.get_authenticated'),'1')
        # Privileged maintenance can bypass RLS; archived metadata must stay hidden.
        self.sql(f"INSERT INTO storage.objects(bucket_id,name,version,archived_at,is_versioned) "
                 f"VALUES('acquisition-evidence',{quoted(KEY)},'synthetic-archive',clock_timestamp(),true)")
        self.assertEqual(self.storage_read(),'1')
        self.assertEqual(self.evidence_state()['status'],'pending_verification')
        for operation in ('','object.list','object.list_v2','object.sign','object.sign_many','object.get_signed',
                          'object.get_public','object.head_authenticated_info','render.image_authenticated','s3.object.get'):
            with self.subTest(operation=operation):
                self.assertEqual(self.storage_read(operation=operation),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=ADMIN),'0')

    def test_evidence_storage_scope_authority_and_paths(self):
        self.storage_ready();self.broad_storage_policies()
        for column,value in (('archived_at','clock_timestamp()'),('is_delete_marker','true'),('is_versioned','true')):
            error=self.sql(f"SET storage.operation='object.upload'; INSERT INTO storage.objects(bucket_id,name,{column}) "
                           f"VALUES('acquisition-evidence',{quoted(KEY)},{value})",user=ADMIN,fail=True)
            self.assertIn('row-level security',error)
        for actor,kwargs in ((OTHER,{}),(CALLER,{}),(OPERATOR,{}),(ADMIN,{'aal':'aal1'}),
                             (ADMIN,{'session':False}),(ADMIN,{'role':'anon'})):
            with self.subTest(actor=actor,kwargs=kwargs):
                self.storage_upload(actor=actor,fail=True,**kwargs)
        for key in (KEY+'/',KEY.upper(),KEY.replace(WORKSPACE,WORKSPACE[:-1]+'2'),KEY[:-1]+'b',
                    '../'+KEY,'malformed',KEY.replace(ARTIFACT,'x'*36)):
            self.storage_upload(key=key,fail=True)
        for operation in ('','object.sign_upload_url','object.upload_signed','object.copy','object.move','s3.upload','tus.upload.create'):
            self.storage_upload(operation=operation,fail=True)
        self.storage_upload()
        for actor,kwargs in ((OTHER,{}),(CALLER,{}),(OPERATOR,{}),(ADMIN,{'aal':'aal1'}),
                             (ADMIN,{'session':False}),(ADMIN,{'role':'anon'})):
            self.assertEqual(self.storage_read(actor=actor,**kwargs),'0')
        self.member(target=OPERATOR,role='admin');self.assertEqual(self.storage_read(actor=OPERATOR),'1')
        self.member(target=OPERATOR,role='agency_manager');self.assertEqual(self.storage_read(actor=OPERATOR),'0')
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE user_id='{ADMIN}'")
        self.assertEqual(self.storage_read(),'0')

    def test_evidence_storage_fresh_revocation_policy_and_gate(self):
        self.storage_ready();self.storage_upload()
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.storage_read(),'1')  # Inspection/revocation stays available when paused.
        self.evidence_revoke();self.assertEqual(self.storage_read(),'0')
        self.storage_upload(fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM storage.objects WHERE bucket_id='acquisition-evidence'"),'1')

    def test_evidence_storage_unavailable_configuration(self):
        self.storage_ready()
        for mutate,restore in (
          ("UPDATE private.acquisition_activation SET enabled=false","UPDATE private.acquisition_activation SET enabled=true"),
          ("UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp()","UPDATE private.acquisition_evidence_policies SET revoked_at=NULL"),
          ("UPDATE private.acquisition_evidence_policies SET valid_until='2026-01-02'","UPDATE private.acquisition_evidence_policies SET valid_until='2099-01-01'"),
          ("UPDATE storage.buckets SET public=true WHERE id='acquisition-evidence'","UPDATE storage.buckets SET public=false WHERE id='acquisition-evidence'"),
          ("UPDATE storage.buckets SET file_size_limit=NULL WHERE id='acquisition-evidence'","UPDATE storage.buckets SET file_size_limit=10485760 WHERE id='acquisition-evidence'"),
        ):
            self.sql(mutate);self.storage_upload(fail=True);self.sql(restore)
        self.storage_upload()
        self.sql("UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp()")
        self.assertEqual(self.storage_read(),'0')

    def test_evidence_storage_retention_deadline(self):
        self.mail_campaign();self.evidence_policy()
        self.sql('UPDATE private.acquisition_evidence_policies SET retention_seconds=1')
        self.evidence_register();self.storage_upload()
        self.assertEqual(self.storage_read(),'1')
        self.sql('SELECT pg_sleep(1.1)')
        self.assertEqual(self.storage_read(),'0');self.storage_upload(fail=True)
        self.assertEqual(self.evidence_state()['status'],'expired')

    def test_evidence_storage_restrictive_guards_preserve_other_buckets(self):
        self.storage_ready();self.storage_upload();self.broad_storage_policies()
        before=self.sql("SELECT to_jsonb(o) FROM storage.objects o WHERE bucket_id='acquisition-evidence'")
        for operation in ('object.upload','object.upload_update','object.move','object.delete','object.get_authenticated'):
            self.sql(f"SET storage.operation={quoted(operation)}; UPDATE storage.objects SET name='changed' WHERE bucket_id='acquisition-evidence'; "
                     "DELETE FROM storage.objects WHERE bucket_id='acquisition-evidence'",user=ADMIN)
        self.assertEqual(self.sql("SELECT to_jsonb(o) FROM storage.objects o WHERE bucket_id='acquisition-evidence'"),before)
        self.sql("UPDATE storage.objects SET bucket_id='acquisition-evidence' WHERE bucket_id='legacy-fixture'",user=ADMIN,fail=True)
        self.sql("UPDATE storage.buckets SET public=true WHERE id='acquisition-evidence'; DELETE FROM storage.buckets WHERE id='acquisition-evidence'",user=ADMIN)
        self.assertEqual(self.sql("SELECT public FROM storage.buckets WHERE id='acquisition-evidence'"),'f')
        self.sql("UPDATE storage.buckets SET name='acquisition-evidence' WHERE id='legacy-fixture'",user=ADMIN,fail=True)
        self.sql("UPDATE storage.objects SET name='legacy-updated' WHERE bucket_id='legacy-fixture'",user=ADMIN)
        self.assertEqual(self.sql("SELECT name FROM storage.objects WHERE bucket_id='legacy-fixture'",user=ADMIN),'legacy-updated')
        self.assertEqual(self.storage_read(role='anon'),'0')

    def test_evidence_storage_populated_upgrade(self):
        self.storage_ready()
        before=self.sql("SELECT jsonb_agg(to_jsonb(o)) FROM storage.objects o")
        audit=self.sql('SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM audit_logs a')
        self.sql(STORAGE_MIGRATION.read_text())
        self.assertEqual(self.sql('SELECT jsonb_agg(to_jsonb(o)) FROM storage.objects o'),before)
        self.assertEqual(self.sql('SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM audit_logs a'),audit)
        self.storage_upload();self.assertEqual(self.storage_read(),'1')

    def test_evidence_storage_bucket_collision_rolls_back(self):
        self.sql("INSERT INTO storage.buckets(id,name,public) VALUES('acquisition-evidence','acquisition-evidence',true)")
        self.sql(STORAGE_MIGRATION.read_text(),fail=True)
        self.assertEqual(self.sql("SELECT public FROM storage.buckets WHERE id='acquisition-evidence'"),'t')
        self.assertEqual(self.sql("SELECT count(*) FROM pg_policies WHERE policyname LIKE 'acquisition_evidence_%' AND schemaname='storage'"),'0')
