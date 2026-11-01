"""Existing scoped state endpoints recognize exact renewed heads, never old IDs."""
import json
from datetime import datetime,timedelta,timezone
from acquisition_renewal_rpc_tests import RenewalRpcTests
from acquisition_contract_document_tests import DRAFT
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_disposition_review_tests import REVIEW
from acquisition_deadline_review_tests import DEADLINE_REVIEW
from acquisition_personal_renewal_tests import FIRST,SCAN
from test_acquisition_workspace import ROOT,WORKSPACE,WORKSPACE_B,ADMIN,OTHER,CALLER,main
MIGRATION=ROOT/'frontend/supabase/migrations/20261101112744_acquisition_effective_review_state.sql'


class EffectiveStateCases:
    def existing_current(self,kind,review,at='clock_timestamp()'):
        return self.sql(f"SELECT private.{kind}_review_current('{review}',{at})")

    def existing_state(self,kind,actor=ADMIN,workspace=WORKSPACE,fail=False,**kwargs):
        term=",'closing_deadline'" if kind=='deadline' else ''
        value=self.sql(f"SELECT public.{kind}_review_state('{workspace}','{DRAFT}',2{term})",user=actor,fail=fail,**kwargs)
        return value if fail else json.loads(value)

    def renew_state_chain(self):
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution' AND renewal_root_id IS NULL"))+[EXEC_REVIEW,TITLE_REVIEW,REVIEW]
        expires=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat();mapping={}
        for n,root in enumerate(roots,1):
            identity=f'af142000-0000-4000-8000-{n:012d}'
            self.renewal_save_rpc(self.renewal_command(root,identity=identity,expires=expires));mapping[root]=identity
        return mapping

    def test_signature_effective_state_exact_heads_preserve_originals_and_handoff(self):
        self.prepare_handoff(True);self.transition(self.handoff_args())
        history=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        originals=self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r')
        pairs=[('deadline',DEADLINE_REVIEW),('execution',EXEC_REVIEW),('title',TITLE_REVIEW),('disposition',REVIEW)]
        for kind,root in pairs:self.assertTrue(self.existing_state(kind)['approval_current'])
        mapping=self.renew_state_chain()
        for kind,root in pairs:
            self.assertEqual(self.existing_current(kind,root),'f')
            self.assertEqual(self.existing_current(kind,mapping[root]),'t')
            state=self.existing_state(kind)
            self.assertEqual(state['review_id'],mapping[root]);self.assertTrue(state['approval_current']);self.assertFalse(state['execution_authorized'])
            self.assertEqual(self.existing_current(kind,mapping[root],"clock_timestamp()+interval '2 minutes'"),'f')
        self.assertEqual(originals,self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r WHERE renewal_root_id IS NULL'))
        self.assertEqual(history,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t'))

    def test_signature_effective_state_no_automatic_downstream_approval_and_scan_revocation(self):
        self.prepare_handoff(True)
        self.renewal_save_rpc(self.renewal_command(DEADLINE_REVIEW,identity=FIRST))
        self.assertTrue(self.existing_state('deadline')['approval_current'])
        for kind in ('execution','title','disposition'):self.assertFalse(self.existing_state(kind)['approval_current'])
        mapping=self.renew_state_chain()
        self.assertTrue(self.existing_state('disposition')['approval_current'])
        self.record_contract_scan(self.signed_contract(request=SCAN))
        for kind in ('deadline','execution','title','disposition'):self.assertFalse(self.existing_state(kind)['approval_current'])
        self.assertEqual(self.sql(f"SELECT status FROM acquisition_contract_reviews WHERE id='{mapping[REVIEW]}'"),'approved')

    def test_signature_effective_state_scope_private_grants_pause_and_withdrawal(self):
        self.prepare_handoff(True);mapping=self.renew_state_chain()
        for kind in ('deadline','execution','title','disposition'):
            for actor in (OTHER,CALLER):self.existing_state(kind,actor=actor,fail=True)
            self.existing_state(kind,workspace=WORKSPACE_B,fail=True)
            self.existing_state(kind,aal='aal1',fail=True)
        self.sql(f"SELECT private.acquisition_review_effective_exact_current('{mapping[REVIEW]}','disposition_findings',clock_timestamp())",user=ADMIN,fail=True)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        for kind in ('deadline','execution','title','disposition'):self.assertFalse(self.existing_state(kind)['approval_current'])
        self.disposition_review(self.disposition_review_args(p_id=FIRST,p_expected_sequence=2,p_status='withdrawn',p_expires=None,
            p_personally_reviewed=False,p_original_review=mapping[REVIEW],p_findings=None))
        self.assertEqual(self.existing_state('disposition')['status'],'withdrawn')
        self.assertEqual(self.existing_current('disposition',mapping[REVIEW]),'f')


class EffectiveStateTests(EffectiveStateCases,RenewalRpcTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(EffectiveStateTests,[n for n in EffectiveStateCases.__dict__ if n.startswith('test_signature_effective_state_')]))
