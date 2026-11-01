"""Renewed review authority through controlled handoffs with immutable original roots."""
import json
from acquisition_effective_state_tests import EffectiveStateTests
from acquisition_disposition_transition_storage_tests import TRANSITION
from acquisition_disposition_review_tests import REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_deadline_review_tests import DEADLINE_POLICY
from test_acquisition_workspace import ROOT,WORKSPACE,ADMIN,main
from acquisition_contract_document_tests import DRAFT
MIGRATION=ROOT/'frontend/supabase/migrations/20261101113021_acquisition_effective_review_handoffs.sql'


class EffectiveHandoffCases:
    def test_signature_effective_handoff_renewed_chain_preserves_roots_and_audits_exact_heads(self):
        self.prepare_handoff(True);mapping=self.renew_state_chain()
        before=self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t')
        candidate=json.loads(self.sql(f"SELECT public.contract_transition_choice('{WORKSPACE}','{DRAFT}',2)",user=ADMIN))
        self.assertEqual(candidate['status'],'ready_for_human_review')
        self.assertEqual(candidate['candidate']['disposition_review_id'],REVIEW)
        self.assertEqual(candidate['candidate']['execution_review_id'],EXEC_REVIEW)
        self.assertFalse(self.transition(self.handoff_args())['duplicate'])
        self.assertTrue(self.transition(self.handoff_args())['duplicate'])
        saved=json.loads(self.sql(f"SELECT to_jsonb(t) FROM acquisition_contract_transitions t WHERE id='{TRANSITION}'"))
        self.assertEqual(saved['disposition_review_id'],REVIEW);self.assertEqual(saved['disposition_title_review_id'],TITLE_REVIEW)
        self.assertEqual(saved['execution_review_id'],EXEC_REVIEW)
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(t) ORDER BY sequence) FROM acquisition_contract_transitions t WHERE sequence<4'))
        snapshot=json.loads(self.sql(f"SELECT new_value->'review_authority' FROM audit_logs WHERE entity_id='{TRANSITION}'"))
        self.assertEqual({r['root_id']:r['review_id'] for r in snapshot},mapping)
        self.assertEqual(self.sql(f"SELECT count(*) FROM audit_logs WHERE entity_id='{TRANSITION}'"),'1')
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        self.assertTrue(self.transition(self.handoff_args())['duplicate'])

    def test_signature_effective_handoff_execution_and_title_keep_original_execution_root(self):
        from datetime import datetime,timedelta,timezone
        from acquisition_executed_transition_tests import ExecutedTransitionCases,EXEC_TRANSITION
        from acquisition_title_transition_tests import TITLE
        findings=self.prepare_execution_bindings();self.prepare_execution()
        self.execution_review(self.execution_args(p_findings=findings))
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"))+[EXEC_REVIEW]
        expires=(datetime.now(timezone.utc)+timedelta(seconds=90)).isoformat();mapping={}
        for n,root in enumerate(roots,10):
            identity=f'af142000-0000-4000-8000-{n:012d}'
            self.renewal_save_rpc(self.renewal_command(root,identity=identity,expires=expires));mapping[root]=identity
        choice=json.loads(self.sql(f"SELECT public.contract_transition_choice('{WORKSPACE}','{DRAFT}',2)",user=ADMIN))
        self.assertEqual(choice['candidate']['execution_review_id'],EXEC_REVIEW)
        self.transition(ExecutedTransitionCases.executed_args(self))
        self.assertEqual(self.sql(f"SELECT execution_review_id FROM acquisition_contract_transitions WHERE id='{EXEC_TRANSITION}'"),EXEC_REVIEW)
        identity='af142000-0000-4000-8000-000000000019'
        self.renewal_save_rpc(self.renewal_command(EXEC_REVIEW,identity=identity,expires=expires));mapping[EXEC_REVIEW]=identity
        choice=json.loads(self.sql(f"SELECT public.contract_transition_choice('{WORKSPACE}','{DRAFT}',2)",user=ADMIN))
        self.assertEqual(choice['candidate']['execution_review_id'],EXEC_REVIEW)
        self.transition(self.title_args())
        self.assertEqual(self.sql(f"SELECT execution_review_id FROM acquisition_contract_transitions WHERE id='{TITLE}'"),EXEC_REVIEW)
        snapshot=json.loads(self.sql(f"SELECT new_value->'review_authority' FROM audit_logs WHERE entity_id='{TITLE}'"))
        self.assertEqual({r['root_id']:r['review_id'] for r in snapshot},mapping)
        self.assertTrue(self.transition(self.title_args())['duplicate'])

    def test_signature_effective_handoff_renewed_authority_revoked_during_wait(self):
        original=self.prepare_handoff
        def renewed(assignment=False):
            original(True);self.renew_state_chain()
        self.prepare_handoff=renewed
        try:self.handoff_wait('acquisition_contract_review_policies','id',DEADLINE_POLICY)
        finally:self.prepare_handoff=original


class EffectiveHandoffTests(EffectiveHandoffCases,EffectiveStateTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(EffectiveHandoffTests,[n for n in EffectiveHandoffCases.__dict__ if n.startswith('test_signature_effective_handoff_')]))
