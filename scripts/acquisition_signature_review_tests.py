"""Signature decisions depend on an exact current contract review; no signing."""
import json
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from acquisition_contract_source_review_tests import ContractSourceReviewTests, NEW_REVIEW
from acquisition_contract_review_tests import POLICY
from acquisition_contract_document_tests import DOCUMENT, DRAFT, SECOND
from test_acquisition_workspace import ROOT, PG, main, ADMIN, OTHER, OPERATOR, CALLER, WORKSPACE, WORKSPACE_B, literal

MIGRATION = ROOT/'frontend/supabase/migrations/20261101020154_acquisition_signature_reviews.sql'
RELEASE_POLICY = 'af400000-0000-4000-8000-000000000001'
RELEASE = 'af400000-0000-4000-8000-000000000002'
WITHDRAW = 'af400000-0000-4000-8000-000000000003'


class SignatureReviewCases:
    def prepare_signature(self):
        self.save_terms()
        self.review(self.source_review_args())
        self.sql(f"""INSERT INTO private.acquisition_signature_policies
            (id,workspace_id,contract_id,contract_version,reviewer_id,basis_policy_id,artifact_id,source_version,sha256,
             template_approval_ref,approved_by,valid_from,valid_until,max_review_seconds)
            VALUES('{RELEASE_POLICY}','{WORKSPACE}','{DRAFT}',2,'{ADMIN}','{POLICY}','{DOCUMENT}',1,repeat('b',64),
            '{SECOND}','{ADMIN}',clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour',600)""")
        self.signature_expiry = (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()

    def signature_args(self, **changes):
        return dict(p_id=RELEASE,p_workspace=WORKSPACE,p_contract=DRAFT,p_version=2,p_expected_sequence=0,
                    p_status='approved',p_basis=NEW_REVIEW,p_policy=RELEASE_POLICY,p_expires=self.signature_expiry,
                    p_personally_reviewed=True,p_note='Synthetic human signature release review; no signing requested.') | changes

    def signature(self, args=None, actor=ADMIN, fail=False, **kwargs):
        values = [ 'NULL' if v is None else 'true' if v is True else 'false' if v is False else literal(str(v))
                  for v in (self.signature_args() if args is None else args).values()]
        result = self.sql('SELECT public.record_signature_review('+','.join(values)+')',user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def signature_state(self, actor=ADMIN, version=2, fail=False, **kwargs):
        result = self.sql(f"SELECT public.signature_review_state('{WORKSPACE}','{DRAFT}',{version})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_signature_exact_concurrent_retry_and_withdrawal(self):
        self.assertEqual(self.signature_state()['status'],'not_reviewed')
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.signature(),range(3)))
        self.assertEqual(sum(not r['duplicate'] for r in results),1)
        self.assertTrue(all(not r['approval_current'] and not r['execution_authorized'] for r in results))
        self.assertTrue(self.signature_state()['approval_current'])
        self.signature(self.signature_args(p_note='Changed request identity must not clear the first uncertain save.'),fail=True)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_type='acquisition_signature_review' AND entity_id='{RELEASE}'"),'1')
        self.sql('UPDATE private.acquisition_activation SET enabled=false; UPDATE private.acquisition_signature_policies SET revoked_at=clock_timestamp()')
        self.assertFalse(self.signature_state()['approval_current'])
        self.assertTrue(self.signature()['duplicate'])
        args=self.signature_args(p_id=WITHDRAW,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False)
        self.assertEqual(self.signature(args)['status'],'withdrawn')
        self.assertTrue(self.signature(args)['duplicate'])
        self.assertEqual(self.signature_state()['status'],'withdrawn')
        self.assertEqual(self.sql(f"SELECT acquisition_status,acquisition_version,stage FROM deals WHERE id='{DRAFT}'"),'draft|2|offer_made')

    def test_signature_does_not_resurrect_when_basis_replaced(self):
        self.signature()
        self.review(self.source_review_args(p_id=SECOND,p_expected_sequence=1))
        self.assertTrue(self.review_state(version=2)['approval_current'])
        self.assertFalse(self.signature_state()['approval_current'])
        self.signature(self.signature_args(p_id=WITHDRAW,p_expected_sequence=1),fail=True)
        self.signature(self.signature_args(p_id=WITHDRAW,p_expected_sequence=1,p_basis=SECOND))
        self.assertTrue(self.signature_state()['approval_current'])
        self.save_terms(request=WITHDRAW,version=2)
        self.assertFalse(self.signature_state()['approval_current'])
        self.assertTrue(self.signature()['duplicate'])

    def test_signature_scope_policy_mfa_and_raw_write_denial(self):
        for change in ({'p_workspace':WORKSPACE_B},{'p_contract':SECOND},{'p_version':1},{'p_basis':SECOND},
                       {'p_policy':POLICY},{'p_personally_reviewed':False},{'p_expected_sequence':1},
                       {'p_expires':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}):
            self.signature(self.signature_args(**change),fail=True)
        self.member();self.member(target=CALLER,role='acquisition_caller')
        for change in ({'actor':OTHER},{'actor':OPERATOR},{'actor':CALLER},{'aal':'aal1'},
                       {'session':False},{'role':'anon'},{'role':'service_role'}):
            self.signature(fail=True,**change)
        self.signature()
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_signature_reviews',user=OTHER),'0')
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_signature_reviews',user=OPERATOR),'0')
        self.signature_state(actor=OTHER,fail=True)
        self.sql(f"UPDATE acquisition_signature_reviews SET note='Unauthorized replacement of a recorded human decision.' WHERE id='{RELEASE}'",fail=True)
        self.sql('DELETE FROM acquisition_signature_reviews',fail=True)
        self.sql('TRUNCATE acquisition_signature_reviews',user=ADMIN,role='service_role',fail=True)
        self.sql('SELECT * FROM private.acquisition_signature_policies',user=ADMIN,role='service_role',fail=True)

    def test_signature_basis_revocation_and_policy_bytes_invalidate(self):
        self.sql(f"UPDATE private.acquisition_signature_policies SET sha256=repeat('c',64) WHERE id='{RELEASE_POLICY}'")
        self.signature(fail=True)
        self.sql(f"UPDATE private.acquisition_signature_policies SET sha256=repeat('b',64) WHERE id='{RELEASE_POLICY}'")
        self.signature();self.revoke_document()
        self.assertFalse(self.signature_state()['approval_current'])
        self.signature(self.signature_args(p_id=WITHDRAW,p_expected_sequence=1),fail=True)
        self.assertTrue(self.signature()['duplicate'])


    def test_signature_unknown_price_is_not_released(self):
        self.save_terms(self.terms() | {'purchase_price_cents':None},request=WITHDRAW,version=2)
        self.review(self.source_review_args(p_id=SECOND,p_version=3))
        self.sql(f"UPDATE private.acquisition_signature_policies SET contract_version=3 WHERE id='{RELEASE_POLICY}'")
        self.signature(self.signature_args(p_version=3,p_basis=SECOND),fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_signature_reviews'),'0')

    def test_signature_wait_rechecks_revoked_underlying_review_policy(self):
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-h',self.socket,'-U','test_admin','-d',getattr(self,'database_name','acquisition_test')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM 1 FROM private.acquisition_signature_policies WHERE id='{RELEASE_POLICY}' FOR UPDATE; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5;locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':locked=True;break
            self.assertTrue(locked)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.signature,fail=True)
                try:
                    deadline=time.monotonic()+5;waiting='0'
                    while time.monotonic()<deadline:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE state='active' AND wait_event_type='Lock' AND query LIKE '%public.record_signature_review%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0')
                    holder.stdin.write(f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{POLICY}'; COMMIT;\n");holder.stdin.flush()
                finally:holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM acquisition_signature_reviews'),'0')
        finally:holder.communicate('\\q\n',timeout=5)


class SignatureReviewTests(SignatureReviewCases,ContractSourceReviewTests):
    def setUp(self):
        super().setUp()
        before=self.sql('SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r')
        self.sql(MIGRATION.read_text())
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(r)) FROM acquisition_contract_reviews r'))
        self.prepare_signature()


if __name__=='__main__':
    raise SystemExit(main(SignatureReviewTests,test_names=[n for n in SignatureReviewCases.__dict__ if n.startswith('test_signature_')]))
