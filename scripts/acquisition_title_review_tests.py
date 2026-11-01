"""Title review writes preserve exact evidence, explicit holds and recovery."""
import json,subprocess,select,time
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from acquisition_title_source_tests import TitleSourceTests
from acquisition_title_storage_tests import TITLE_FILE,TITLE_SCAN,FINDINGS_POLICY,EXEC_REVIEW
from acquisition_execution_review_tests import EXEC_POLICY,EXEC_WITHDRAW
from acquisition_deadline_review_tests import DEADLINE_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,PG,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101061744_acquisition_title_review_write.sql'
TITLE_REVIEW='af980000-0000-4000-8000-000000000001'
TITLE_HOLD='af980000-0000-4000-8000-000000000002'
TITLE_WITHDRAW='af980000-0000-4000-8000-000000000003'

class TitleReviewCases:
    def prepare_title_review(self):
        self.prepare_title_storage()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_seconds=86400,title_report_max_age_days=1,title_report_timezone='UTC' WHERE id='{FINDINGS_POLICY}'")

    def title_review_args(self,**changes):
        value=self.title_storage_findings();value['report_as_of']['calendar_date']=datetime.now(timezone.utc).date().isoformat()
        return dict(p_id=TITLE_REVIEW,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_expected_sequence=0,
            p_status='approved',p_artifact=TITLE_FILE,p_verification=TITLE_SCAN,p_policy=FINDINGS_POLICY,p_expires=self.signature_expiry,
            p_personally_reviewed=True,p_note='Human reviewed original title findings and unresolved obligations explicitly.',p_findings=value)|changes

    def title_review(self,args=None,actor=ADMIN,fail=False,**kwargs):
        args=self.title_review_args() if args is None else args
        values=['NULL' if v is None else 'true' if v is True else 'false' if v is False else literal(json.dumps(v))+'::jsonb' if isinstance(v,dict) else literal(str(v)) for v in args.values()]
        result=self.sql('SELECT public.record_title_review('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def title_current(self,review=TITLE_REVIEW):
        return self.sql(f"SELECT private.title_review_current('{review}',clock_timestamp())")=='t'

    def test_signature_title_write_exact_concurrent_retry_and_original_binding(self):
        self.prepare_title_review();args=self.title_review_args()
        before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(lambda _:self.title_review(args),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in rows),1)
        self.assertTrue(all(r['review_recorded'] and not r['approval_current'] and not r['execution_authorized'] for r in rows))
        self.assertTrue(self.title_current())
        saved=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{TITLE_REVIEW}'"))
        self.assertEqual(saved['title_findings'],args['p_findings']);self.assertEqual(saved['title_sources'][0]['verification_id'],TITLE_SCAN)
        self.assertEqual(saved['title_execution_transition_id'],self.sql('SELECT id FROM acquisition_contract_transitions WHERE sequence=2'))
        self.assertEqual(saved['title_policy_snapshot']['title_report_timezone'],'UTC')
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{TITLE_REVIEW}'"),'1')
        self.title_review(args|dict(p_note='Changed original request must never replace an existing receipt.'),fail=True)

    def test_signature_title_write_hold_supersedes_approval_and_original_withdrawal_survives_pause(self):
        self.prepare_title_review();args=self.title_review_args();self.title_review(args)
        hold=deepcopy(args);hold.update(p_id=TITLE_HOLD,p_expected_sequence=1,p_status='requires_resolution',p_expires=None)
        hold['p_findings']['liens_and_payoffs'].update(finding='unknown',sources=[],required_action='Obtain payoff evidence and resolve the unverified lien.')
        self.title_review(hold);self.assertFalse(self.title_current())
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{FINDINGS_POLICY}'")
        self.assertTrue(self.title_review(args)['duplicate']);self.assertTrue(self.title_review(hold)['duplicate'])
        withdrawal=hold|dict(p_id=TITLE_WITHDRAW,p_expected_sequence=2,p_status='withdrawn',p_personally_reviewed=False,p_findings=None)
        self.title_review(withdrawal)
        self.assertTrue(self.title_review(withdrawal)['duplicate'])
        self.assertEqual(self.sql(f"SELECT title_original_review_id,title_original_status FROM acquisition_contract_reviews WHERE id='{TITLE_WITHDRAW}'"),TITLE_HOLD+'|requires_resolution')
        self.assertFalse(self.title_current())

    def test_signature_title_write_requires_explicit_report_freshness_and_preserves_unknown(self):
        self.prepare_title_review();args=self.title_review_args()
        for days in (-2,1):
            bad=deepcopy(args);bad['p_findings']['report_as_of']['calendar_date']=(datetime.now(timezone.utc).date()+timedelta(days=days)).isoformat()
            self.title_review(bad,fail=True)
        for instant in (datetime.now(timezone.utc)+timedelta(hours=1),datetime.now(timezone.utc)-timedelta(days=2)):
            bad=deepcopy(args);bad['p_findings']['report_as_of']=dict(precision='instant',calendar_date=None,instant=instant.isoformat());self.title_review(bad,fail=True)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=NULL,title_report_timezone=NULL,title_report_max_age_seconds=NULL WHERE id='{FINDINGS_POLICY}'")
        self.title_review(args,fail=True)
        hold=deepcopy(args);hold.update(p_status='requires_resolution',p_expires=None)
        hold['p_findings'].update(report_as_of=dict(precision='unknown',calendar_date=None,instant=None),report_as_of_source=None)
        self.title_review(hold);self.assertFalse(self.title_current())
        self.assertEqual(self.sql(f"SELECT title_findings->'report_as_of'->>'precision',expires_at IS NULL FROM acquisition_contract_reviews WHERE id='{TITLE_REVIEW}'"),'unknown|t')

    def test_signature_title_write_current_snapshot_and_execution_revocation(self):
        self.prepare_title_review();args=self.title_review_args();self.title_review(args);self.assertTrue(self.title_current())
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=2 WHERE id='{FINDINGS_POLICY}'")
        self.assertFalse(self.title_current());self.assertTrue(self.title_review(args)['duplicate'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=1 WHERE id='{FINDINGS_POLICY}'")
        self.assertTrue(self.title_current())
        self.execution_review(self.execution_args(p_id=EXEC_WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False,p_findings=None))
        self.assertFalse(self.title_current())
        self.title_review(args|dict(p_id=TITLE_HOLD,p_expected_sequence=1),fail=True)
        self.title_review(args|dict(p_id=TITLE_WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_personally_reviewed=False,p_expires=None,p_findings=None))

    def test_signature_title_write_role_session_scope_and_invalid_envelopes(self):
        self.prepare_title_review();self.member();args=self.title_review_args()
        for kwargs in ({'actor':OTHER},{'actor':OPERATOR},{'role':'service_role'},{'aal':'aal1'},{'session':False}):self.title_review(args,fail=True,**kwargs)
        for change in ({'p_workspace':WORKSPACE_B},{'p_version':1},{'p_personally_reviewed':False},{'p_expected_sequence':1},
            {'p_expires':None},{'p_findings':None},{'p_policy':EXEC_POLICY},{'p_status':'requires_resolution'},
            {'p_expires':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}):self.title_review(args|change,fail=True)
        self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='title_findings'"),'0')

    def test_signature_title_write_calendar_zone_precision_and_instant_policy(self):
        self.prepare_title_review()
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=0,title_report_timezone='America/Chicago' WHERE id='{FINDINGS_POLICY}'")
        report=dict(precision='date',calendar_date='2026-11-01',instant=None)
        query=f"SELECT private.title_report_fresh_until({literal(json.dumps(report))}::jsonb,p,'2026-11-01T12:00:00Z')='2026-11-02T06:00:00Z'::timestamptz FROM private.acquisition_contract_review_policies p WHERE id='{FINDINGS_POLICY}'"
        self.assertEqual(self.sql(query),'t')  # Explicit local calendar policy spans the 25-hour DST day.
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_timezone='Invalid/Zone' WHERE id='{FINDINGS_POLICY}'")
        self.assertEqual(self.sql(query.replace("='2026-11-02T06:00:00Z'::timestamptz",' IS NULL')),'t')
        args=self.title_review_args();args['p_findings']['report_as_of']=dict(precision='instant',calendar_date=None,instant=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())
        self.title_review(args);self.assertTrue(self.title_current())
        self.assertEqual(self.sql(f"SELECT title_findings->'report_as_of'->>'precision' FROM acquisition_contract_reviews WHERE id='{TITLE_REVIEW}'"),'instant')

    def test_signature_title_write_scoped_read_state_and_paused_history(self):
        self.prepare_title_review();self.member()
        query=f"SELECT public.title_review_state('{WORKSPACE}','{DRAFT}',2)"
        self.assertEqual(json.loads(self.sql(query,user=ADMIN))['status'],'not_reviewed')
        self.title_review();state=json.loads(self.sql(query,user=ADMIN));self.assertEqual(state['status'],'approved');self.assertTrue(state['approval_current']);self.assertFalse(state['execution_authorized'])
        for kwargs in ({'user':OTHER},{'user':OPERATOR},{'user':ADMIN,'aal':'aal1'},{'user':ADMIN,'session':False},{'user':ADMIN,'role':'service_role'}):self.sql(query,fail=True,**kwargs)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        state=json.loads(self.sql(query,user=ADMIN));self.assertEqual(state['status'],'requires_review');self.assertFalse(state['approval_current']);self.assertIsNone(state['expires_at']);self.assertEqual(state['review_id'],TITLE_REVIEW)

    def title_review_wait(self,policy):
        self.prepare_title_review();args=self.title_review_args()
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_contract_review_policies WHERE id='{policy}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.title_review,args,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_title_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{policy}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql("SELECT count(*) FROM acquisition_contract_reviews WHERE kind='title_findings'"),'0')
        finally:holder.communicate('\\q\n',timeout=5)

    def test_signature_title_write_wait_rechecks_title_policy(self):self.title_review_wait(FINDINGS_POLICY)
    def test_signature_title_write_wait_rechecks_original_deadline_policy(self):self.title_review_wait(DEADLINE_POLICY)

class TitleReviewTests(TitleReviewCases,TitleSourceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(TitleReviewTests,[n for n in TitleReviewCases.__dict__ if n.startswith('test_signature_title_write_')]))
