"""Policy-controlled human decisions, exact evidence and current authority on disposable DB."""
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from acquisition_contract_scan_state_tests import ContractScanStateTests
from acquisition_contract_observation_tests import OBS
from acquisition_contract_document_tests import DOCUMENT,DRAFT,SECOND
from test_acquisition_workspace import ROOT,PG,main,ADMIN,OTHER,OPERATOR,CALLER,WORKSPACE,WORKSPACE_B,literal

MIGRATION=ROOT/'frontend/supabase/migrations/20261101000910_acquisition_contract_reviews.sql'
POLICY='af000000-0000-4000-8000-000000000001'
REVIEW='af000000-0000-4000-8000-000000000002'
WITHDRAW='af000000-0000-4000-8000-000000000003'

class ContractReviewCases:
    def prepare_review_fixture(self):
        self.record_contract_scan(self.signed_contract())
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies(id,workspace_id,kind,purpose,reviewer_id,max_review_seconds,valid_from,valid_until,reviewed_by,approval_ref) VALUES('{POLICY}','{WORKSPACE}','contract_review','purchase_contract','{ADMIN}',1800,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour','{ADMIN}','{SECOND}')")
        self.review_expiry=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()

    def review_args(self, **changes):
        return dict(p_id=REVIEW,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=1,p_kind='contract_review',p_expected_sequence=0,
            p_status='approved',p_artifact=DOCUMENT,p_verification=OBS,p_policy=POLICY,p_expires=self.review_expiry,
            p_personally_reviewed=True,p_note='Synthetic human reviewed the exact source document for contract terms.')|changes

    def review(self, args=None, actor=ADMIN, fail=False, **kwargs):
        args=self.review_args() if args is None else args
        values=['NULL' if v is None else 'true' if v is True else 'false' if v is False else literal(str(v)) for v in args.values()]
        value=self.sql('SELECT public.record_contract_review('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def review_state(self, actor=ADMIN, workspace=WORKSPACE, contract=DRAFT, version=1, kind='contract_review', fail=False,**kwargs):
        value=self.sql(f"SELECT public.contract_review_state('{workspace}','{contract}',{version},{literal(kind)})",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def withdraw(self):
        return self.review(self.review_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False))

    def test_contract_review_concurrent_exact_retry_history_and_withdrawal(self):
        self.assertEqual(self.review_state()['status'],'not_reviewed')
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda _:self.review(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(not r['approval_current'] and not r['execution_authorized'] for r in results))
        self.assertTrue(self.review_state()['approval_current'])
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id='{REVIEW}'"),'1')
        self.review(self.review_args(p_note='Conflicting review text must not replace the recorded exact request.'),fail=True)
        self.review(self.review_args(p_id=SECOND),fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp()')
        self.assertEqual(self.review_state()['status'],'requires_review')
        self.assertTrue(self.review()['duplicate'])
        self.assertEqual(self.withdraw()['sequence'],2)
        self.assertEqual(self.review_state()['status'],'withdrawn')
        self.assertTrue(self.withdraw()['duplicate'])
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews'),'2')

    def test_contract_review_exact_scope_mfa_policy_and_raw_write_denial(self):
        for change in ({'p_workspace':WORKSPACE_B},{'p_contract':SECOND},{'p_version':2},{'p_kind':'title_review'},
                       {'p_artifact':SECOND},{'p_verification':SECOND},{'p_policy':SECOND},{'p_personally_reviewed':False},
                       {'p_expires':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()}):
            self.review(self.review_args(**change),fail=True)
        for change in ({'actor':OTHER},{'aal':'aal1'},{'session':False},{'role':'anon'},{'role':'service_role'}):
            self.review(fail=True,**change)
        self.member();self.review(actor=OPERATOR,fail=True)
        self.member(target=CALLER,role='acquisition_caller');self.review(actor=CALLER,fail=True)
        self.review()
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews',user=OPERATOR),'0')
        for role in ('authenticated','anon','service_role'):
            for sql in ('UPDATE acquisition_contract_reviews SET status=\'withdrawn\'','DELETE FROM acquisition_contract_reviews','TRUNCATE acquisition_contract_reviews','SELECT * FROM private.acquisition_contract_review_policies'):
                self.sql(sql,user=ADMIN,role=role,fail=True)
        self.sql('DELETE FROM acquisition_contract_reviews',fail=True)
        self.review_state(workspace=WORKSPACE_B,fail=True);self.review_state(version=2,fail=True)
        self.review_state(actor=OTHER,fail=True);self.review_state(actor=OPERATOR,fail=True)

    def test_contract_review_requires_current_scan_and_exact_latest_observation(self):
        self.record_contract_scan(self.signed_contract(request=SECOND))
        self.review(fail=True)
        self.review(self.review_args(p_verification=SECOND))
        self.record_contract_scan(self.signed_contract(request=WITHDRAW))
        self.assertFalse(self.review_state()['approval_current'])
        self.review(self.review_args(p_id=SECOND,p_expected_sequence=1,p_verification=WITHDRAW))
        self.assertTrue(self.review_state()['approval_current'])
        self.revoke_document()
        self.assertFalse(self.review_state()['approval_current'])

    def test_contract_review_alias_detection_invalidates_existing_and_new_review(self):
        self.review()
        self.evidence_register(request=SECOND,digest='b'*64)
        self.record_observation(self.signed_observation(request=SECOND,artifact=SECOND,scan_status='detected'))
        self.assertEqual(self.review_state()['status'],'requires_review')
        self.review(self.review_args(p_id=WITHDRAW,p_expected_sequence=1),fail=True)
        self.assertTrue(self.review()['duplicate'])

    def test_contract_review_original_reviewer_session_or_policy_cannot_stay_current(self):
        self.member(target=OTHER,role='admin');self.review()
        for mutation in (
            'UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp()',
            "UPDATE private.acquisition_contract_review_policies SET valid_until=clock_timestamp()-interval '1 second'",
            "UPDATE private.acquisition_contract_review_policies SET max_review_seconds=1",
            f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'",
            f"UPDATE workspace_memberships SET updated_at=updated_at+interval '1 second' WHERE user_id='{ADMIN}' AND workspace_id='{WORKSPACE}'",
        ):
            result=self.sql('BEGIN; '+mutation+'; SET LOCAL ROLE authenticated; '+
                f"SELECT set_config('request.jwt.claims',jsonb_build_object('sub','{OTHER}','role','authenticated','aal','aal2','session_id','{OTHER}')::text,true); "+
                f"SELECT public.contract_review_state('{WORKSPACE}','{DRAFT}',1,'contract_review'); ROLLBACK;")
            self.assertFalse(json.loads(result.splitlines()[-1])['approval_current'],mutation)
        self.assertTrue(self.review_state()['approval_current'])

    def wait_review(self, change, setup_sql=None):
        args=self.review_args()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write((setup_sql or f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:{DRAFT}',0)); END $$;")+" SELECT 'LOCKED';\n");holder.stdin.flush()
            end=time.monotonic()+5;locked=False
            while time.monotonic()<end:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.review,args,fail=True)
                try:
                    end=time.monotonic()+5;waiting='0'
                    while time.monotonic()<end:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.record_contract_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0');change()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews'),'0')
        finally:holder.communicate('\\q\n',timeout=5)

    def test_contract_review_wait_rechecks_reviewer_policy(self):
        self.wait_review(lambda:self.sql('UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp()'))

    def test_contract_review_wait_rechecks_membership(self):
        self.wait_review(lambda:self.sql(f"UPDATE workspace_memberships SET status='revoked' WHERE user_id='{ADMIN}' AND workspace_id='{WORKSPACE}'"))

    def test_contract_review_wait_rechecks_session_expiry(self):
        self.wait_review(lambda:self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id='{ADMIN}'"))

    def test_contract_review_waits_for_committing_alias_detection(self):
        self.evidence_register(request=SECOND,digest='b'*64)
        signed=self.signed_observation(request=SECOND,artifact=SECOND,scan_status='detected')
        claims=json.dumps({'sub':ADMIN,'role':'authenticated','aal':'aal2','session_id':ADMIN})
        setup=(f"BEGIN; SET LOCAL ROLE authenticated; SET LOCAL request.jwt.claims={literal(claims)}; "
               +"DO $$ BEGIN PERFORM public.record_acquisition_evidence_verification("+','.join(literal(v) for v in signed)+"); END $$;")
        self.wait_review(lambda:None,setup_sql=setup)
        self.assertEqual(self.contract_scan_state()['status'],'quarantined')


class ContractReviewTests(ContractReviewCases,ContractScanStateTests):
    def setUp(self):
        super().setUp()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v)) FROM acquisition_evidence_verifications v')
        audits=self.sql('SELECT count(*) FROM audit_logs')
        self.sql(MIGRATION.read_text())
        self.assertEqual(self.sql('SELECT jsonb_agg(to_jsonb(v)) FROM acquisition_evidence_verifications v'),before)
        self.assertEqual(self.sql('SELECT count(*) FROM audit_logs'),audits)
        self.prepare_review_fixture()

if __name__=='__main__':
    raise SystemExit(main(ContractReviewTests,test_names=[n for n in ContractReviewCases.__dict__ if n.startswith('test_contract_review_')]))
