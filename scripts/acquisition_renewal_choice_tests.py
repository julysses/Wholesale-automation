"""Scoped private read choices; no public grant or automatic approval."""
import json
from copy import deepcopy
from pydantic import ValidationError
from datetime import datetime, timedelta, timezone
from schemas.acquisition_renewal_choices import ReviewRenewalCandidate
from acquisition_personal_renewal_tests import PersonalRenewalTests, SCAN, FIRST
from acquisition_disposition_review_tests import REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_deadline_review_tests import DEADLINE_REVIEW
from test_acquisition_workspace import ROOT, WORKSPACE, WORKSPACE_B, ADMIN, OTHER, CALLER, literal, main
from acquisition_contract_document_tests import DRAFT
MIGRATION=ROOT/'frontend/supabase/migrations/20261101110243_acquisition_review_renewal_choices.sql'


class RenewalChoiceCases:
    def renewal_choice(self,root=REVIEW,actor=ADMIN,workspace=WORKSPACE,version=2,aal='aal2',fail=False):
        claims=json.dumps(dict(sub=actor,role='authenticated',aal=aal,session_id=actor))
        value=self.sql(f"BEGIN; SET LOCAL request.jwt.claims={literal(claims)}; SELECT private.acquisition_review_renewal_candidate('{workspace}','{DRAFT}',{version},'{root}'); COMMIT;",fail=fail)
        if fail:return value
        parsed=json.loads(value)
        ReviewRenewalCandidate.model_validate(parsed)
        return parsed

    def test_signature_renewal_choice_exact_originals_read_only_and_save_binding(self):
        self.prepare_handoff(True);self.transition(self.handoff_args())
        before=self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r')
        audit=self.sql('SELECT count(*) FROM audit_logs')
        for root in (DEADLINE_REVIEW,EXEC_REVIEW,TITLE_REVIEW,REVIEW):
            choice=self.renewal_choice(root)
            self.assertEqual(choice['status'],'ready_for_human_review')
            self.assertFalse(choice['execution_authorized'])
            self.assertEqual(choice['root_review_id'],root)
            self.assertTrue(choice['original']['findings'])
            self.assertNotIn('policy_snapshot',choice['candidate'])
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM acquisition_contract_reviews r'))
        self.assertEqual(audit,self.sql('SELECT count(*) FROM audit_logs'))
        choice=self.renewal_choice();candidate=choice['candidate']
        args=self.renewal_command()|dict(p_previous=candidate['previous_review_id'],p_policy=candidate['policy_id'],
            p_expected_sequence=candidate['expected_sequence'],p_snapshot=candidate['expected_snapshot_sha256'])
        self.personal_renewal(args)
        self.assertEqual(self.renewal_choice()['current_review']['review_id'],FIRST)

    def test_signature_renewal_choice_permission_pause_and_withdrawal(self):
        self.prepare_handoff(True)
        for identity in (dict(actor=OTHER),dict(actor=CALLER),dict(workspace=WORKSPACE_B),dict(aal='aal1')):
            self.renewal_choice(fail=True,**identity)
        self.sql('UPDATE private.acquisition_activation SET enabled=false')
        paused=self.renewal_choice();self.assertEqual(paused['status'],'paused');self.assertIsNone(paused['candidate'])
        self.sql('UPDATE private.acquisition_activation SET enabled=true')
        self.disposition_review(self.disposition_review_args(p_id=FIRST,p_expected_sequence=1,p_status='withdrawn',p_expires=None,
            p_personally_reviewed=False,p_original_review=REVIEW,p_findings=None))
        held=self.renewal_choice();self.assertEqual(held['status'],'withdrawn_or_superseded');self.assertIsNone(held['candidate'])
        self.assertIsNone(held['current_review'])

    def test_signature_renewal_choice_requires_support_before_downstream_and_caps_expiry(self):
        self.prepare_handoff(True)
        self.record_contract_scan(self.signed_contract(request=SCAN))
        self.assertEqual(self.renewal_choice(DEADLINE_REVIEW)['status'],'ready_for_human_review')
        for root in (EXEC_REVIEW,TITLE_REVIEW,REVIEW):
            held=self.renewal_choice(root);self.assertEqual(held['status'],'supporting_review_required');self.assertIsNone(held['candidate'])
        roots=json.loads(self.sql("SELECT jsonb_agg(id ORDER BY sequence) FROM acquisition_contract_reviews WHERE kind='deadline_resolution'"))+[EXEC_REVIEW,TITLE_REVIEW,REVIEW]
        expires=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()
        for index,root in enumerate(roots,10):
            choice=self.renewal_choice(root);self.assertEqual(choice['status'],'ready_for_human_review')
            cap=datetime.fromisoformat(choice['candidate']['max_expires_at'])
            for dep in choice['dependencies']:
                self.assertTrue(dep['approval_current']);self.assertLessEqual(cap,datetime.fromisoformat(dep['expires_at']))
            self.personal_renewal(self.renewal_command(root,identity=f'af140000-0000-4000-8000-{index:012d}',expires=expires))
        self.assertEqual(self.renewal_choice()['current_review']['approval_current'],True)

    def test_signature_renewal_choice_changed_report_path_and_evidence_are_held(self):
        from acquisition_title_review_tests import FINDINGS_POLICY
        from acquisition_disposition_plan_tests import SECOND
        self.prepare_handoff(True)
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=NULL,title_report_timezone=NULL,title_report_max_age_seconds=NULL WHERE id='{FINDINGS_POLICY}'")
        held=self.renewal_choice(TITLE_REVIEW)
        self.assertEqual(held['status'],'report_review_required');self.assertIsNone(held['candidate'])
        self.sql(f"UPDATE private.acquisition_contract_review_policies SET title_report_max_age_days=1,title_report_timezone='UTC',title_report_max_age_seconds=86400 WHERE id='{FINDINGS_POLICY}'")
        self.plan(self.plan_args(p_id=SECOND,p_expected_sequence=1))
        held=self.renewal_choice();self.assertEqual(held['status'],'purchase_path_changed');self.assertIsNone(held['candidate'])
        self.sql('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp()')
        held=self.renewal_choice(DEADLINE_REVIEW)
        self.assertEqual(held['status'],'evidence_review_required');self.assertIsNone(held['candidate'])

    def test_signature_renewal_choice_schema_rejects_mismatched_authority(self):
        self.prepare_handoff(True);choice=self.renewal_choice()
        for patch in ({'execution_authorized':True},{'execution_authorized':0},{'status':'paused'}, {'dependencies':[]}, {'private_policy':{}}):
            with self.assertRaises(ValidationError):ReviewRenewalCandidate.model_validate(choice|patch)
        for patch in ({'previous_review_id':FIRST},{'max_expires_at':choice['checked_at']},{'sources':[]},{'policy_snapshot':{}}):
            with self.assertRaises(ValidationError):ReviewRenewalCandidate.model_validate(choice|dict(candidate=choice['candidate']|patch))
        changed=deepcopy(choice);changed['dependencies'][0]['approval_current']=False
        with self.assertRaises(ValidationError):ReviewRenewalCandidate.model_validate(changed)
        changed=deepcopy(choice);changed['candidate']['sources'][0]['source_version']=3
        with self.assertRaises(ValidationError):ReviewRenewalCandidate.model_validate(changed)


class RenewalChoiceTests(RenewalChoiceCases,PersonalRenewalTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(RenewalChoiceTests,[n for n in RenewalChoiceCases.__dict__ if n.startswith('test_signature_renewal_choice_')]))
