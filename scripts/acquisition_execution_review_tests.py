"""Exact execution review, sourced current authority and historical recovery."""
import json
import select
import subprocess
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from acquisition_execution_storage_tests import ExecutionStorageTests,ExecutionStorageCases
from acquisition_contract_document_tests import DOCUMENT,DRAFT
from acquisition_contract_observation_tests import OBS
from acquisition_contract_review_tests import POLICY
from test_acquisition_workspace import ROOT,PG,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101030913_acquisition_execution_review_write.sql'
EXEC_POLICY='af780000-0000-4000-8000-000000000001'
EXEC_REVIEW='af780000-0000-4000-8000-000000000002'
EXEC_WITHDRAW='af780000-0000-4000-8000-000000000003'


class ExecutionReviewCases:
    def execution_prepared_terms(self):
        # Relative synthetic dates avoid asserting that an expired real agreement is current.
        now=datetime.now(timezone.utc)
        return dict(purchase_price_cents=20000000,earnest_money_cents=100000,assignment_allowed=False,
          assignment_provisions='Assignment requires written consent.',
          effective={'precision':'instant','instant':(now-timedelta(hours=1)).isoformat()},
          inspection_deadline={'precision':'instant','instant':(now+timedelta(days=5)).isoformat()},
          closing_deadline={'precision':'instant','instant':(now+timedelta(days=20)).isoformat()},
          sources=[dict(term=term,artifact_id=DOCUMENT,artifact_version=1,sha256='b'*64,locator='Synthetic original clause')
            for term in ('purchase_price','earnest_money','assignment','effective','inspection_deadline','closing_deadline')],
          note='Synthetic complete terms from retained original evidence.')

    def prepare_execution(self):
        self.signature();self.transition()
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id','{EXEC_POLICY}','kind','executed_contract'))).* FROM private.acquisition_contract_review_policies p WHERE id='{POLICY}'")

    def execution_args(self,**changes):
        return dict(p_id=EXEC_REVIEW,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_expected_sequence=0,
            p_status='approved',p_artifact=DOCUMENT,p_verification=OBS,p_policy=EXEC_POLICY,p_expires=self.signature_expiry,
            p_personally_reviewed=True,p_note='Synthetic human reviewed signatures, authority and exact returned terms.',
            p_findings=self.execution_findings())|changes

    def execution_review(self,args=None,actor=ADMIN,fail=False,**kwargs):
        args=self.execution_args() if args is None else args
        values=['NULL' if v is None else 'true' if v is True else 'false' if v is False else
                literal(json.dumps(v))+'::jsonb' if isinstance(v,dict) else literal(str(v)) for v in args.values()]
        value=self.sql('SELECT public.record_execution_review('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_signature_execution_write_exact_parallel_retry_audit_and_unchanged_lifecycle(self):
        self.prepare_execution()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.execution_review(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(r['kind']=='executed_contract' and not r['approval_current'] and not r['execution_authorized'] for r in results))
        saved=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{EXEC_REVIEW}'"))
        self.assertEqual(saved['execution_findings'],self.execution_findings())
        self.assertEqual(saved['execution_sources'][0]['verification_id'],OBS)
        self.assertEqual(saved['source_version'],1)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id='{EXEC_REVIEW}'"),'1')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version FROM deals WHERE id='{DRAFT}'"),'pending_signature|2')
        changed=self.execution_findings();changed['seller_signatures']['note']='A changed finding must never replace the original committed request.'
        self.execution_review(self.execution_args(p_findings=changed),fail=True)

    def test_signature_execution_write_reviewed_terms_sources_and_findings_must_match(self):
        self.prepare_execution()
        for mutation in ('price','signature','hash','version','date','missing'):
            changed=self.execution_findings()
            if mutation=='price':changed['terms']['purchase_price_cents']+=1
            elif mutation=='signature':changed['seller_signatures']['finding']='unknown'
            elif mutation=='hash':changed['terms']['sources'][0]['sha256']='c'*64
            elif mutation=='version':changed['terms']['sources'][0]['artifact_version']=2
            elif mutation=='date':changed['terms']['effective']={'precision':'date','calendar_date':'2026-11-01'}
            else:changed['terms']['earnest_money_cents']=None
            self.execution_review(self.execution_args(p_findings=changed),fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='executed_contract'"),'0')

    def test_signature_execution_write_scope_mfa_sessions_policy_and_raw_denial(self):
        self.prepare_execution()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'}):
            self.execution_review(fail=True,**kwargs)
        self.execution_review(self.execution_args(p_workspace=WORKSPACE_B),fail=True)
        self.execution_review(self.execution_args(p_version=1),fail=True)
        self.execution_review(self.execution_args(p_policy=POLICY),fail=True)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        self.execution_review(fail=True)

    def test_signature_execution_write_pause_retry_and_original_withdrawal(self):
        self.prepare_execution();self.execution_review()
        self.sql(f"UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'")
        self.assertTrue(self.execution_review()['duplicate'])
        self.execution_review(self.execution_args(p_id=EXEC_WITHDRAW,p_expected_sequence=1),fail=True)
        withdraw=self.execution_args(p_id=EXEC_WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False,p_findings=None)
        self.execution_review(withdraw,actor=OTHER,fail=True)
        self.assertFalse(self.execution_review(withdraw)['duplicate'])
        self.assertTrue(self.execution_review(withdraw)['duplicate'])
        self.assertEqual(self.sql(f"SELECT execution_findings IS NULL,execution_sources IS NULL FROM acquisition_contract_reviews WHERE id='{EXEC_WITHDRAW}'"),'t|t')
        self.assertEqual(self.sql(f"SELECT execution_findings IS NOT NULL FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"),'t')


    def test_signature_execution_write_additional_term_source_is_independently_verified(self):
        self.prepare_execution()
        source_id='af780000-0000-4000-8000-000000000004'
        scan_id='af780000-0000-4000-8000-000000000005'
        self.document(identity=source_id,version=2)
        changed=self.execution_findings()
        changed['terms']['sources'][0].update(artifact_id=source_id,artifact_version=2)
        args=self.execution_args(p_findings=changed)
        self.execution_review(args,fail=True)
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{source_id}')",user=ADMIN))
        self.record_contract_scan(self.signed_contract(request=scan_id,artifact_id=source_id,contract_version=2,
            retain_until=state['retain_until']))
        self.execution_review(args)
        sources=json.loads(self.sql(f"SELECT execution_sources FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"))
        self.assertEqual({row['artifact_id'] for row in sources},{DOCUMENT,source_id})
        self.sql(f"SELECT public.revoke_contract_document('{EXEC_WITHDRAW}','{WORKSPACE}','{DRAFT}',2,'{source_id}','Supplemental source is no longer valid for review.')",user=ADMIN)
        self.assertTrue(self.execution_review(args)['duplicate'])
        self.execution_review(args|{'p_id':EXEC_WITHDRAW,'p_expected_sequence':1},fail=True)

    def test_signature_execution_write_wait_rechecks_review_policy_revocation(self):
        self.prepare_execution()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id='{EXEC_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.execution_review,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_execution_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{EXEC_POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='executed_contract'"),'0')
        finally:holder.communicate('\\q\n',timeout=5)


class ExecutionReviewTests(ExecutionReviewCases,ExecutionStorageTests):
    def setUp(self):
        self.terms=self.execution_prepared_terms
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(ExecutionReviewTests,test_names=[n for n in ExecutionReviewCases.__dict__ if n.startswith('test_signature_execution_write_')]))
