"""Internal purchase-path intentions preserve canonical contract history and holds."""
import json,subprocess,select,time
from concurrent.futures import ThreadPoolExecutor
from acquisition_title_candidate_tests import TitleCandidateTests
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,PG,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101071737_acquisition_disposition_plans.sql'
PLAN='af103000-0000-4000-8000-000000000001'
SECOND='af103000-0000-4000-8000-000000000002'
WITHDRAW='af103000-0000-4000-8000-000000000003'

class DispositionPlanCases:
    def plan_args(self,**changes):
        return dict(p_id=PLAN,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_expected_sequence=0,
            p_status='proposed',p_exit_type='principal_acquisition',p_note='Proposed direct acquisition for separate human review.',p_original_plan=None)|changes

    def plan(self,args=None,actor=ADMIN,fail=False,**kwargs):
        args=args or self.plan_args()
        fields=','.join(k+'=>'+('NULL' if v is None else str(v) if type(v) is int else literal(v)) for k,v in args.items())
        result=self.sql('SELECT public.record_disposition_plan('+fields+')',user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def plan_state(self,actor=ADMIN,workspace=WORKSPACE,version=2,fail=False,**kwargs):
        result=self.sql(f"SELECT public.disposition_plan_state('{workspace}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_signature_disposition_plan_exact_retry_preserves_contract_and_audit(self):
        self.prepare_title_review()
        before=self.sql(f"SELECT to_jsonb(d)::text FROM deals d WHERE id='{DRAFT}'")
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.plan(),range(2)))
        self.assertEqual(sum(r['duplicate'] for r in results),1)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_disposition_plan'"),'1')
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(d)::text FROM deals d WHERE id='{DRAFT}'"))
        for result in results:
            self.assertFalse(result['disposition_approved']);self.assertFalse(result['execution_authorized']);self.assertTrue(result['plan_recorded'])
        state=self.plan_state();self.assertEqual(state['latest']['plan_id'],PLAN);self.assertEqual(state['latest']['exit_type'],'principal_acquisition')
        self.assertEqual(state['readiness'],'ready_for_planning');self.assertEqual(state['withdrawal']['expected_sequence'],1)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='title_findings'"),'0')  # Intent is not title or legal approval.
        self.plan(self.plan_args(p_note='Changed request text cannot replace the original intent.'),fail=True)
        self.plan(self.plan_args(p_id=SECOND),fail=True)

    def test_signature_disposition_plan_revisions_and_original_withdrawal_after_pause(self):
        self.prepare_title_review();self.plan()
        args=self.plan_args(p_id=SECOND,p_expected_sequence=1,p_exit_type='wholesale_assignment',p_note='Proposed assignment requires separate reviewed legal basis.')
        self.plan(args)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertEqual(self.plan_state()['readiness'],'paused');self.assertTrue(self.plan(args)['duplicate'])
        self.plan(self.plan_args(p_id=WITHDRAW,p_expected_sequence=2),fail=True)
        withdrawal=args|dict(p_id=WITHDRAW,p_expected_sequence=2,p_status='withdrawn',p_original_plan=SECOND,p_note='Withdraw the original assignment proposal pending counsel review.')
        self.plan(withdrawal);self.assertTrue(self.plan(withdrawal)['duplicate'])
        state=self.plan_state();self.assertEqual(state['latest']['status'],'withdrawn');self.assertIsNone(state['withdrawal'])
        self.assertEqual(state['latest']['original_plan_id'],SECOND)
        self.assertEqual(self.sql("SELECT string_agg(exit_type,',' ORDER BY sequence) FROM acquisition_disposition_plans"),'principal_acquisition,wholesale_assignment,wholesale_assignment')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_disposition_plan'"),'3')

    def test_signature_disposition_plan_scope_mfa_roles_and_raw_writes(self):
        self.prepare_title_review();self.member();self.plan()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'actor':ADMIN,'aal':'aal1'},{'actor':ADMIN,'session':False},{'actor':ADMIN,'role':'service_role'}):
            self.plan(fail=True,**kwargs);self.plan_state(fail=True,**kwargs)
        self.plan(self.plan_args(p_workspace=WORKSPACE_B),fail=True);self.plan_state(workspace=WORKSPACE_B,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans',user=OPERATOR),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans',user=ADMIN),'1')
        for role in ('authenticated','service_role'):
            for sql in ('DELETE FROM acquisition_disposition_plans','TRUNCATE acquisition_disposition_plans',"UPDATE acquisition_disposition_plans SET note='Replace protected original intention with a different text.'"):
                self.sql(sql,user=ADMIN,role=role,fail=True)
        self.sql("INSERT INTO acquisition_disposition_plans SELECT * FROM acquisition_disposition_plans",user=ADMIN,fail=True)
        self.sql("UPDATE acquisition_disposition_plans SET note='Privileged edits still cannot rewrite original decisions.'",fail=True)

    def test_signature_disposition_plan_context_and_invalid_withdrawals(self):
        self.prepare_title_review()
        self.assertEqual(self.plan_state(version=1)['readiness'],'contract_unavailable')
        for changes in ({'p_version':1},{'p_expected_sequence':-1},{'p_status':'approved'},{'p_exit_type':'brokerage'},
                {'p_note':' '*30},{'p_original_plan':SECOND},{'p_status':'withdrawn'},{'p_expected_sequence':2147483647}):self.plan(self.plan_args(**changes),fail=True)
        self.plan()
        for changes in ({'p_original_plan':SECOND},{'p_exit_type':'wholesale_assignment'},{'p_expected_sequence':0}):
            args=self.plan_args(p_id=WITHDRAW,p_status='withdrawn',p_expected_sequence=1,p_original_plan=PLAN)|changes
            self.plan(args,fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans'),'1')

    def test_signature_disposition_plan_wait_observes_membership_revocation(self):
        self.prepare_title_review()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM public.workspace_memberships WHERE workspace_id='{WORKSPACE}' AND user_id='{ADMIN}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.plan,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_disposition_plan%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE public.workspace_memberships SET status='revoked' WHERE workspace_id='{WORKSPACE}' AND user_id='{ADMIN}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_disposition_plans'),'0')
        finally:holder.communicate('\\q\n',timeout=5)

class DispositionPlanTests(DispositionPlanCases,TitleCandidateTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionPlanTests,[n for n in DispositionPlanCases.__dict__ if n.startswith('test_signature_disposition_plan_')]))
