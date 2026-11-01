"""Existing application journeys on per-test copies of the full upgraded catalog."""
import json
import unittest

import psycopg2
from psycopg2 import sql

from test_acquisition_workflow import WorkflowTests
from acquisition_contract_tests import ContractDraftCases
from acquisition_contract_storage_tests import ContractStorageCases
from acquisition_contract_discovery_tests import ContractDiscoveryCases
from acquisition_contract_observation_tests import ContractObservationCases
from acquisition_contract_scan_state_tests import ContractScanStateCases
from acquisition_contract_review_tests import ContractReviewCases
from acquisition_contract_review_candidate_tests import ContractReviewCandidateCases
from acquisition_contract_terms_tests import ContractTermsCases
from acquisition_contract_document_link_tests import ContractDocumentLinkCases
from acquisition_contract_source_review_tests import ContractSourceReviewCases
from acquisition_contract_reference_discovery_tests import ContractReferenceDiscoveryCases
from acquisition_signature_review_tests import SignatureReviewCases
from acquisition_pending_document_tests import PendingDocumentCases
from acquisition_execution_storage_tests import ExecutionStorageCases
from acquisition_execution_review_tests import ExecutionReviewCases
from acquisition_execution_state_tests import ExecutionStateCases
from acquisition_execution_choice_tests import ExecutionChoiceCases
from acquisition_executed_transition_tests import ExecutedTransitionCases
from acquisition_executed_choice_tests import ExecutedChoiceCases
from acquisition_deadline_storage_tests import DeadlineStorageCases
from acquisition_deadline_review_tests import DeadlineReviewCases
from acquisition_deadline_state_tests import DeadlineStateCases
from acquisition_deadline_choice_tests import DeadlineChoiceCases
from acquisition_execution_deadline_tests import ExecutionDeadlineCases
from acquisition_title_transition_tests import TitleTransitionCases
from acquisition_title_choice_tests import TitleChoiceCases
from acquisition_title_document_tests import TitleDocumentCases
from acquisition_title_storage_tests import TitleStorageCases
from acquisition_title_source_tests import TitleSourceCases
from acquisition_title_review_tests import TitleReviewCases
from acquisition_title_candidate_tests import TitleCandidateCases
from acquisition_disposition_plan_tests import DispositionPlanCases
from acquisition_disposition_storage_tests import DispositionStorageCases
from acquisition_disposition_source_tests import DispositionSourceCases
from acquisition_disposition_policy_tests import DispositionPolicyCases
from acquisition_disposition_review_tests import DispositionReviewCases
from acquisition_disposition_candidate_tests import DispositionCandidateCases
from acquisition_disposition_transition_storage_tests import DispositionTransitionStorageCases
from acquisition_disposition_transition_tests import DispositionTransitionCases
from acquisition_disposition_transition_choice_tests import DispositionTransitionChoiceCases
from acquisition_review_renewal_storage_tests import ReviewRenewalStorageCases
from acquisition_review_lineage_head_tests import ReviewLineageHeadCases
from acquisition_review_dependency_tests import ReviewDependencyCases
from acquisition_deadline_effective_tests import DeadlineEffectiveCases
from acquisition_execution_effective_tests import ExecutionEffectiveCases
from acquisition_downstream_effective_tests import DownstreamEffectiveCases
from acquisition_retained_refresh_tests import RetainedRefreshCases
from acquisition_retained_scan_journey_tests import RetainedScanJourneyCases
from acquisition_renewal_authority_lock_tests import RenewalAuthorityLockCases
from acquisition_personal_renewal_tests import PersonalRenewalCases
from acquisition_renewal_choice_tests import RenewalChoiceCases
from acquisition_renewal_rpc_tests import RenewalRpcCases
from acquisition_effective_state_tests import EffectiveStateCases
from acquisition_effective_handoff_tests import EffectiveHandoffCases
from acquisition_original_support_tests import OriginalSupportCases
from acquisition_buyer_storage_tests import BuyerStorageCases
from acquisition_buyer_discovery_tests import BuyerDiscoveryCases
from acquisition_buyer_evidence_storage_tests import BuyerEvidenceStorageCases
from acquisition_transition_choice_tests import TransitionChoiceCases
from acquisition_contract_transition_tests import ContractTransitionCases
from acquisition_signature_candidate_tests import SignatureCandidateCases
from acquisition_contract_document_tests import ContractDocumentCases, ContractUploadAdmissionCases
from test_acquisition_workspace import ADMIN, OTHER, CALLER, OPERATOR, WORKSPACE, WORKSPACE_B, LEAD, LEAD_B, PROPERTY


class FullCatalogWorkflowTests(WorkflowTests):
    def prepare_database(self):
        # No table recreation, omitted constraints, replacement policies or added grants.
        for user, role in ((ADMIN,'admin'),(OTHER,'admin'),(CALLER,'user'),(OPERATOR,'user')):
            self.sql(f"INSERT INTO auth.users(id) VALUES('{user}'); INSERT INTO auth.sessions(id,user_id) VALUES('{user}','{user}'); INSERT INTO profiles(id,email,role,status) VALUES('{user}','{user}@example.test','{role}','approved');")
        self.activate()
        self.create(ADMIN, WORKSPACE)
        self.create(OTHER, WORKSPACE_B)
        self.sql(f"INSERT INTO leads(id,property_address,city,owner_phone_1) VALUES ('{LEAD}','1 Fixture St','Dallas','+12145550101'),('{LEAD_B}','2 Fixture St','Plano','+12145550101'); INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES('{PROPERTY}','TX','Dallas','fixture-parcel','{LEAD}');")

        # Existing county triggers update the daily aggregate during property seeding.
        # Snapshot those two tables after fixture setup, before application requests.
        self.fixture_aggregate_rows={table:self.sql("SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb)::text FROM public."+table+' t') for table in ('tasks','app_notifications')}


class FullCatalogContractTests(ContractDraftCases, FullCatalogWorkflowTests):
    def prepare_database(self):
        super().prepare_database()
        self.seed_historical_contract()

    def setUp(self):
        super().setUp()
        self.prepare_contract_fixture()


class FullCatalogDocumentTests(BuyerEvidenceStorageCases, BuyerDiscoveryCases, BuyerStorageCases, OriginalSupportCases, EffectiveHandoffCases, EffectiveStateCases, RenewalRpcCases, RenewalChoiceCases, PersonalRenewalCases, RenewalAuthorityLockCases, RetainedScanJourneyCases, RetainedRefreshCases, DownstreamEffectiveCases, ExecutionEffectiveCases, DeadlineEffectiveCases, ReviewDependencyCases, ReviewLineageHeadCases, ReviewRenewalStorageCases, DispositionTransitionChoiceCases, DispositionTransitionCases, DispositionTransitionStorageCases, DispositionCandidateCases, DispositionReviewCases, DispositionPolicyCases, DispositionSourceCases, DispositionStorageCases, DispositionPlanCases, TitleCandidateCases, TitleReviewCases, TitleSourceCases, TitleStorageCases, TitleDocumentCases, TitleChoiceCases, TitleTransitionCases, ExecutionDeadlineCases, DeadlineChoiceCases, DeadlineStateCases, DeadlineReviewCases, DeadlineStorageCases, ExecutedChoiceCases, ExecutedTransitionCases, ExecutionChoiceCases, ExecutionStateCases, ExecutionReviewCases, ExecutionStorageCases, PendingDocumentCases, TransitionChoiceCases, ContractTransitionCases, SignatureCandidateCases, SignatureReviewCases, ContractReferenceDiscoveryCases, ContractSourceReviewCases, ContractDocumentLinkCases, ContractTermsCases, ContractReviewCandidateCases, ContractReviewCases, ContractScanStateCases, ContractObservationCases, ContractDiscoveryCases, ContractStorageCases, ContractUploadAdmissionCases, ContractDocumentCases, FullCatalogContractTests):
    supports_title_choice = True
    supports_disposition_handoff = True
    supports_disposition_choice = True

    def setUp(self):
        super().setUp()
        self.prepare_document_fixture()
        if self._testMethodName.startswith(('test_contract_observation_', 'test_contract_scan_state_', 'test_contract_review_', 'test_terms_', 'test_contract_link_', 'test_source_review_', 'test_reference_discovery_', 'test_signature_')):
            self.prepare_observation_fixture()
        if self._testMethodName.startswith(('test_contract_review_', 'test_terms_', 'test_contract_link_', 'test_source_review_', 'test_reference_discovery_', 'test_signature_')):
            self.prepare_review_fixture()
        if self._testMethodName.startswith(('test_signature_execution_write_', 'test_signature_execution_state_', 'test_signature_execution_choice_', 'test_signature_executed_transition_', 'test_signature_executed_choice_')):
            self.terms=self.execution_prepared_terms
        if self._testMethodName.startswith(('test_signature_deadline_write_','test_signature_deadline_state_','test_signature_deadline_choice_')):
            self.terms=self.deadline_prepared_terms
        if self._testMethodName.startswith(('test_signature_execution_deadline_', 'test_signature_title_transition_', 'test_signature_title_choice_', 'test_signature_title_document_', 'test_signature_title_storage_', 'test_signature_title_sources_', 'test_signature_title_write_', 'test_signature_title_candidate_', 'test_signature_disposition_plan_', 'test_signature_disposition_storage_', 'test_signature_disposition_sources_', 'test_signature_disposition_policy_', 'test_signature_disposition_write_', 'test_signature_disposition_candidate_', 'test_signature_disposition_transition_storage_', 'test_signature_disposition_transition_', 'test_signature_disposition_handoff_choice_', 'test_signature_review_renewal_', 'test_signature_review_lineage_', 'test_signature_review_dependencies_', 'test_signature_deadline_effective_', 'test_signature_execution_effective_', 'test_signature_downstream_effective_', 'test_signature_retained_refresh_', 'test_signature_retained_scan_journey_', 'test_signature_renewal_locks_', 'test_signature_personal_renewal_', 'test_signature_renewal_choice_', 'test_signature_renewal_rpc_', 'test_signature_effective_state_', 'test_signature_effective_handoff_', 'test_signature_original_support_')):
            self.terms=self.binding_prepared_terms
            self.deadline_proposal=self.binding_deadline_proposal
        if self._testMethodName=='test_signature_execution_effective_suspended_workspace_instant':
            self.terms=self.execution_prepared_terms
        if self._testMethodName.startswith('test_signature_'):
            self.prepare_signature()


def run_workflow_probes(db):
    # Include every application journey declared by WorkflowTests, not inherited
    # focused schema-mutation tests from WorkspaceTests.
    names = sorted(name for name, method in WorkflowTests.__dict__.items()
                   if name.startswith('test_') and callable(method))
    contract_names = sorted(name for name in ContractDraftCases.__dict__ if name.startswith('test_contract_draft_'))
    document_names = sorted(name for name in ContractDocumentCases.__dict__ if name.startswith('test_contract_document_'))
    document_names += sorted(name for name in ContractUploadAdmissionCases.__dict__ if name.startswith('test_contract_upload_'))
    document_names += sorted(name for name in ContractStorageCases.__dict__ if name.startswith('test_contract_storage_'))
    document_names += sorted(name for name in ContractDiscoveryCases.__dict__ if name.startswith('test_contract_discovery_'))
    document_names += sorted(name for name in ContractObservationCases.__dict__ if name.startswith('test_contract_observation_'))
    document_names += sorted(name for name in ContractScanStateCases.__dict__ if name.startswith('test_contract_scan_state_'))
    document_names += sorted(name for name in ContractReviewCases.__dict__ if name.startswith('test_contract_review_'))
    document_names += sorted(name for name in ContractReviewCandidateCases.__dict__ if name.startswith('test_contract_review_candidate_'))
    document_names += sorted(name for name in ContractTermsCases.__dict__ if name.startswith('test_terms_'))
    document_names += sorted(name for name in ContractDocumentLinkCases.__dict__ if name.startswith('test_contract_link_'))
    document_names += sorted(name for name in ContractSourceReviewCases.__dict__ if name.startswith('test_source_review_'))
    document_names += sorted(name for name in ContractReferenceDiscoveryCases.__dict__ if name.startswith('test_reference_discovery_'))
    document_names += sorted(name for name in SignatureReviewCases.__dict__ if name.startswith('test_signature_'))
    document_names += sorted(name for name in SignatureCandidateCases.__dict__ if name.startswith('test_signature_candidate_'))
    document_names += sorted(name for name in ContractTransitionCases.__dict__ if name.startswith('test_signature_transition_'))
    document_names += sorted(name for name in TransitionChoiceCases.__dict__ if name.startswith('test_signature_transition_choice_'))
    document_names += sorted(name for name in PendingDocumentCases.__dict__ if name.startswith('test_signature_pending_document_'))
    document_names += sorted(name for name in ExecutionStorageCases.__dict__ if name.startswith('test_signature_execution_storage_'))
    document_names += sorted(name for name in ExecutionReviewCases.__dict__ if name.startswith('test_signature_execution_write_'))
    document_names += sorted(name for name in ExecutionStateCases.__dict__ if name.startswith('test_signature_execution_state_'))
    document_names += sorted(name for name in ExecutionChoiceCases.__dict__ if name.startswith('test_signature_execution_choice_'))
    document_names += sorted(name for name in ExecutedTransitionCases.__dict__ if name.startswith('test_signature_executed_transition_'))
    document_names += sorted(name for name in ExecutedChoiceCases.__dict__ if name.startswith('test_signature_executed_choice_'))
    document_names += sorted(name for name in DeadlineStorageCases.__dict__ if name.startswith('test_signature_deadline_storage_'))
    document_names += sorted(name for name in DeadlineReviewCases.__dict__ if name.startswith('test_signature_deadline_write_'))
    document_names += sorted(name for name in DeadlineStateCases.__dict__ if name.startswith('test_signature_deadline_state_'))
    document_names += sorted(name for name in DeadlineChoiceCases.__dict__ if name.startswith('test_signature_deadline_choice_'))
    document_names += sorted(name for name in TitleDocumentCases.__dict__ if name.startswith('test_signature_title_document_'))
    document_names += sorted(name for name in TitleStorageCases.__dict__ if name.startswith('test_signature_title_storage_'))
    document_names += sorted(name for name in TitleSourceCases.__dict__ if name.startswith('test_signature_title_sources_'))
    document_names += sorted(name for name in TitleReviewCases.__dict__ if name.startswith('test_signature_title_write_'))
    document_names += sorted(name for name in TitleCandidateCases.__dict__ if name.startswith('test_signature_title_candidate_'))
    document_names += sorted(name for name in DispositionPlanCases.__dict__ if name.startswith('test_signature_disposition_plan_'))
    document_names += sorted(name for name in DispositionStorageCases.__dict__ if name.startswith('test_signature_disposition_storage_'))
    document_names += sorted(name for name in DispositionSourceCases.__dict__ if name.startswith('test_signature_disposition_sources_'))
    document_names += sorted(name for name in DispositionPolicyCases.__dict__ if name.startswith('test_signature_disposition_policy_'))
    document_names += sorted(name for name in DispositionReviewCases.__dict__ if name.startswith('test_signature_disposition_write_'))
    document_names += sorted(name for name in DispositionCandidateCases.__dict__ if name.startswith('test_signature_disposition_candidate_'))
    document_names += sorted(name for name in DispositionTransitionStorageCases.__dict__ if name.startswith('test_signature_disposition_transition_storage_'))
    document_names += sorted(name for name in DispositionTransitionCases.__dict__ if name.startswith('test_signature_disposition_transition_'))
    document_names += sorted(name for name in RetainedScanJourneyCases.__dict__ if name.startswith('test_signature_retained_scan_journey_'))
    document_names += ['test_acquisition_buyer_storage_boundaries', 'test_acquisition_buyer_profile_and_discovery', 'test_acquisition_buyer_evidence_storage']
    document_names += sorted(name for name in OriginalSupportCases.__dict__ if name.startswith('test_signature_original_support_'))
    document_names += sorted(name for name in EffectiveStateCases.__dict__ if name.startswith('test_signature_effective_state_'))
    document_names += sorted(name for name in EffectiveHandoffCases.__dict__ if name.startswith('test_signature_effective_handoff_'))
    document_names += sorted(name for name in RenewalRpcCases.__dict__ if name.startswith('test_signature_renewal_rpc_'))
    document_names += sorted(name for name in RenewalChoiceCases.__dict__ if name.startswith('test_signature_renewal_choice_'))
    document_names += sorted(name for name in PersonalRenewalCases.__dict__ if name.startswith('test_signature_personal_renewal_'))
    document_names += sorted(name for name in RenewalAuthorityLockCases.__dict__ if name.startswith('test_signature_renewal_locks_'))
    document_names += sorted(name for name in RetainedRefreshCases.__dict__ if name.startswith('test_signature_retained_refresh_'))
    document_names += sorted(name for name in DownstreamEffectiveCases.__dict__ if name.startswith('test_signature_downstream_effective_'))
    document_names += sorted(name for name in ExecutionEffectiveCases.__dict__ if name.startswith('test_signature_execution_effective_'))
    document_names += sorted(name for name in DeadlineEffectiveCases.__dict__ if name.startswith('test_signature_deadline_effective_'))
    document_names += sorted(name for name in ReviewDependencyCases.__dict__ if name.startswith('test_signature_review_dependencies_'))
    document_names += sorted(name for name in ReviewLineageHeadCases.__dict__ if name.startswith('test_signature_review_lineage_'))
    document_names += sorted(name for name in ReviewRenewalStorageCases.__dict__ if name.startswith('test_signature_review_renewal_'))
    document_names += sorted(name for name in DispositionTransitionChoiceCases.__dict__ if name.startswith('test_signature_disposition_handoff_choice_'))
    document_names += sorted(name for name in TitleChoiceCases.__dict__ if name.startswith('test_signature_title_choice_'))
    document_names += sorted(name for name in TitleTransitionCases.__dict__ if name.startswith('test_signature_title_transition_'))
    document_names += sorted(name for name in ExecutionDeadlineCases.__dict__ if name.startswith('test_signature_execution_deadline_'))
    names += contract_names + document_names
    if not names:
        raise RuntimeError('No application journeys discovered')
    from rehearse_acquisition_upgrade import fingerprints, CATALOG
    expected_history=fingerprints(db,CATALOG['tables'])
    socket=db.connection.get_dsn_parameters()['host']
    # The source must have no sessions while PostgreSQL copies it as a template.
    db.connection.close()
    control=psycopg2.connect(host=socket,dbname='postgres',user='test_admin',connect_timeout=5)
    control.autocommit=True
    passed=[]
    try:
        for index,name in enumerate(names):
            database='acquisition_workflow_'+str(index)
            with control.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {} TEMPLATE acquisition_upgrade').format(sql.Identifier(database)))
            try:
                print(json.dumps({'running_full_catalog_workflow':name}),flush=True)
                test=(FullCatalogDocumentTests if name in document_names else FullCatalogContractTests if name in contract_names else FullCatalogWorkflowTests)(name)
                test.socket=socket
                test.database_name=database
                test.env={'PATH':'/usr/bin:/bin','HOME':socket,'TMPDIR':socket,'LANG':'C','PGCONNECT_TIMEOUT':'5'}
                result=unittest.TestResult()
                test.run(result)
                if not result.wasSuccessful():
                    raise AssertionError('\n'.join(detail for _,detail in result.failures+result.errors))
                from rehearse_acquisition_baseline import DisposableDatabase
                clone=object.__new__(DisposableDatabase)
                clone.connection=psycopg2.connect(host=socket,dbname=database,user='test_admin',connect_timeout=5)
                clone.connection.autocommit=True
                try:
                    after=fingerprints(clone,CATALOG['tables'])
                    changed=[table for table,rows in expected_history.items() if table not in ('\"public\".\"tasks\"','\"public\".\"app_notifications\"') and rows-after[table]]
                    for table,raw in test.fixture_aggregate_rows.items():
                        current=clone.query('SELECT to_jsonb(t) AS row FROM public.'+table+' t')
                        current_rows=[r['row'] for r in current]
                        if any(row not in current_rows for row in json.loads(raw)):
                            changed.append(table)
                    if changed:
                        raise AssertionError(name+': historical records changed: '+', '.join(changed))
                finally:
                    clone.connection.close()
                passed.append(name)
            finally:
                with control.cursor() as cursor:
                    cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
    finally:
        control.close()
        db.connection=psycopg2.connect(host=socket,dbname='acquisition_upgrade',user='test_admin',connect_timeout=5)
        db.connection.autocommit=True
    return {'full_catalog_application_workflows':'passed','tests':passed,
            'database_copies_removed':True,'provider_and_postgrest_simulated':True}
