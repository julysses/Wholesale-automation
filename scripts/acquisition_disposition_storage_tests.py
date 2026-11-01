"""Disposition storage binds exact proposal, execution and post-execution title."""
import json
from copy import deepcopy
from acquisition_disposition_plan_tests import DispositionPlanTests,PLAN
from acquisition_title_review_tests import TITLE_REVIEW
from acquisition_execution_review_tests import EXEC_REVIEW,EXEC_POLICY
from acquisition_contract_document_tests import DRAFT
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101074125_acquisition_disposition_findings_storage.sql'
POLICY='af106000-0000-4000-8000-000000000001'
REVIEW='af106000-0000-4000-8000-000000000002'
WITHDRAW='af106000-0000-4000-8000-000000000003'

class DispositionStorageCases:
    def disposition_findings(self,row,assignment=False):
        def finding():return dict(finding='satisfactory',note='Human reviewed original contract clauses and supporting legal evidence.',required_action=None,
            sources=[dict(artifact_id=row['artifact_id'],artifact_version=row['source_version'],sha256=row['sha256'],locator='Original contract clause, page 4')])
        return dict(exit_type='wholesale_assignment' if assignment else 'principal_acquisition',
            **{name:finding() for name in ('contractual_interest','closing_structure','remaining_obligations')},
            assignment={name:finding() for name in ('assignment_provisions','legal_basis','seller_disclosure_requirements','assignee_disclosure_requirements')} if assignment else None)

    def prepare_disposition_storage(self,assignment=False,title_held=False):
        self.prepare_title_review();self.title_review(self.title_review_args(**(dict(p_status='requires_resolution',p_expires=None) if title_held else {})))
        self.plan(self.plan_args(p_exit_type='wholesale_assignment' if assignment else 'principal_acquisition'))
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id','{POLICY}','kind','disposition_findings'))).* FROM private.acquisition_contract_review_policies p WHERE id='{EXEC_POLICY}'")
        original=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{EXEC_REVIEW}'"))
        value=self.disposition_findings(original,assignment)
        original.update(id=REVIEW,kind='disposition_findings',sequence=1,policy_id=POLICY,execution_findings=None,execution_sources=None,
            disposition_findings=value,disposition_sources=[dict(artifact_id=original['artifact_id'],source_version=original['source_version'],verification_id=original['verification_id'],sha256=original['sha256'],purpose='purchase_contract',expires_at=original['expires_at'])],
            disposition_plan_id=PLAN,disposition_exit_type=value['exit_type'],disposition_execution_id=self.sql('SELECT id FROM acquisition_contract_transitions WHERE sequence=2'),
            disposition_title_entry_id=self.sql('SELECT id FROM acquisition_contract_transitions WHERE sequence=3'),disposition_title_review_id=TITLE_REVIEW,
            disposition_title_status='requires_resolution' if title_held else 'approved',disposition_original_review_id=None,disposition_original_status=None)
        return original

    def disposition_valid(self,value,approved=True,exit_type='principal_acquisition'):
        return self.sql(f"SELECT private.valid_disposition_findings({literal(json.dumps(value))}::jsonb,2,{'true' if approved else 'false'},{literal(exit_type)})")

    def test_signature_disposition_storage_validates_findings_sources_and_exit(self):
        row=self.prepare_disposition_storage(True);value=row['disposition_findings']
        self.assertEqual(self.disposition_valid(value,exit_type='wholesale_assignment'),'t')
        self.assertEqual(self.disposition_valid(value),'f')
        for name in ('assignment_provisions','legal_basis','seller_disclosure_requirements','assignee_disclosure_requirements'):
            held=deepcopy(value);held['assignment'][name].update(finding='unknown',required_action='Obtain the missing original and resolve this specific requirement.',sources=[])
            self.assertEqual(self.disposition_valid(held,exit_type='wholesale_assignment'),'f')
            self.assertEqual(self.disposition_valid(held,False,'wholesale_assignment'),'t')
            held['assignment'][name]['required_action']=None;self.assertEqual(self.disposition_valid(held,False,'wholesale_assignment'),'f')
        for patch in ({'artifact_version':3},{'artifact_version':True},{'sha256':'e'*64},{'locator':'\n'}, {'locator':' '}):
            bad=deepcopy(value);bad['assignment']['legal_basis']['sources'][0].update(patch)
            self.assertEqual(self.disposition_valid(bad,exit_type='wholesale_assignment'),'f')
        bad=deepcopy(value);bad['assignment']['legal_basis']['sources']*=2
        self.assertEqual(self.disposition_valid(bad,exit_type='wholesale_assignment'),'f')
        for bad in (None,[],{},value|{'marketing_authorized':True},value|{'assignment':None}):
            self.assertEqual(self.disposition_valid(bad,exit_type='wholesale_assignment'),'f')

    def test_signature_disposition_storage_binds_original_plan_title_execution_and_journal(self):
        row=self.prepare_disposition_storage();before=self.sql(f"SELECT to_jsonb(d)::text FROM deals d WHERE id='{DRAFT}'")
        for patch in ({'disposition_plan_id':None},{'disposition_plan_id':REVIEW},{'disposition_exit_type':'wholesale_assignment'},
            {'disposition_execution_id':row['disposition_title_entry_id']},{'disposition_title_entry_id':row['disposition_execution_id']},
            {'disposition_title_review_id':EXEC_REVIEW},{'disposition_title_status':'requires_resolution'},
            {'workspace_id':WORKSPACE_B},{'contract_version':1},{'disposition_findings':None},{'disposition_sources':[]},{'kind':'contract_review'}):
            self.insert_title_fixture(row|patch,fail=True)
        for field,value in (('verification_id',REVIEW),('source_version',3-row['source_version']),('sha256','e'*64),('purpose','title_report')):
            bad=deepcopy(row);bad['disposition_sources'][0][field]=value;self.insert_title_fixture(bad,fail=True)
        bad=deepcopy(row);bad['disposition_sources']*=2;self.insert_title_fixture(bad,fail=True)
        self.insert_title_fixture(row)
        self.assertEqual(before,self.sql(f"SELECT to_jsonb(d)::text FROM deals d WHERE id='{DRAFT}'"))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.sql(f"UPDATE acquisition_contract_reviews SET note='Rewrite this immutable original disposition decision' WHERE id='{REVIEW}'",fail=True)
        self.sql(f"DELETE FROM acquisition_contract_reviews WHERE id='{REVIEW}'",fail=True)

    def test_signature_disposition_storage_holds_and_original_withdrawal_preserve_all_roots(self):
        row=self.prepare_disposition_storage(True,title_held=True)
        self.insert_title_fixture(row,fail=True)  # Approval cannot bind a held title decision.
        held=deepcopy(row);held.update(status='requires_resolution',expires_at=None)
        held['disposition_findings']['assignment']['legal_basis'].update(finding='requires_resolution',sources=[],required_action='Obtain counsel review of the original assignment provisions.')
        self.insert_title_fixture(held)
        withdrawn=held|dict(id=WITHDRAW,sequence=2,status='withdrawn',personally_reviewed=False,disposition_findings=None,disposition_sources=None,
            disposition_original_review_id=REVIEW,disposition_original_status='requires_resolution')
        for patch in ({'disposition_original_review_id':None},{'disposition_original_status':'approved'}, {'disposition_title_status':'approved'},
            {'disposition_exit_type':'principal_acquisition'},{'disposition_plan_id':WITHDRAW},{'disposition_findings':held['disposition_findings']}):self.insert_title_fixture(withdrawn|patch,fail=True)
        self.insert_title_fixture(withdrawn)
        self.assertEqual(self.sql(f"SELECT disposition_original_review_id,disposition_plan_id,disposition_title_review_id FROM acquisition_contract_reviews WHERE id='{WITHDRAW}'"),REVIEW+'|'+PLAN+'|'+TITLE_REVIEW)

    def test_signature_disposition_storage_retains_scope_and_disables_generic_writer(self):
        row=self.prepare_disposition_storage();self.insert_title_fixture(row);self.member()
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_reviews WHERE id='{REVIEW}'",user=ADMIN),'1')
        for actor in (OTHER,OPERATOR):self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_reviews WHERE id='{REVIEW}'",user=actor),'0')
        for kwargs in ({'aal':'aal1'},{'session':False}):self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_reviews WHERE id='{REVIEW}'",user=ADMIN,**kwargs),'0')
        for role in ('authenticated','service_role'):
            self.insert_title_fixture(row|dict(id=WITHDRAW,sequence=2),user=ADMIN,role=role,fail=True)
            self.sql('TRUNCATE acquisition_contract_reviews',user=ADMIN,role=role,fail=True)
        self.sql("SELECT private.valid_disposition_findings('{}',2,false,'principal_acquisition')",user=ADMIN,fail=True)
        self.review(self.review_args(p_kind='disposition_findings',p_version=2),fail=True)

class DispositionStorageTests(DispositionStorageCases,DispositionPlanTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':raise SystemExit(main(DispositionStorageTests,[n for n in DispositionStorageCases.__dict__ if n.startswith('test_signature_disposition_storage_')]))
