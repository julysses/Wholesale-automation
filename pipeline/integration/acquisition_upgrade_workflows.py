"""Existing application journeys on per-test copies of the full upgraded catalog."""
import json
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

        # Existing county triggers update the daily aggregate during property seeding.
        # Snapshot those two tables after fixture setup, before application requests.
        self.fixture_aggregate_rows={table:self.sql("SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]'::jsonb)::text FROM public."+table+' t') for table in ('tasks','app_notifications')}


def run_workflow_probes(db):
    # Include every application journey declared by WorkflowTests, not inherited
    # focused schema-mutation tests from WorkspaceTests.
    names = sorted(name for name, method in WorkflowTests.__dict__.items()
                   if name.startswith('test_') and callable(method))
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
                test=FullCatalogWorkflowTests(name)
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
