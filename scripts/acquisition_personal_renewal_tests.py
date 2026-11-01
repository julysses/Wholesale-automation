"""Private authenticated writer rehearsal; no exposed endpoint or live activation."""
import json
import select
import subprocess
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from acquisition_renewal_authority_lock_tests import RenewalAuthorityLockTests
from acquisition_contract_document_tests import DRAFT, DOCUMENT
from acquisition_contract_observation_tests import OBS, KEY
from acquisition_disposition_review_tests import REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from test_acquisition_workspace import PG, ROOT, WORKSPACE, WORKSPACE_B, ADMIN, OTHER, CALLER, literal, main
from schemas.acquisition_review_renewal import ReviewRenewalReceipt

MIGRATION=ROOT/'frontend/supabase/migrations/20261101104656_acquisition_personal_review_renewal.sql'
FIRST='af138000-0000-4000-8000-000000000001'
SECOND='af138000-0000-4000-8000-000000000002'
SCAN='af138000-0000-4000-8000-000000000003'


class PersonalRenewalCases:
    def renewal_command(self,root=REVIEW,identity=FIRST,expires=None):
        original=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{root}'"))
        snapshot=json.loads(self.sql(f"SELECT private.acquisition_renewal_snapshot('{WORKSPACE}','{DRAFT}',2,'{root}','{original['policy_id']}',clock_timestamp())"))
        return dict(p_id=identity,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_kind=original['kind'],p_term=original['deadline_term'],
            p_expected_sequence=snapshot['expected_sequence'],p_root=root,p_previous=snapshot['previous']['id'],p_policy=original['policy_id'],
            p_snapshot=snapshot['sha256'],p_expires=expires or (datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),
            p_personally_reviewed=True,p_note='Personally reviewed unchanged original facts and current supporting evidence.')

    def personal_renewal_query(self,args,actor=ADMIN,aal='aal2',role='authenticated'):
        values=[('NULL' if v is None else ('true' if v else 'false') if isinstance(v,bool) else literal(str(v))) for v in args.values()]
        claims=json.dumps(dict(sub=actor,aal=aal,role=role,session_id=actor))
        # Private functions intentionally have no client grant yet. The disposable
        # owner invokes the definer with real auth claims; no test-only public API.
        return f"BEGIN; SET LOCAL request.jwt.claims={literal(claims)}; SELECT private.record_acquisition_review_renewal("+','.join(values)+'); COMMIT;'

    def personal_renewal(self,args,fail=False,**identity):
        result=self.sql(self.personal_renewal_query(args,**identity),fail=fail)
        return result if fail else json.loads(result)

    def test_signature_personal_renewal_all_kinds_originals_and_receipt_replay(self):
        self.prepare_handoff(True);self.transition(self.handoff_args())
        history=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        originals=self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r')
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"))+[EXEC_REVIEW,TITLE_REVIEW,REVIEW]
        expires=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
        for index,root in enumerate(roots,10):
            args=self.renewal_command(root,identity=f'af138000-0000-4000-8000-{index:012d}',expires=expires)
            first=self.personal_renewal(args);receipt=ReviewRenewalReceipt.model_validate(first)
            self.assertFalse(receipt.duplicate);self.assertFalse(receipt.approval_current)
            self.assertTrue(self.personal_renewal(args)['duplicate'])
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.assertEqual(history,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t'))
        self.assertEqual(originals,self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r WHERE renewal_root_id IS NULL'))
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='renewed'"),str(len(roots)))
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.personal_renewal(args)['duplicate'])
        self.personal_renewal(args|dict(p_note='Changed note must not replace an immutable original request.'),fail=True)

    def test_signature_personal_renewal_snapshot_scope_and_expiry_fail_without_rows(self):
        self.prepare_handoff(True)
        args=self.renewal_command()
        for change in (dict(p_snapshot='0'*64),dict(p_previous=EXEC_REVIEW),dict(p_workspace=WORKSPACE_B),
                       dict(p_personally_reviewed=False),dict(p_expires='2000-01-01T00:00:00+00:00'),dict(p_expires='2099-01-01T00:00:00+00:00')):
            self.personal_renewal(args|change,fail=True)
        for identity in (dict(actor=OTHER),dict(actor=CALLER),dict(aal='aal1'),dict(role='service_role')):
            self.personal_renewal(args,fail=True,**identity)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL'),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='renewed'"),'0')

    def test_signature_personal_renewal_new_scan_requires_independent_supports(self):
        self.prepare_handoff(True);args=self.renewal_command()
        self.record_contract_scan(self.signed_contract(request=SCAN))
        self.personal_renewal(args,fail=True)
        self.personal_renewal(self.renewal_command(),fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL'),'0')
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"))+[EXEC_REVIEW,TITLE_REVIEW,REVIEW]
        expires=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
        for index,root in enumerate(roots,20):
            self.personal_renewal(self.renewal_command(root,identity=f'af138000-0000-4000-8000-{index:012d}',expires=expires))
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.assertEqual(self.sql(f"SELECT verification_id FROM acquisition_contract_reviews WHERE id='{EXEC_REVIEW}'"),OBS)

    def test_signature_personal_renewal_expired_original_gets_new_bounded_decision(self):
        self.prepare_disposition_review(True)
        expires=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
        self.disposition_review(self.disposition_review_args(p_expires=expires))
        original=self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'")
        self.sql('DO $$ BEGIN PERFORM pg_sleep(1.1); END $$')
        self.assertEqual(self.effective_downstream('disposition'),'f')
        receipt=self.personal_renewal(self.renewal_command())
        self.assertFalse(receipt['approval_current'])
        self.assertEqual(self.effective_downstream('disposition'),'t')
        self.assertEqual(original,self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{REVIEW}'"))

    def test_signature_personal_renewal_parallel_retry_one_audit(self):
        self.prepare_handoff(True);args=self.renewal_command()
        with ThreadPoolExecutor(max_workers=3) as pool:
            rows=list(pool.map(lambda _:self.personal_renewal(args),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in rows),1)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{FIRST}' AND action='renewed'"),'1')

    def wait_personal_renewal(self, holder_setup, *, expire=False):
        self.prepare_handoff(True)
        args=self.renewal_command(expires=(datetime.now(timezone.utc)+timedelta(seconds=2)).isoformat() if expire else None)
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,'-U','test_admin',
            '-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write('BEGIN; '+holder_setup+"; SELECT 'LOCKED';\n");holder.stdin.flush()
            end=time.monotonic()+5;locked=False
            while time.monotonic()<end:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.personal_renewal,args,fail=True)
                try:
                    end=time.monotonic()+5;waiting='0'
                    while time.monotonic()<end:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%private.record_acquisition_review_renewal%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                finally:
                    holder.stdin.write(('SELECT pg_sleep(2.1); ' if expire else '')+'COMMIT;\n');holder.stdin.flush()
                error=future.result(timeout=8)
                self.assertTrue(any(message in error for message in ('context changed','bounded personal renewal','source verification')),error)
        finally:holder.communicate('\\q\n',timeout=5)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL'),'0')
        self.assertEqual(self.sql("SELECT count(*) FROM audit_logs WHERE action='renewed'"),'0')

    def test_signature_personal_renewal_wait_rechecks_policy_revocation(self):
        from acquisition_disposition_storage_tests import POLICY
        self.wait_personal_renewal(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{POLICY}'")

    def test_signature_personal_renewal_wait_rechecks_scanner_revocation(self):
        self.wait_personal_renewal(f"UPDATE private.acquisition_evidence_verification_keys SET revoked_at=clock_timestamp() WHERE id='{KEY}'")

    def test_signature_personal_renewal_wait_rechecks_requested_expiry(self):
        self.wait_personal_renewal(f"DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:{DOCUMENT}',0)); END $$",expire=True)


class PersonalRenewalTests(PersonalRenewalCases,RenewalAuthorityLockTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())


if __name__=='__main__':
    raise SystemExit(main(PersonalRenewalTests,[n for n in PersonalRenewalCases.__dict__ if n.startswith('test_signature_personal_renewal_')]))
