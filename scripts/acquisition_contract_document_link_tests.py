"""Original source identity, explicit carry-forward and independent withdrawal."""
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from acquisition_contract_terms_tests import ContractTermsTests
from acquisition_contract_document_tests import DOCUMENT,DRAFT,SECOND
from acquisition_contract_observation_tests import OBS
from test_acquisition_workspace import ROOT,PG,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101010335_acquisition_contract_document_links.sql'
LINK='af200000-0000-4000-8000-000000000001'
REVOKE='af200000-0000-4000-8000-000000000002'

class ContractDocumentLinkCases:
    def unknown_terms(self):
        value=self.terms()|dict(purchase_price_cents=None,earnest_money_cents=None,assignment_allowed=None,assignment_provisions=None,sources=[])
        for name in ('effective','inspection_deadline','closing_deadline'):value[name]={'precision':'unknown'}
        return value

    def link_args(self,**changes):
        return dict(p_id=LINK,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_source_version=1,
                    p_artifact=DOCUMENT,p_verification=OBS,p_sha256='b'*64,p_note='Synthetic source retained for a fresh human review.')|changes

    def link_document(self,args=None,actor=ADMIN,fail=False,**kwargs):
        args=self.link_args() if args is None else args
        values=['NULL' if v is None else literal(str(v)) for v in args.values()]
        value=self.sql('SELECT public.link_contract_document('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def withdraw_link(self,actor=ADMIN,fail=False,**kwargs):
        value=self.sql(f"SELECT public.revoke_contract_document_link('{REVOKE}','{WORKSPACE}','{DRAFT}',2,'{LINK}','Synthetic document reference withdrawn from this version.')",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def reference_state(self,version=2,artifact=DOCUMENT,actor=ADMIN,workspace=WORKSPACE,fail=False,**kwargs):
        value=self.sql(f"SELECT public.contract_reference_state('{workspace}','{DRAFT}',{version},'{artifact}')",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_contract_link_terms_reuse_original_source_without_approval(self):
        self.review();self.save_terms()
        ref=self.reference_state()
        self.assertEqual((ref['source_version'],ref['reference_type'],ref['link_id'],ref['status']),(1,'term_source',None,'available_for_review'))
        self.assertEqual(ref['verification_id'],OBS)
        self.assertFalse(ref['review_approved']);self.assertFalse(ref['execution_authorized'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_document_links'),'0')
        self.assertFalse(self.review_state()['approval_current'])
        self.link_document(fail=True)
        self.assertEqual(self.reference_state(version=1)['reference_type'],'native')
        self.reference_state(version=3,fail=True)

    def test_contract_link_exact_concurrent_retry_and_independent_withdrawal(self):
        self.save_terms(self.unknown_terms())
        before=self.sql('SELECT (SELECT count(*) FROM acquisition_evidence_artifacts),(SELECT count(*) FROM acquisition_evidence_verifications)')
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:self.link_document(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(not r['review_approved'] and not r['execution_authorized'] for r in results))
        self.assertEqual(self.reference_state()['reference_type'],'linked')
        self.link_document(self.link_args(p_note='Changed note must not replace exact link request.'),fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertFalse(self.withdraw_link()['duplicate']);self.assertTrue(self.withdraw_link()['duplicate'])
        self.assertTrue(self.link_document()['duplicate'])
        self.assertEqual(self.reference_state()['status'],'reference_withdrawn')
        self.assertEqual(self.reference_state(version=1)['status'],'available_for_review')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_evidence_revocations'),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_document_link'"),'2')
        self.assertEqual(self.sql('SELECT (SELECT count(*) FROM acquisition_evidence_artifacts),(SELECT count(*) FROM acquisition_evidence_verifications)'),before)

    def test_contract_link_scope_roles_and_immutable_rows(self):
        self.save_terms(self.unknown_terms())
        for change in ({'p_workspace':WORKSPACE_B},{'p_contract':SECOND},{'p_source_version':2},{'p_artifact':SECOND},{'p_verification':SECOND},{'p_sha256':'a'*64},{'p_note':'short'}):
            self.link_document(self.link_args(**change),fail=True)
        for change in ({'actor':OTHER},{'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.link_document(fail=True,**change)
        self.member();self.link_document(actor=OPERATOR)
        self.assertEqual(self.reference_state(actor=OPERATOR)['status'],'available_for_review')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_document_links',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_document_links',user=ADMIN,aal='aal1'),'0')
        self.reference_state(actor=OTHER,fail=True);self.reference_state(workspace=WORKSPACE_B,fail=True)
        self.withdraw_link(actor=OTHER,fail=True);self.withdraw_link(actor=OPERATOR)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_document_link_revocations',user=OTHER),'0')
        for table in ('acquisition_contract_document_links','acquisition_contract_document_link_revocations'):
            self.sql('DELETE FROM '+table,fail=True)
            for role in ('authenticated','anon','service_role'):
                self.sql('DELETE FROM '+table,user=ADMIN,role=role,fail=True)
                self.sql('TRUNCATE '+table,user=ADMIN,role=role,fail=True)

    def test_contract_link_current_source_and_current_target_required(self):
        self.save_terms(self.unknown_terms());self.link_document()
        self.save_terms(self.unknown_terms(),request=SECOND,version=2)
        self.reference_state(version=3,fail=True)
        self.assertTrue(self.link_document()['duplicate'])
        self.link_document(self.link_args(p_id=SECOND,p_version=2),fail=True)
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        self.link_document(self.link_args(p_id=SECOND,p_version=3),fail=True)
        self.assertEqual(self.reference_state()['status'],'requires_review')
        self.assertIsNone(self.reference_state()['verification_id'])
        self.revoke_document()
        self.assertEqual(self.reference_state()['status'],'source_revoked')

    def test_contract_link_wait_rechecks_source_authority(self):
        self.save_terms(self.unknown_terms())
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
                                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:{DOCUMENT}',0)); END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.link_document,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.link_contract_document%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp(); COMMIT;\n');holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_document_links'),'0')
        finally:holder.communicate('\\q\n',timeout=5)

class ContractDocumentLinkTests(ContractDocumentLinkCases,ContractTermsTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ContractDocumentLinkTests,test_names=[n for n in ContractDocumentLinkCases.__dict__ if n.startswith('test_contract_link_')]))
