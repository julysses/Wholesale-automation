"""Persisted lifecycle cursor and exact evidence, independent of draft versions."""
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from acquisition_signature_review_tests import SignatureReviewTests, RELEASE_POLICY, RELEASE, WITHDRAW
from acquisition_contract_review_tests import POLICY
from acquisition_contract_document_tests import DRAFT, SECOND
from test_acquisition_workspace import ROOT, PG, main, ADMIN, OTHER, OPERATOR, CALLER, WORKSPACE, WORKSPACE_B, literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101023551_acquisition_contract_lifecycle.sql'
TRANSITION='af500000-0000-4000-8000-000000000001'


class ContractTransitionCases:
    def transition_args(self,**changes):
        return dict(p_id=TRANSITION,p_workspace=WORKSPACE,p_contract=DRAFT,p_expected_version=2,p_expected_sequence=0,
                    p_expected_status='draft',p_target_status='pending_signature',p_reason='Record reviewed contract as awaiting signature without sending it.') | changes

    def transition(self,args=None,actor=ADMIN,fail=False,**kwargs):
        values=['NULL' if v is None else literal(str(v)) for v in (self.transition_args() if args is None else args).values()]
        raw=self.sql('SELECT public.record_contract_transition('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return raw if fail else json.loads(raw)

    def test_signature_transition_concurrent_exact_retry_preserves_terms_and_legacy_stage(self):
        self.signature()
        versions=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.transition(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(r['sequence']==1 and r['contract_version']==2 and not r['execution_authorized'] for r in results))
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version,stage FROM deals WHERE id='{DRAFT}'"),'pending_signature|2|offer_made')
        self.assertEqual(versions,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_transition'"),'1')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.transition()['duplicate'])
        self.transition(self.transition_args(p_reason='A changed reason must not confirm the original request.'),fail=True)
        self.transition(self.transition_args(p_id=SECOND),fail=True)
        self.sql(f"UPDATE acquisition_contract_transitions SET reason='Changed historical decision must always be rejected.' WHERE id='{TRANSITION}'",fail=True)
        self.sql('DELETE FROM acquisition_contract_transitions',fail=True)

    def test_signature_transition_requires_current_release_and_both_cursors(self):
        self.transition(fail=True);self.signature()
        for changes in ({'p_expected_version':1},{'p_expected_sequence':1},{'p_expected_status':'executed'},
                        {'p_target_status':'executed'},{'p_reason':' ' * 30}):
            self.transition(self.transition_args(**changes),fail=True)
        self.revoke_document();self.transition(fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'0')

    def test_signature_transition_role_mfa_tenant_and_raw_write_boundaries(self):
        self.signature();self.member();self.member(target=CALLER,role='acquisition_caller')
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'actor':CALLER},{'aal':'aal1'},
                       {'session':False},{'role':'anon'},{'role':'service_role'}):
            self.transition(fail=True,**kwargs)
        self.transition(self.transition_args(p_workspace=WORKSPACE_B),fail=True)
        self.transition()
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions',user=OPERATOR),'0')
        self.sql("UPDATE deals SET acquisition_status='draft' WHERE workspace_id IS NOT NULL",fail=True)
        self.sql('TRUNCATE acquisition_contract_transitions',user=ADMIN,role='service_role',fail=True)
        self.save_terms(request=SECOND,version=2,fail=True)

    def test_signature_transition_changed_version_and_withdrawn_release_are_held(self):
        self.signature()
        self.signature(self.signature_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False))
        self.transition(fail=True)
        self.save_terms(request=SECOND,version=2)
        self.transition(fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'0')


    def test_signature_transition_wait_rechecks_revoked_underlying_review_policy(self):
        self.signature()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_signature_policies WHERE id='{RELEASE_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.transition,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_contract_transition%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'0')
        finally:holder.communicate('\\q\n',timeout=5)


class ContractTransitionTests(ContractTransitionCases,SignatureReviewTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())


if __name__=='__main__':
    raise SystemExit(main(ContractTransitionTests,test_names=[n for n in ContractTransitionCases.__dict__ if n.startswith('test_signature_transition_')]))
