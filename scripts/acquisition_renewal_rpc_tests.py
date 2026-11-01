"""Real role-scoped SQL RPC grants for renewal discovery and personal saving."""
import json
from acquisition_renewal_choice_tests import RenewalChoiceTests
from acquisition_disposition_review_tests import REVIEW
from acquisition_personal_renewal_tests import FIRST
from schemas.acquisition_renewal_choices import ReviewRenewalIndex
from test_acquisition_workspace import ROOT,WORKSPACE,WORKSPACE_B,ADMIN,OTHER,CALLER,OPERATOR,literal,main
from acquisition_contract_document_tests import DRAFT
MIGRATION=ROOT/'frontend/supabase/migrations/20261101110902_acquisition_review_renewal_api.sql'


class RenewalRpcCases:
    def renewal_index_rpc(self,actor=ADMIN,workspace=WORKSPACE,fail=False,**kwargs):
        value=self.sql(f"SELECT public.acquisition_review_renewal_index('{workspace}','{DRAFT}',2)",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def renewal_save_rpc(self,args,actor=ADMIN,fail=False,**kwargs):
        fields=','.join(k+'=>'+('NULL' if v is None else ('true' if v else 'false') if isinstance(v,bool) else literal(str(v))) for k,v in args.items())
        value=self.sql('SELECT public.record_acquisition_review_renewal('+fields+')',user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def test_signature_renewal_rpc_discovery_roles_exact_retry_and_pause(self):
        self.prepare_handoff(True)
        index=ReviewRenewalIndex.model_validate(self.renewal_index_rpc())
        self.assertEqual(len(index.items),5)
        self.assertEqual([r.kind for r in index.items],['deadline_resolution','deadline_resolution','executed_contract','title_findings','disposition_findings'])
        args=self.renewal_command()
        for actor in (OTHER,CALLER,OPERATOR):
            self.renewal_index_rpc(actor=actor,fail=True);self.renewal_save_rpc(args,actor=actor,fail=True)
        for role in ('anon','service_role'):
            self.renewal_index_rpc(role=role,fail=True);self.renewal_save_rpc(args,role=role,fail=True)
        self.renewal_index_rpc(workspace=WORKSPACE_B,fail=True)
        self.renewal_save_rpc(args|dict(p_workspace=WORKSPACE_B),fail=True)
        self.renewal_index_rpc(aal='aal1',fail=True);self.renewal_save_rpc(args,aal='aal1',fail=True)
        self.assertFalse(self.renewal_save_rpc(args)['duplicate'])
        self.assertTrue(self.renewal_save_rpc(args)['duplicate'])
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.renewal_save_rpc(args)['duplicate'])
        self.assertTrue(all(item['status']=='paused' for item in self.renewal_index_rpc()['items']))
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{FIRST}' AND action='renewed'"),'1')
        self.assertEqual(next(r for r in self.renewal_index_rpc()['items'] if r['root_review_id']==REVIEW)['current_review']['review_id'],FIRST)


class RenewalRpcTests(RenewalRpcCases,RenewalChoiceTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(RenewalRpcTests,[n for n in RenewalRpcCases.__dict__ if n.startswith('test_signature_renewal_rpc_')]))
