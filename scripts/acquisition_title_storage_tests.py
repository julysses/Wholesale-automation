"""Title finding storage is scoped, immutable and distinct from preparation approval."""
import json
from copy import deepcopy
from acquisition_title_document_tests import TitleDocumentTests,TitleDocumentCases,TITLE_FILE,TITLE_POLICY
from acquisition_contract_document_tests import DRAFT
from acquisition_contract_observation_tests import KEY
from acquisition_execution_review_tests import EXEC_REVIEW,EXEC_POLICY
from test_acquisition_workspace import ROOT,main,ADMIN,OTHER,OPERATOR,WORKSPACE,WORKSPACE_B,literal
MIGRATION=ROOT/'frontend/supabase/migrations/20261101055752_acquisition_title_findings_storage.sql'
TITLE_SCAN='af960000-0000-4000-8000-000000000001'
FINDINGS_POLICY='af960000-0000-4000-8000-000000000002'
FINDINGS_REVIEW='af960000-0000-4000-8000-000000000003'
HELD='af960000-0000-4000-8000-000000000004'
WITHDRAW='af960000-0000-4000-8000-000000000005'
NAMES=('ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession')

class TitleStorageCases:
    def title_storage_findings(self):
        source=dict(artifact_id=TITLE_FILE,artifact_version=2,sha256='b'*64,locator='Schedule A, page 1')
        return dict(report_as_of=dict(precision='date',calendar_date='2026-10-31',instant=None),report_as_of_source=deepcopy(source),
            report_note='Synthetic original report date; no cutoff time is inferred.',
            **{name:dict(finding='satisfactory',note='Human-reviewed synthetic source finding for storage checks only.',required_action=None,sources=[deepcopy(source)]) for name in NAMES})

    def valid_title(self,value,approved=True):
        return self.sql(f"SELECT private.valid_title_findings({literal(json.dumps(value))}::jsonb,2,{'true' if approved else 'false'})")

    def prepare_title_storage(self):
        TitleDocumentCases.title_capture(self);TitleDocumentCases.title_document(self)
        self.sql(f"INSERT INTO private.acquisition_contract_verification_key_scopes(workspace_id,key_id,purpose,reviewed_by,approval_ref,valid_from,valid_until) VALUES('{WORKSPACE}','{KEY}','title_report','{ADMIN}','{TITLE_FILE}',clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour')")
        state=json.loads(self.sql(f"SELECT public.contract_document_state('{WORKSPACE}','{DRAFT}',2,'{TITLE_FILE}')",user=ADMIN))
        self.record_contract_scan(self.signed_contract(request=TITLE_SCAN,signing_purposes={'title_report'},contract_version=2,artifact_id=TITLE_FILE,purpose='title_report',retention_policy_id=TITLE_POLICY,retain_until=state['retain_until']))
        self.sql(f"INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id','{FINDINGS_POLICY}','kind','title_findings','purpose','title_report'))).* FROM private.acquisition_contract_review_policies p WHERE id='{EXEC_POLICY}'")
        original=json.loads(self.sql(f"SELECT to_jsonb(r) FROM acquisition_contract_reviews r WHERE id='{EXEC_REVIEW}'"))
        execution=self.sql('SELECT id FROM acquisition_contract_transitions WHERE sequence=2')
        original.update(id=FINDINGS_REVIEW,kind='title_findings',sequence=1,artifact_id=TITLE_FILE,verification_id=TITLE_SCAN,
            purpose='title_report',policy_id=FINDINGS_POLICY,evidence_version=2,sha256='b'*64,execution_findings=None,execution_sources=None,
            title_findings=self.title_storage_findings(),title_execution_transition_id=execution,title_original_review_id=None,title_original_status=None,
            title_sources=[dict(artifact_id=TITLE_FILE,source_version=2,verification_id=TITLE_SCAN,sha256='b'*64,purpose='title_report',expires_at=original['expires_at'])])
        return original

    def insert_title_fixture(self,value,fail=False,**kwargs):
        columns=self.sql("SELECT string_agg(quote_ident(attname),',' ORDER BY attnum) FROM pg_attribute WHERE attrelid='public.acquisition_contract_reviews'::regclass AND attnum>0 AND NOT attisdropped AND attgenerated=''")
        return self.sql(f"INSERT INTO acquisition_contract_reviews({columns}) SELECT {columns} FROM jsonb_populate_record(NULL::acquisition_contract_reviews,{literal(json.dumps(value))}::jsonb)",fail=fail,**kwargs)

    def test_signature_title_storage_validates_uncertainty_sources_and_cutoff_precision(self):
        value=self.title_storage_findings();self.assertEqual(self.valid_title(value),'t')
        for name in NAMES:
            held=deepcopy(value);held[name].update(finding='unknown',required_action='Obtain the missing original and resolve this title issue.',sources=[])
            self.assertEqual(self.valid_title(held),'f');self.assertEqual(self.valid_title(held,False),'t')
            held[name]['required_action']=None;self.assertEqual(self.valid_title(held,False),'f')
        missing=deepcopy(value);missing['report_as_of']=dict(precision='unknown',calendar_date=None,instant=None);missing['report_as_of_source']=None
        self.assertEqual(self.valid_title(missing,False),'t');self.assertEqual(self.valid_title(missing),'f')
        for stamp in ('2026-10-31T12:00:00.1234567Z','2026-10-31','2026-10-31T24:00:00Z','2026-02-30T12:00:00Z'):
            bad=deepcopy(value);bad['report_as_of']=dict(precision='instant',calendar_date=None,instant=stamp);self.assertEqual(self.valid_title(bad),'f')
        for patch in ({'artifact_version':3},{'artifact_version':True},{'sha256':'a'*64},{'locator':' '},{'locator':'page\n1'}):
            bad=deepcopy(value);bad['ownership']['sources'][0].update(patch);self.assertEqual(self.valid_title(bad),'f')
        bad=deepcopy(value);bad['ownership']['sources']*=2;self.assertEqual(self.valid_title(bad),'f')
        for bad in (None,[],{},value|{'execution_authorized':True}):self.assertEqual(self.valid_title(bad),'f')

    def test_signature_title_storage_binds_execution_and_root_journal_without_rewriting_history(self):
        row=self.prepare_title_storage();before=self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v')
        for patch in ({'title_execution_transition_id':None},{'title_execution_transition_id':self.sql('SELECT id FROM acquisition_contract_transitions WHERE sequence=3')},
            {'workspace_id':WORKSPACE_B},{'title_findings':None},{'title_sources':[]},{'title_sources':[{}]},
            {'kind':'title_review'},{'purpose':'purchase_contract'},{'contract_version':1}):self.insert_title_fixture(row|patch,fail=True)
        for field,value in (('verification_id',KEY),('sha256','a'*64),('source_version',1),('purpose','purchase_contract')):
            bad=deepcopy(row);bad['title_sources'][0][field]=value;self.insert_title_fixture(bad,fail=True)
        bad=deepcopy(row);bad['title_sources']*=2;self.insert_title_fixture(bad,fail=True)
        self.insert_title_fixture(row)
        self.assertEqual(before,self.sql('SELECT jsonb_agg(to_jsonb(v) ORDER BY version) FROM acquisition_contract_versions v'))
        self.assertEqual(self.sql('SELECT count(*) FROM acquisition_contract_transitions'),'3')
        self.sql(f"UPDATE acquisition_contract_reviews SET note='Replacement of immutable title finding is forbidden' WHERE id='{FINDINGS_REVIEW}'",fail=True)
        self.sql(f"DELETE FROM acquisition_contract_reviews WHERE id='{FINDINGS_REVIEW}'",fail=True)

    def test_signature_title_storage_holds_and_withdrawals_preserve_original_context(self):
        row=self.prepare_title_storage();held=deepcopy(row);held.update(id=HELD,status='requires_resolution',expires_at=None)
        held['title_findings']['liens_and_payoffs'].update(finding='requires_resolution',required_action='Obtain the payoff and review the recorded lien release.',sources=[])
        self.insert_title_fixture(held|{'expires_at':row['expires_at']},fail=True)
        self.insert_title_fixture(held|{'status':'approved','expires_at':row['expires_at']},fail=True)
        self.insert_title_fixture(held)
        withdrawal=held|dict(id=WITHDRAW,sequence=2,status='withdrawn',personally_reviewed=False,title_findings=None,title_sources=None,
            title_original_review_id=HELD,title_original_status='requires_resolution')
        for patch in ({'title_original_review_id':None},{'title_original_status':'approved'},{'title_original_status':'withdrawn'},
            {'title_original_review_id':EXEC_REVIEW},{'personally_reviewed':True},{'title_findings':held['title_findings']}):self.insert_title_fixture(withdrawal|patch,fail=True)
        self.insert_title_fixture(withdrawal)
        self.assertEqual(self.sql(f"SELECT status,expires_at IS NULL,personally_reviewed FROM acquisition_contract_reviews WHERE id='{HELD}'"),'requires_resolution|t|t')
        self.assertEqual(self.sql(f"SELECT title_original_review_id FROM acquisition_contract_reviews WHERE id='{WITHDRAW}'"),HELD)

    def test_signature_title_storage_retains_isolation_and_does_not_enable_old_rpc(self):
        row=self.prepare_title_storage();self.insert_title_fixture(row)
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_reviews WHERE id='{FINDINGS_REVIEW}'",user=ADMIN),'1')
        self.member()
        for actor in (OTHER,OPERATOR):self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_reviews WHERE id='{FINDINGS_REVIEW}'",user=actor),'0')
        self.assertEqual(self.sql(f"SELECT count(*) FROM acquisition_contract_reviews WHERE id='{FINDINGS_REVIEW}'",user=ADMIN,aal='aal1'),'0')
        for role in ('authenticated','service_role'):
            self.insert_title_fixture(row|{'id':WITHDRAW,'sequence':2},user=ADMIN,role=role,fail=True)
        self.sql("SELECT private.valid_title_findings('{}',2,false)",user=ADMIN,fail=True)
        self.review(self.review_args(p_kind='title_findings',p_version=2),fail=True)
        self.review(self.review_args(p_status='requires_resolution',p_expires=None),fail=True)

class TitleStorageTests(TitleStorageCases,TitleDocumentTests):
    def setUp(self):
        super().setUp();self.sql(MIGRATION.read_text())

if __name__=='__main__':
    raise SystemExit(main(TitleStorageTests,test_names=[n for n in TitleStorageCases.__dict__ if n.startswith('test_signature_title_storage_')]))
