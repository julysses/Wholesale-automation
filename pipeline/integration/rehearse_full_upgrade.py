"""Rehearse only the reviewed eleven-file proposal on a disposable local database.

Restore the saved catalog and rehearse the released Facebook migration first via
run_production_upgrade.py. No production DSN or provider access is accepted.
"""
import hashlib
import json
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


def rehearse(db):
    names = json.loads((ROOT/'docs/integration/forward-migration-order.json').read_text())
    assert len(names) == len(set(names)) == 11
    paths = [ROOT/'frontend/supabase/migrations'/name for name in names]
    assert all(p.name.startswith('20261020') and '_integration_' in p.name and p.parent == paths[0].parent for p in paths)
    tables = {}
    for row in db.query("SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE table_schema IN ('public','private','wholesale_ingest') AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname IN ('public','private','wholesale_ingest')) ORDER BY ordinal_position"):
        key = ident(row['table_schema'])+'.'+ident(row['table_name'])
        tables.setdefault(key, []).append(row['column_name'])
    before = retained_rows(db, tables)
    before_functions = functions(db)
    history = db.query('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version')

    # Full-sequence rollback is checked before committing anything in this local DB.
    for rollback in [True, False]:
        db.query("BEGIN; SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='30s'")
        try:
            for path in paths:
                print(json.dumps({'phase': 'rollback' if rollback else 'apply', 'migration': path.name}), flush=True)
                db.query(path.read_text())
            assert retained_rows(db, tables) == before, 'Existing evidence rows changed'
            db.query('ROLLBACK' if rollback else 'COMMIT')
        except Exception:
            db.query('ROLLBACK')
            raise
        if rollback:
            assert retained_rows(db, tables) == before
            assert functions(db) == before_functions
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
            assert not (access['executable'] and access['schema_access'] and not access['is_trigger']), (role, signature, access)
    assert db.query('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version') == history
    assert not db.query('SELECT * FROM cron.job WHERE active')
    assert not db.query('SELECT * FROM private.retell_sms_scheduler WHERE enabled')
    assert not db.query('SELECT * FROM private.retell_app_scheduler WHERE enabled')
    assert not db.query('SELECT * FROM net.test_requests')
    assert db.query("SELECT to_regprocedure('private.reconcile_empty_retell_session(uuid)') value")[0]['value'] is None
    print(json.dumps({'integration_upgrade':'passed','rollback':'passed','migrations':[
        {'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
        'retained_tables':len(tables),'retained_rows_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        'changed_existing_functions':changed,'new_functions':len(new_functions),'browser_permission_checks':permission_checks,'provider_calls':0}), flush=True)


if __name__ == '__main__':
    db = Database()
    try:
        rehearse(db)
    finally:
        db.connection.close()
