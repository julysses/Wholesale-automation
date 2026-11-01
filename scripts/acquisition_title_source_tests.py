"""Internal title-source resolution; no approval or public writer is enabled."""
import json,subprocess,select,time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from acquisition_title_storage_tests import TitleStorageTests,TITLE_FILE,TITLE_SCAN,TITLE_POLICY,EXEC_REVIEW
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,PG,literal
from acquisition_contract_document_tests import DRAFT
MIGRATION=ROOT/'frontend/supabase/migrations/20261101061021_acquisition_title_source_resolution.sql'

class TitleSourceCases:
    def title_sources(self,findings=None,artifact=TITLE_FILE,verification=TITLE_SCAN,workspace=WORKSPACE,version=2,actor=ADMIN,aal='aal2',session=True,fail=False):
        claims=dict(sub=actor,role='authenticated',aal=aal)
        if session:claims['session_id']=actor
        # Privileged synthetic caller models the forthcoming private writer. No
        # public function or application grant is created by this fixture.
        query=f"SET request.jwt.claims={literal(json.dumps(claims))}; SELECT private.resolve_title_review_sources('{workspace}','{DRAFT}',{version},'{artifact}','{verification}',{literal(json.dumps(findings if findings is not None else self.title_storage_findings()))}::jsonb)"
        result=self.sql(query,fail=fail)
        return result if fail else json.loads(result)

    def test_signature_title_sources_exact_originals_and_no_authority(self):
        self.prepare_title_storage()
        before=self.sql('SELECT count(*) FROM acquisition_contract_reviews')
        result=self.title_sources();self.assertEqual(len(result['sources']),1)
        source=result['sources'][0];self.assertEqual(source['artifact_id'],TITLE_FILE);self.assertEqual(source['verification_id'],TITLE_SCAN)
        self.assertEqual(source['source_version'],2);self.assertEqual(source['purpose'],'title_report')
        for name in ('legal_review_approved','title_clearance_confirmed','execution_authorized'):self.assertFalse(result[name])
        value=self.title_storage_findings()
        extra=json.loads(self.sql(f"SELECT execution_sources->0 FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"))
        value['liens_and_payoffs']['sources']=[dict(artifact_id=extra['artifact_id'],artifact_version=extra['source_version'],sha256=extra['sha256'],locator='Executed agreement original, page 2')]
        result=self.title_sources(value);self.assertEqual(len(result['sources']),2)
        self.assertEqual(before,self.sql('SELECT count(*) FROM acquisition_contract_reviews'))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')

    def test_signature_title_sources_citations_scope_and_private_boundary(self):
        self.prepare_title_storage();self.member()
        for patch in ({'workspace':WORKSPACE_B},{'version':1},{'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'verification':EXEC_REVIEW}):
            self.title_sources(fail=True,**patch)
        for change in ({'sha256':'a'*64},{'artifact_version':1}):
            value=self.title_storage_findings()
            for item in [value['report_as_of_source']]+[value[name]['sources'][0] for name in ('ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession')]:item.update(change)
            self.title_sources(value,fail=True)
        for role in ('authenticated','service_role','anon'):
            self.sql(f"SELECT private.resolve_title_review_sources('{WORKSPACE}','{DRAFT}',2,'{TITLE_FILE}','{TITLE_SCAN}','{{}}')",user=ADMIN,role=role,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false');self.title_sources(fail=True)

    def test_signature_title_sources_revoked_scan_scope_and_expired_authority(self):
        self.prepare_title_storage()
        self.sql(f"UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp() WHERE purpose='title_report'")
        self.title_sources(fail=True)
        self.sql("UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=NULL WHERE purpose='title_report'")
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{TITLE_POLICY}'")
        self.title_sources(fail=True)
        self.sql(f"UPDATE private.acquisition_evidence_policies SET revoked_at=NULL WHERE id='{TITLE_POLICY}'")
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.title_sources(fail=True)

    def test_signature_title_sources_wait_rechecks_retention_revocation(self):
        self.prepare_title_storage()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_evidence_policies WHERE id='{TITLE_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.title_sources,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%private.resolve_title_review_sources%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_evidence_policies SET revoked_at=clock_timestamp() WHERE id='{TITLE_POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                self.assertIn('Title source authority changed while waiting',future.result(timeout=5))
        finally:holder.communicate('\\q\n',timeout=5)

class TitleSourceTests(TitleSourceCases,TitleStorageTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(TitleSourceTests,[n for n in TitleSourceCases.__dict__ if n.startswith('test_signature_title_sources_')]))
