"""Rehearse only the reviewed migration allowlist on a disposable local database.

Restore the saved catalog and rehearse the released Facebook migration first via
run_production_upgrade.py. No production DSN or provider access is accepted.
"""
import hashlib
import json
from uuid import uuid4
from psycopg2.errors import DivisionByZero
from production_schema import ROOT, ident
from tests.local_journey_db import Database


def functions(db):
    return {r['signature']:r for r in db.query("SELECT p.oid::regprocedure::text signature,pg_get_functiondef(p.oid) definition,p.proacl::text acl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','private','wholesale_ingest','offer_review') AND p.prokind='f'")}


def retained_rows(db, tables):
    result = {}
    for table, columns in tables.items():
        selection = ','.join(ident(c) for c in columns)
        result[table] = db.query(f'SELECT to_jsonb(t) row FROM (SELECT {selection} FROM {table}) t ORDER BY to_jsonb(t)::text')
    return result


def structure(db):
    return db.query("SELECT table_schema,table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema IN ('public','private','wholesale_ingest','offer_review') ORDER BY table_schema,table_name,ordinal_position")


def seed_legacy_features(db):
    owner = '00000000-0000-4000-8000-000000000777'
    lead, land, comp = [str(uuid4()) for _ in range(3)]
    db.query("INSERT INTO leads(id,property_address,city,dnc,status) VALUES(%s,'Synthetic retained land','Dallas',true,'dnc')", [lead])
    db.query("INSERT INTO land_leads(id,lead_id,owner_name,property_address,city,dnc,assigned_to) VALUES(%s,%s,'Synthetic owner','Synthetic retained land','Dallas',true,%s)", [land, lead, owner])
    db.query("INSERT INTO land_comps(id,land_lead_id,comped_by,house_comp_radius_mi,direct_comp_avg,tav,comp_notes) VALUES(%s,%s,%s,1.25,123456,98765,'Synthetic historical valuation; retain exactly')", [comp, land, owner])
    for index, status in enumerate(['submitting','accepted','unknown','completed']):
        call_lead = str(uuid4())
        db.query("INSERT INTO leads(id,property_address,city,dnc,status) VALUES(%s,'Synthetic retained call','Dallas',true,'dnc')", [call_lead])
        db.query("INSERT INTO retell_call_requests(id,lead_id,requested_by,phone_number,status,provider_call_id) VALUES(%s,%s,%s,%s,%s,%s)", [str(uuid4()), call_lead, owner, f'+1214555060{index}', status, 'synthetic_'+status if status in ['accepted','completed'] else None])
    retained_buyer,retained_history=str(uuid4()),str(uuid4())
    db.query("INSERT INTO buyers(id,first_name,last_name,active,email_opt_in,sms_opt_in) VALUES(%s,'Synthetic retained','Buyer',false,false,false)",[retained_buyer])
    db.query("INSERT INTO buyer_outreach_log(id,buyer_id,channel,status,body,to_address,provider_msg_id) VALUES(%s,%s,'email','sent','Synthetic historical outreach; retain exactly','retained-history@example.test','synthetic-historical-reference')",[retained_history,retained_buyer])
    return {'buyer_outreach_history':1,'land_leads':1,'land_comps':1,'call_requests':4,'valuation_radius_mi':1.25}


def rehearse(db):
    names = json.loads((ROOT/'docs/integration/forward-migration-order.json').read_text())
    assert len(names) == len(set(names)) == 18
    paths = [ROOT/'frontend/supabase/migrations'/name for name in names]
    assert all((p.name.startswith('20261020') or p.name in {'20261022160020_integration_manual_land_import.sql','20261022170346_integration_csv_lead_intake.sql','20261022190018_integration_buyer_csv_transaction.sql','20261022194256_integration_buyer_outreach_claims.sql','20261022201934_integration_buyer_sms_consent.sql','20261022203734_integration_buyer_sms_transport.sql','20261022210254_integration_buyer_enrollment.sql'}) and '_integration_' in p.name and p.parent == paths[0].parent for p in paths)
    legacy_features = seed_legacy_features(db)
    tables = {}
    for row in db.query("SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE table_schema IN ('public','private','wholesale_ingest') AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname IN ('public','private','wholesale_ingest')) ORDER BY ordinal_position"):
        key = ident(row['table_schema'])+'.'+ident(row['table_name'])
        tables.setdefault(key, []).append(row['column_name'])
    before = retained_rows(db, tables)
    before_functions = functions(db)
    before_structure = structure(db)
    history = db.query('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version')

    # Prove actual SQL failure rolls back partial DDL and preserves old callers,
    # then check a successful full rollback before the final local apply.
    for phase in ['injected_failure','rollback','apply']:
        db.query("BEGIN; SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='30s'")
        injection_reached = False
        try:
            for index, path in enumerate(paths):
                print(json.dumps({'phase': phase, 'migration': path.name}), flush=True)
                db.query(path.read_text())
                if phase == 'injected_failure' and index == 5:
                    injection_reached = True
                    db.query('SELECT 1/0')
            assert phase != 'injected_failure', 'Failure injection did not run'
            assert retained_rows(db, tables) == before, 'Existing evidence rows changed'
            db.query('ROLLBACK' if phase == 'rollback' else 'COMMIT')
        except DivisionByZero:
            db.query('ROLLBACK')
            assert phase == 'injected_failure' and injection_reached and index == 5
        except Exception:
            db.query('ROLLBACK')
            raise
        if phase != 'apply':
            assert retained_rows(db, tables) == before
            assert functions(db) == before_functions
            assert structure(db) == before_structure
            assert db.query("SELECT to_regclass('offer_review.events') value")[0]['value'] is None

    after_functions = functions(db)
    changed = [key for key, value in before_functions.items() if after_functions.get(key) != value]
    assert set(changed) == {'scan_list_pipeline()', 'claim_retell_call(uuid,uuid,text,uuid)'}, changed
    old_claim = 'claim_retell_call(uuid,uuid,text,uuid)'
    assert before_functions[old_claim]['definition'] == after_functions[old_claim]['definition']
    assert not db.query("SELECT has_function_privilege('service_role','public.claim_retell_call(uuid,uuid,text,uuid)','EXECUTE') allowed")[0]['allowed']
    assert db.query("SELECT has_function_privilege('service_role','public.claim_retell_call_versioned(uuid,uuid,text,uuid,text,integer,text)','EXECUTE') allowed")[0]['allowed']
    new_functions = set(after_functions)-set(before_functions)
    permission_checks = []
    for signature in new_functions:
        for role in ['anon','authenticated']:
            access = db.query("SELECT has_function_privilege(%s,p.oid,'EXECUTE') executable,has_schema_privilege(%s,n.oid,'USAGE') schema_access,p.prorettype='trigger'::regtype is_trigger FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.oid=%s::regprocedure", [role, role, signature])[0]
            permission_checks.append({'role':role,'function':signature,**access})
            # Trigger functions cannot be called as ordinary RPCs; private-schema
            # EXECUTE alone is also insufficient without schema USAGE.
            if role == 'authenticated' and signature == 'private.csv_lead_key(text,text,text)':
                # Reviewed pure index expression, never a business-data endpoint.
                helper = db.query("SELECT provolatile,prosecdef FROM pg_proc WHERE oid=%s::regprocedure",[signature])[0]
                assert helper == {'provolatile':'i','prosecdef':False},helper
                assert access['executable'] and access['schema_access']
                continue
            assert not (access['executable'] and access['schema_access'] and not access['is_trigger']), (role, signature, access)
    assert db.query('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version') == history
    assert not db.query('SELECT * FROM cron.job WHERE active')
    assert not db.query('SELECT * FROM private.retell_sms_scheduler WHERE enabled')
    assert not db.query('SELECT * FROM private.retell_app_scheduler WHERE enabled')
    assert not db.query('SELECT * FROM net.test_requests')
    assert db.query("SELECT to_regprocedure('private.reconcile_empty_retell_session(uuid)') value")[0]['value'] is None
    print(json.dumps({'integration_upgrade':'passed','rollback':'passed','injected_failure_after_migration':6,'injected_failure_rollback':'passed','legacy_feature_fixtures':legacy_features,'migrations':[
        {'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
        'retained_tables':len(tables),'retained_rows_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        'changed_existing_functions':changed,'new_functions':len(new_functions),'browser_permission_checks':permission_checks,'provider_calls':0}), flush=True)


if __name__ == '__main__':
    db = Database()
    try:
        rehearse(db)
    finally:
        db.connection.close()
