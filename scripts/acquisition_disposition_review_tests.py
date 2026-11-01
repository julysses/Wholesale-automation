"""Real disposition review writes, original recovery and current authority."""
import json,subprocess,select,time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from acquisition_disposition_policy_tests import DispositionPolicyTests
from acquisition_disposition_storage_tests import POLICY
from acquisition_disposition_plan_tests import PLAN,SECOND
from acquisition_title_review_tests import TITLE_REVIEW,FINDINGS_POLICY
from acquisition_deadline_review_tests import DEADLINE_POLICY
from acquisition_title_storage_tests import TITLE_POLICY,TITLE_FILE
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,PG,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101080958_acquisition_disposition_review_write.sql'
REVIEW='af109000-0000-4000-8000-000000000001'
HOLD='af109000-0000-4000-8000-000000000002'
WITHDRAW='af109000-0000-4000-8000-000000000003'

class DispositionReviewCases:
    def prepare_disposition_review(self,assignment=False,title_held=False):
        row=self.prepare_disposition_storage(assignment,title_held)
        self.insert_disposition_scope(self.disposition_scope(row,assignment))
        self.disposition_input=row['disposition_findings']
        return row

    def disposition_review_args(self,**changes):
        return dict(p_id=REVIEW,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_expected_sequence=0,
            p_status='approved',p_plan=PLAN,p_original_review=None,p_policy=POLICY,
            p_expires=self.sql("SELECT clock_timestamp()+interval '45 seconds'"),p_personally_reviewed=True,
            p_note='Human reviewed this original disposition and its supporting requirements.',p_findings=deepcopy(self.disposition_input))|changes

    def disposition_review_query(self,args):
        def encode(value):
            if value is None:return 'NULL'
            if isinstance(value,bool):return 'true' if value else 'false'
            if isinstance(value,int):return str(value)
            if isinstance(value,dict):return literal(json.dumps(value))+'::jsonb'
            return literal(value)
        return 'SELECT public.record_disposition_review('+','.join(f'{key}=>{encode(value)}' for key,value in args.items())+')'

    def disposition_review(self,args,actor=ADMIN,role='authenticated',aal='aal2',session=True,fail=False):
        result=self.sql(self.disposition_review_query(args),user=actor,role=role,aal=aal,session=session,fail=fail)
        return result if fail else json.loads(result)

    def disposition_state(self,workspace=WORKSPACE,version=2,actor=ADMIN,role='authenticated',aal='aal2',session=True,fail=False):
        result=self.sql(f"SELECT public.disposition_review_state('{workspace}','{DRAFT}',{version})",user=actor,role=role,aal=aal,session=session,fail=fail)
        return result if fail else json.loads(result)

    def test_signature_disposition_write_original_approval_retry_and_revocation(self):
        row=self.prepare_disposition_review();before=self.sql(f"SELECT to_jsonb(d) FROM deals d WHERE id='{DRAFT}'")
        args=self.disposition_review_args();self.assertEqual(self.disposition_state()['status'],'not_reviewed')
        receipt=self.disposition_review(args);self.assertFalse(receipt['duplicate']);self.assertFalse(receipt['approval_current']);self.assertFalse(receipt['execution_authorized'])
        self.assertTrue(self.disposition_state()['approval_current'])
        stored=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'"))
        self.assertEqual(stored['artifact_id'],row['artifact_id']);self.assertEqual(stored['source_version'],1)
        self.assertEqual(stored['disposition_title_review_id'],TITLE_REVIEW);self.assertIsNotNone(stored['disposition_policy_snapshot'])
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.disposition_review(args)['duplicate']);self.assertEqual(self.disposition_state()['status'],'requires_review')
        self.disposition_review(args|dict(p_note='Different request must not replace the original review.'),fail=True)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{REVIEW}'"),'1')
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(d) FROM deals d WHERE id='{DRAFT}'"))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')

    def test_signature_disposition_write_hold_and_original_withdraw_after_pause(self):
        self.prepare_disposition_review(True,title_held=True)
        self.disposition_review(self.disposition_review_args(),fail=True)
        findings=deepcopy(self.disposition_input)
        findings['assignment']['legal_basis'].update(finding='unknown',sources=[],required_action='Obtain counsel assessment of the original assignment requirements.')
        args=self.disposition_review_args(p_status='requires_resolution',p_expires=None,p_findings=findings)
        self.disposition_review(args);self.assertEqual(self.disposition_state()['status'],'requires_resolution')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.sql('UPDATE private.acquisition_disposition_policy_scopes SET revoked_at=clock_timestamp()')
        withdrawal=self.disposition_review_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_original_review=REVIEW,
            p_personally_reviewed=False,p_expires=None,p_findings=None)
        self.disposition_review(withdrawal|dict(p_original_review=HOLD),fail=True)
        self.disposition_review(withdrawal);self.assertTrue(self.disposition_review(withdrawal)['duplicate'])
        self.assertEqual(self.disposition_state()['status'],'withdrawn')
        self.assertEqual(self.sql(f"SELECT disposition_original_review_id,disposition_title_review_id FROM acquisition_contract_reviews WHERE id='{WITHDRAW}'"),REVIEW+'|'+TITLE_REVIEW)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{WITHDRAW}'"),'1')

    def test_signature_disposition_write_superseding_plan_title_and_policy_snapshot(self):
        self.prepare_disposition_review();self.disposition_review(self.disposition_review_args())
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET approval_ref='{OTHER}' WHERE policy_id='{POLICY}'")
        self.assertFalse(self.disposition_state()['approval_current'])
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET approval_ref='{POLICY}' WHERE policy_id='{POLICY}'")
        self.assertTrue(self.disposition_state()['approval_current'])
        self.plan(self.plan_args(p_id=SECOND,p_expected_sequence=1))
        self.assertFalse(self.disposition_state()['approval_current'])
        self.disposition_review(self.disposition_review_args(p_id=HOLD,p_expected_sequence=1),fail=True)
        self.disposition_review(self.disposition_review_args(p_id=HOLD,p_plan=SECOND,p_expected_sequence=1))
        self.assertTrue(self.disposition_state()['approval_current'])
        self.title_review(self.title_review_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='requires_resolution',p_expires=None))
        self.assertFalse(self.disposition_state()['approval_current'])

    def test_signature_disposition_write_assignment_policy_source_and_expiry(self):
        self.prepare_disposition_review(True)
        self.sql(f"UPDATE private.acquisition_disposition_policy_scopes SET legal_source_id='{TITLE_FILE}' WHERE policy_id='{POLICY}'")
        self.disposition_review(self.disposition_review_args(),fail=True)
        value=deepcopy(self.disposition_input)
        value['assignment']['legal_basis']['sources']=[dict(artifact_id=TITLE_FILE,artifact_version=2,sha256='b'*64,locator='Reviewed original legal requirements schedule')]
        self.disposition_review(self.disposition_review_args(p_findings=value,p_expires=self.sql("SELECT clock_timestamp()+interval '2 hours'")),fail=True)
        self.disposition_review(self.disposition_review_args(p_findings=value))
        self.assertTrue(self.disposition_state()['approval_current'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{FINDINGS_POLICY}'")
        self.assertFalse(self.disposition_state()['approval_current'])

    def test_signature_disposition_write_scope_mfa_session_and_service_denials(self):
        self.prepare_disposition_review();self.member();args=self.disposition_review_args()
        for patch in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.disposition_review(args,fail=True,**patch);self.disposition_state(fail=True,**patch)
        for patch in ({'p_workspace':WORKSPACE_B},{'p_version':1},{'p_plan':SECOND},{'p_policy':TITLE_POLICY}):self.disposition_review(args|patch,fail=True)
        self.disposition_state(workspace=WORKSPACE_B,fail=True)
        self.disposition_review(args);self.assertTrue(self.disposition_state()['approval_current'])
        self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'")
        self.disposition_state(fail=True);self.disposition_review(args,fail=True)

    def test_signature_disposition_write_concurrent_exact_retry(self):
        self.prepare_disposition_review();args=self.disposition_review_args()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.disposition_review(args),range(2)))
        self.assertEqual(sorted(r['duplicate'] for r in results),[False,True])
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{REVIEW}'"),'1')

    def disposition_review_wait(self,table,key,policy):
        self.prepare_disposition_review();args=self.disposition_review_args()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.{table} WHERE {key}='{policy}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.disposition_review,args,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_disposition_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.{table} SET revoked_at=clock_timestamp() WHERE {key}='{policy}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
        finally:holder.communicate('\\q\n',timeout=5)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='disposition_findings'"),'0')

    def test_signature_disposition_write_wait_rechecks_scope_revocation(self):
        self.disposition_review_wait('acquisition_disposition_policy_scopes','policy_id',POLICY)

    def test_signature_disposition_write_wait_rechecks_title_revocation(self):
        self.disposition_review_wait('acquisition_contract_review_policies','id',FINDINGS_POLICY)

    def test_signature_disposition_write_wait_rechecks_deadline_revocation(self):
        self.disposition_review_wait('acquisition_contract_review_policies','id',DEADLINE_POLICY)

class DispositionReviewTests(DispositionReviewCases,DispositionPolicyTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionReviewTests,[n for n in DispositionReviewCases.__dict__ if n.startswith('test_signature_disposition_write_')]))
