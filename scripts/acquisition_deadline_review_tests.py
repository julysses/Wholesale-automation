"""Source-bound interpretation writes, exact retry and independent term withdrawal."""
import json
import select
import subprocess
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from acquisition_deadline_storage_tests import DeadlineStorageTests,DEADLINE_POLICY,DEADLINE_REVIEW
from acquisition_execution_review_tests import ExecutionReviewCases
from acquisition_contract_document_tests import DOCUMENT,DRAFT
from acquisition_contract_observation_tests import OBS
from acquisition_contract_review_tests import POLICY
from test_acquisition_workspace import ROOT,PG,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101041353_acquisition_deadline_resolution_write.sql'
WITHDRAW='af830000-0000-4000-8000-000000000001'
SECOND_REVIEW='af830000-0000-4000-8000-000000000002'

class DeadlineReviewCases:
    def deadline_prepared_terms(self):
        value=ExecutionReviewCases.execution_prepared_terms(self)
        value['effective']={'precision':'date','calendar_date':'2026-11-01'}
        value['closing_deadline']={'precision':'date','calendar_date':'2026-11-20'}
        return value

    def prepare_deadline_review(self):
        self.signature();self.transition()
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id','{DEADLINE_POLICY}','kind','deadline_resolution'))).* FROM private.acquisition_contract_review_policies p WHERE id='{POLICY}'")

    def deadline_args(self,**changes):
        return dict(p_id=DEADLINE_REVIEW,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_expected_sequence=0,
            p_status='approved',p_artifact=DOCUMENT,p_verification=OBS,p_policy=DEADLINE_POLICY,p_expires=self.signature_expiry,
            p_personally_reviewed=True,p_note='Synthetic human review of the original date and explicit interpretation.',
            p_term='closing_deadline',p_resolution=self.deadline_proposal(),p_original=None)|changes

    def deadline_review(self,args=None,actor=ADMIN,fail=False,**kwargs):
        args=self.deadline_args() if args is None else args
        values=['NULL' if v is None else 'true' if v is True else 'false' if v is False else
                literal(json.dumps(v))+'::jsonb' if isinstance(v,dict) else literal(str(v)) for v in args.values()]
        result=self.sql('SELECT public.record_deadline_resolution_review('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_signature_deadline_write_parallel_exact_retry_preserves_calendar_and_status(self):
        self.prepare_deadline_review()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.deadline_review(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(r['interpretation_review_id']==DEADLINE_REVIEW and not r['approval_current'] and not r['execution_authorized'] for r in results))
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{DEADLINE_REVIEW}' AND entity_type='acquisition_contract_review'"),'1')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version FROM deals WHERE id='{DRAFT}'"),'pending_signature|2')
        saved=json.loads(self.sql(f"SELECT deadline_sources FROM acquisition_contract_reviews WHERE id='{DEADLINE_REVIEW}'"))
        self.assertEqual(saved[0]['verification_id'],OBS)
        changed=self.deadline_proposal();changed['rationale']='A changed interpretation must not replace this exact saved request.'
        self.deadline_review(self.deadline_args(p_resolution=changed),fail=True)

    def test_signature_deadline_write_withdraws_original_term_after_other_term_and_pause(self):
        self.prepare_deadline_review();self.deadline_review()
        effective=self.deadline_proposal();effective.update(term='effective',calendar_date='2026-11-01',resolved_instant='2026-11-01T17:00:00-06:00')
        effective['source']['term']='effective'
        self.deadline_review(self.deadline_args(p_id=SECOND_REVIEW,p_expected_sequence=1,p_term='effective',p_resolution=effective))
        self.sql(f"UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.assertTrue(self.deadline_review()['duplicate'])
        withdraw=self.deadline_args(p_id=WITHDRAW,p_expected_sequence=2,p_status='withdrawn',p_original=DEADLINE_REVIEW,
            p_resolution=None,p_personally_reviewed=False,p_expires=None)
        self.deadline_review(withdraw|{'p_term':'effective'},fail=True)
        self.deadline_review(withdraw|{'p_original':SECOND_REVIEW},fail=True)
        self.deadline_review(withdraw|{'p_expected_sequence':1},fail=True)
        self.deadline_review(withdraw,actor=OTHER,fail=True)
        saved=self.deadline_review(withdraw)
        self.assertEqual(saved['interpretation_review_id'],DEADLINE_REVIEW)
        self.assertEqual(saved['sequence'],3)
        self.assertTrue(self.deadline_review(withdraw)['duplicate'])
        self.assertEqual(self.sql(f"SELECT deadline_sources IS NULL,deadline_resolution IS NULL FROM acquisition_contract_reviews WHERE id='{WITHDRAW}'"),'t|t')
        self.assertEqual(self.sql(f"SELECT status FROM acquisition_contract_reviews WHERE id='{SECOND_REVIEW}'"),'approved')

    def test_signature_deadline_write_scope_mfa_source_date_and_policy_holds(self):
        self.prepare_deadline_review()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'aal':'aal1'},{'session':False},{'role':'service_role'},{'role':'anon'}):
            self.deadline_review(fail=True,**kwargs)
        for changes in ({'p_workspace':WORKSPACE_B},{'p_version':1},{'p_policy':POLICY},{'p_verification':SECOND_REVIEW},
                        {'p_term':'effective'},{'p_original':SECOND_REVIEW},{'p_personally_reviewed':False}):
            self.deadline_review(self.deadline_args(**changes),fail=True)
        for mutation in ('date','source','future','instant'):
            changed=self.deadline_proposal();term='closing_deadline'
            if mutation=='date':changed.update(calendar_date='2026-11-21',resolved_instant='2026-11-21T17:00:00-06:00')
            elif mutation=='source':changed['source']['sha256']='c'*64
            elif mutation=='future':changed['source']['artifact_version']=3
            else:term='inspection_deadline';changed['term']=term;changed['source']['term']=term
            self.deadline_review(self.deadline_args(p_term=term,p_resolution=changed),fail=True)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'")
        self.deadline_review(fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"),'0')

    def test_signature_deadline_write_requires_both_original_and_interpretation_sources(self):
        self.prepare_deadline_review()
        source_id='af830000-0000-4000-8000-000000000004';scan_id='af830000-0000-4000-8000-000000000005'
        self.document(identity=source_id,version=2)
        proposal=self.deadline_proposal();proposal['source'].update(artifact_id=source_id,artifact_version=2)
        args=self.deadline_args(p_artifact=source_id,p_verification=scan_id,p_resolution=proposal)
        self.deadline_review(args,fail=True)
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{source_id}')",user=ADMIN))
        self.record_contract_scan(self.signed_contract(request=scan_id,artifact_id=source_id,contract_version=2,retain_until=state['retain_until']))
        self.deadline_review(args)
        bound=json.loads(self.sql(f"SELECT deadline_sources FROM acquisition_contract_reviews WHERE id='{DEADLINE_REVIEW}'"))
        self.assertEqual({s['artifact_id'] for s in bound},{DOCUMENT,source_id})
        self.sql(f"SELECT public.revoke_contract_document('{WITHDRAW}','{WORKSPACE}','{DRAFT}',1,'{DOCUMENT}','Original calendar clause evidence withdrawn after review.')",user=ADMIN)
        self.assertTrue(self.deadline_review(args)['duplicate'])
        self.deadline_review(args|{'p_id':SECOND_REVIEW,'p_expected_sequence':1},fail=True)

    def test_signature_deadline_write_wait_rechecks_revoked_review_policy(self):
        self.prepare_deadline_review()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id='{DEADLINE_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.deadline_review,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_deadline_resolution_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"),'0')
        finally:holder.communicate('\\q\n',timeout=5)


class DeadlineReviewTests(DeadlineReviewCases,DeadlineStorageTests):
    def setUp(self):
        self.execution_prepared_terms=self.deadline_prepared_terms
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(DeadlineReviewTests,test_names=[n for n in DeadlineReviewCases.__dict__ if n.startswith('test_signature_deadline_write_')]))
