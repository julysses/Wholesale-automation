"""Disposable real PostgreSQL contract draft acceptance, no external services."""
import json
from concurrent.futures import ThreadPoolExecutor

from test_acquisition_workspace import WorkspaceTests, main, ROOT, ADMIN, OTHER, CALLER, OPERATOR, WORKSPACE, WORKSPACE_B, LEAD, LEAD_B, literal

MIGRATION = ROOT/'frontend/supabase/migrations/20261031221633_acquisition_contract_drafts.sql'
DRAFT='ac000000-0000-4000-8000-000000000001'
SECOND='ac000000-0000-4000-8000-000000000002'
OFFER='c0000000-0000-4000-8000-000000000001'
RELATION='70000000-0000-4000-8000-000000000001'


class ContractDraftCases:
    def seed_historical_contract(self):
        if self._testMethodName=='test_contract_draft_does_not_adopt_historical_deal':
            # Seed the legacy record before workspace binding, through its actual
            # existing write role. Do not bypass the new scoped-write guard.
            self.sql(f"INSERT INTO public.deals(id,lead_id,stage,deal_name) VALUES('{SECOND}','{LEAD}','offer_made','Historical')",user=ADMIN,role='service_role')

    def prepare_contract_fixture(self):
        self.ready_offer(); self.propose_offer(); self.review_offer()
        self.sql(f"UPDATE public.leads SET owner_first_name='Synthetic',owner_last_name='Seller' WHERE id='{LEAD}';")
        self.owner(); self.owner_property()

    def draft(self, identity=DRAFT, workspace=WORKSPACE, actor=ADMIN, seq=2, name='Review draft', relationship=RELATION, fail=False, **kwargs):
        result=self.sql(f"SELECT public.create_acquisition_contract_draft('{identity}','{workspace}','{OFFER}',{seq},'{relationship}',{literal(name)})",user=actor,fail=fail,**kwargs)
        return result if fail else json.loads(result)

    def test_contract_draft_exact_retry_and_atomic_audit(self):
        first=self.draft(); self.assertFalse(first['execution_authorized']); self.assertFalse(first['duplicate'])
        self.assertTrue(self.draft()['duplicate'])
        self.draft(name='Changed',fail=True)
        self.assertEqual(self.sql('SELECT count(*) FROM public.acquisition_contract_versions'),'1')
        self.assertEqual(self.sql("SELECT count(*) FROM public.audit_logs WHERE entity_type='acquisition_contract'"),'1')
        self.assertEqual(self.sql(f"SELECT stage||':'||acquisition_status FROM public.deals WHERE id='{DRAFT}'"),'offer_made:draft')
        self.assertEqual(self.sql(f"SELECT contract_price IS NULL AND contract_date IS NULL AND buyer_id IS NULL AND psa_doc_url IS NULL FROM public.deals WHERE id='{DRAFT}'"),'t')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.draft()['duplicate'])
        self.draft(identity=SECOND,fail=True)

    def test_contract_draft_scope_roles_and_session(self):
        self.draft(actor=OTHER,fail=True); self.draft(workspace=WORKSPACE_B,fail=True)
        self.member(target=CALLER,role='acquisition_caller'); self.draft(actor=CALLER,fail=True)
        self.member(target=CALLER,role='agency_manager'); self.draft(actor=CALLER,fail=True)
        self.draft(aal='aal1',fail=True); self.draft(session=False,fail=True)
        self.draft(role='service_role',fail=True)
        self.member(); self.draft(actor=OPERATOR)
        self.assertEqual(self.sql('SELECT count(*) FROM public.acquisition_contract_versions',user=OTHER),'0')
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.deals WHERE id='{DRAFT}'",user=OTHER),'0')
        self.member(status='revoked'); self.draft(actor=OPERATOR,fail=True)

    def test_contract_draft_stale_amount_and_relationship(self):
        self.draft(seq=1,fail=True)
        self.draft(relationship=SECOND,fail=True)
        self.review_offer(identity='d0000000-0000-4000-8000-000000000002',status='approval_revoked',sequence=2)
        self.draft(fail=True)
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.deals WHERE lead_id='{LEAD}'"),'0')

    def test_contract_draft_concurrent_creations_keep_one_deal(self):
        def attempt(identity):
            try:return self.draft(identity=identity)
            except AssertionError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,[DRAFT,SECOND]))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.sql(f"SELECT count(*) FROM public.deals WHERE lead_id='{LEAD}'"),'1')
        self.assertEqual(self.sql('SELECT count(*) FROM public.acquisition_contract_versions'),'1')

    def test_contract_draft_raw_mutations_and_legacy_behavior(self):
        self.draft()
        for query in [f"UPDATE public.deals SET workspace_id=NULL WHERE id='{DRAFT}'",
                      f"DELETE FROM public.deals WHERE id='{DRAFT}'",
                      f"UPDATE public.deals SET lead_id='{LEAD_B}' WHERE id='{DRAFT}'",
                      f"INSERT INTO public.deals(id,lead_id,stage) VALUES('{SECOND}','{LEAD}','offer_made')",
                      'TRUNCATE public.deals', 'TRUNCATE public.acquisition_contract_versions',
                      'DELETE FROM public.acquisition_contract_versions']:
            self.sql(query,user=ADMIN,role='service_role',fail=True)
        self.sql(f"INSERT INTO public.deals(id,lead_id,stage,deal_name) VALUES('{SECOND}','{LEAD_B}','offer_made','Legacy')",user=ADMIN,role='service_role')
        self.sql(f"UPDATE public.deals SET deal_name='Legacy updated' WHERE id='{SECOND}'",user=ADMIN,role='service_role')
        self.assertEqual(self.sql(f"SELECT workspace_id IS NULL FROM public.deals WHERE id='{SECOND}'"),'t')

    def test_contract_draft_does_not_adopt_historical_deal(self):
        self.draft(fail=True)
        self.assertEqual(self.sql(f"SELECT workspace_id IS NULL AND deal_name='Historical' FROM public.deals WHERE id='{SECOND}'"),'t')
        self.assertEqual(self.sql('SELECT count(*) FROM public.acquisition_contract_versions'),'0')


class ContractDraftTests(ContractDraftCases, WorkspaceTests):
    def setUp(self):
        super().setUp()
        self.sql("CREATE UNIQUE INDEX IF NOT EXISTS deals_one_active_lead ON public.deals(lead_id) WHERE stage NOT IN ('closed','cancelled'); GRANT ALL ON public.deals TO service_role;")
        self.sql(MIGRATION.read_text())
        self.seed_historical_contract()
        self.prepare_contract_fixture()


if __name__=='__main__':
    raise SystemExit(main(ContractDraftTests, test_names=[name for name in ContractDraftCases.__dict__ if name.startswith('test_contract_draft_')]))
