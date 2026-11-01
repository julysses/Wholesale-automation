"""Private renewal lock union; no public renewal save or current approval claim."""
import json
import select
import subprocess
import time

from acquisition_downstream_effective_tests import DownstreamEffectiveTests, NEW_DATE
from acquisition_contract_document_tests import DRAFT, DOCUMENT
from acquisition_contract_observation_tests import KEY
from acquisition_deadline_review_tests import DEADLINE_REVIEW, DEADLINE_POLICY
from acquisition_disposition_review_tests import REVIEW
from acquisition_disposition_storage_tests import POLICY
from test_acquisition_workspace import ROOT, PG, WORKSPACE, WORKSPACE_B, ADMIN, main

MIGRATION = ROOT/'frontend/supabase/migrations/20261101104256_acquisition_renewal_authority_locks.sql'


class RenewalAuthorityLockCases:
    def renewal_set(self, root=REVIEW, workspace=WORKSPACE, **kwargs):
        return self.sql(f"SELECT private.acquisition_renewal_review_set('{workspace}','{DRAFT}',2,'{root}',clock_timestamp())", **kwargs)

    def renewal_lock_query(self):
        return f"SELECT private.lock_acquisition_renewal_authority('{WORKSPACE}','{DRAFT}',2,'{REVIEW}','{POLICY}')"

    def test_signature_renewal_locks_complete_heads_without_granting_currentness(self):
        self.prepare_handoff(True)
        rows = json.loads(self.renewal_set())
        self.assertEqual({r['kind'] for r in rows}, {'deadline_resolution','executed_contract','title_findings','disposition_findings'})
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(r['kind']=='deadline_resolution' for r in rows), 2)
        self.assertEqual(rows, json.loads(self.sql(self.renewal_lock_query())))
        self.insert_title_fixture(self.renewal_row(DEADLINE_REVIEW, id=NEW_DATE))
        changed = json.loads(self.renewal_set())
        self.assertEqual(next(r['review_id'] for r in changed if r['root_id']==DEADLINE_REVIEW), NEW_DATE)
        self.assertEqual(changed, json.loads(self.sql(self.renewal_lock_query())))
        self.assertEqual(self.effective_downstream('disposition'), 'f')
        self.assertEqual(self.renewal_set(workspace=WORKSPACE_B), '')
        self.assertEqual(self.renewal_set(root=NEW_DATE), '')

    def test_signature_renewal_locks_private_and_withdrawal_rejected(self):
        self.prepare_handoff(True)
        for role in ('anon','authenticated','service_role'):
            self.renewal_set(user=ADMIN, role=role, fail=True)
            self.sql(self.renewal_lock_query(), user=ADMIN, role=role, fail=True)
        self.disposition_review(self.disposition_review_args(p_id=NEW_DATE,p_expected_sequence=1,p_status='withdrawn',
            p_expires=None,p_personally_reviewed=False,p_original_review=REVIEW,p_findings=None))
        self.assertEqual(self.renewal_set(), '')
        self.assertIn('Complete unsuperseded renewal support', self.sql(self.renewal_lock_query(), fail=True))

    def test_signature_renewal_locks_hold_transitive_sources_policies_and_sessions(self):
        self.prepare_handoff(True)
        holder = subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,'-U','test_admin',
            '-d',getattr(self,'database_name','acquisition_test')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            function = self.renewal_lock_query().removeprefix('SELECT ')
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM {function}; END $$; SELECT 'LOCKED';\n");holder.stdin.flush()
            deadline=time.monotonic()+5; locked=False
            while time.monotonic()<deadline:
                if select.select([holder.stdout],[],[],.1)[0] and holder.stdout.readline().strip()=='LOCKED':
                    locked=True;break
            self.assertTrue(locked)
            changes = [
                f"UPDATE private.acquisition_contract_review_policies SET revoked_at=clock_timestamp() WHERE id='{DEADLINE_POLICY}'",
                f"UPDATE private.acquisition_evidence_verification_keys SET revoked_at=clock_timestamp() WHERE id='{KEY}'",
                f"UPDATE auth.sessions SET not_after=clock_timestamp() WHERE id='{ADMIN}'",
                f"SELECT pg_advisory_xact_lock(hashtextextended('evidence-artifact:{DOCUMENT}',0))",
                f"SELECT pg_advisory_xact_lock(hashtextextended('deal-ref:{DRAFT}',0))",
            ]
            for change in changes:
                self.assertIn('lock timeout', self.sql("SET lock_timeout='100ms'; "+change, fail=True))
        finally:
            _, errors = holder.communicate('COMMIT;\n\\q\n',timeout=5)
        self.assertEqual(holder.returncode, 0, errors)
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_reviews WHERE renewal_root_id IS NOT NULL'),'0')


class RenewalAuthorityLockTests(RenewalAuthorityLockCases, DownstreamEffectiveTests):
    def setUp(self):
        super().setUp()
        self.sql(MIGRATION.read_text())


if __name__=='__main__':
    raise SystemExit(main(RenewalAuthorityLockTests,[n for n in RenewalAuthorityLockCases.__dict__ if n.startswith('test_signature_renewal_locks_')]))
