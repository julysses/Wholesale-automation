"""Observed lock-wait authorization checks for contract drafts on disposable SQL."""
import select
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from acquisition_contract_tests import ContractDraftTests, DRAFT
from test_acquisition_workspace import ADMIN, PG, main


class ContractContentionTests(ContractDraftTests):
    def blocked_draft(self, change):
        holder=subprocess.Popen([str(PG/'psql'),'-X','-qAt','-v','ON_ERROR_STOP=1','-h',self.socket,
            '-U','test_admin','-d','acquisition_test'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,env=self.env)
        try:
            holder.stdin.write(f"BEGIN; DO $$ BEGIN PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:{DRAFT}',0)); END $$;\n\\echo locked\n")
            holder.stdin.flush()
            self.assertTrue(select.select([holder.stdout],[],[],5)[0])
            self.assertEqual(holder.stdout.readline().strip(),'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.draft,fail=True)
                try:
                    end=time.monotonic()+5; waiting='0'
                    while time.monotonic()<end:
                        waiting=self.sql("SELECT count(*) FROM pg_stat_activity WHERE wait_event='advisory' AND query LIKE '%public.create_acquisition_contract_draft%'")
                        if waiting!='0':break
                        time.sleep(.02)
                    self.assertNotEqual(waiting,'0','Draft must actually wait before changing authority')
                    change()
                finally:
                    holder.stdin.write('COMMIT;\n');holder.stdin.flush()
                result=future.result(timeout=5)
            self.assertEqual(self.sql('SELECT count(*) FROM public.acquisition_contract_versions'),'0')
            return result
        finally:
            holder.communicate('\\q\n',timeout=5)

    def test_contract_wait_session_expiration(self):
        error=self.blocked_draft(lambda:self.sql(f"UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE user_id='{ADMIN}'"))
        self.assertIn('Current workspace session required',error)

    def test_contract_wait_approval_revocation(self):
        error=self.blocked_draft(lambda:self.review_offer(identity='d0000000-0000-4000-8000-000000000002',status='approval_revoked',sequence=2))
        self.assertIn('Current reviewed amount and property required',error)

    def test_contract_wait_membership_revocation(self):
        error=self.blocked_draft(lambda:self.sql(f"UPDATE workspace_memberships SET status='revoked' WHERE user_id='{ADMIN}'"))
        self.assertIn('Current workspace session required',error)


if __name__=='__main__':
    raise SystemExit(main(ContractContentionTests,test_names=[name for name in ContractContentionTests.__dict__ if name.startswith('test_contract_wait_')]))
