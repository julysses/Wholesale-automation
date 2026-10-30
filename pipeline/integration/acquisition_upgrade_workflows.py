"""Existing application journeys on per-test copies of the full upgraded catalog."""
import unittest

import psycopg2
from psycopg2 import sql

from test_acquisition_workflow import WorkflowTests
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


def run_workflow_probes(db):
    names = [
        'test_qualified_facebook_intake_handoff_calculates_canonical_property_and_goes_stale',
        'test_real_calculation_persists_then_enters_offer_review',
        'test_rental_persisted_cashflow_enters_amount_review',
        'test_development_persisted_costs_enter_amount_review',
        'test_assignment_persisted_buyer_economics_enter_amount_review',
        'test_assignment_unsupported_buyer_price_cannot_enter_offer_queue',
        'test_missing_market_value_is_persisted_as_incomplete_and_cannot_propose',
        'test_lost_completion_response_retry_reconciles_existing_revision',
    ]
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
                test=FullCatalogWorkflowTests(name)
                test.socket=socket
                test.database_name=database
                test.env={'PATH':'/usr/bin:/bin','HOME':socket,'TMPDIR':socket,'LANG':'C','PGCONNECT_TIMEOUT':'5'}
                result=unittest.TestResult()
                test.run(result)
                if not result.wasSuccessful():
                    raise AssertionError('\n'.join(detail for _,detail in result.failures+result.errors))
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
