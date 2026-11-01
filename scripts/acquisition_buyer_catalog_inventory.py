"""Read buyer catalog from a separate disposable full-baseline + candidate database.

No database URL or production access is accepted. This inventories structure, not
migration-role acceptance, which remains the full populated rehearsal's job.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'pipeline/integration'))
from rehearse_acquisition_baseline import DisposableDatabase, EVIDENCE, PG, restore, verify
from acquisition_storage_fixture import install_storage_fixture

TABLES = ('buyers', 'buyer_preferences', 'buyer_transactions', 'buyer_import_log',
          'deal_matches', 'buyer_outreach_log', 'deals', 'tasks')


def inspect(db):
    queries = {
        'columns': "SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(%s) ORDER BY table_name,ordinal_position",
        'constraints': "SELECT c.relname,co.conname,co.contype,pg_get_constraintdef(co.oid) definition FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY 1,2",
        'indexes': "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=ANY(%s) ORDER BY 1,2",
        'policies': "SELECT * FROM pg_policies WHERE schemaname='public' AND tablename=ANY(%s) ORDER BY tablename,policyname",
        'grants': "SELECT table_name,grantee,privilege_type FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name=ANY(%s) ORDER BY 1,2,3",
        'triggers': "SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname='public' AND c.relname=ANY(%s) ORDER BY 1,2",
        'row_security': "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY 1",
        'incoming_foreign_keys': "SELECT n.nspname,c.relname,co.conname,pg_get_constraintdef(co.oid) definition FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_class target ON target.oid=co.confrelid JOIN pg_namespace tn ON tn.oid=target.relnamespace WHERE co.contype='f' AND tn.nspname='public' AND target.relname=ANY(%s) ORDER BY 1,2,3",
    }
    result = {key: db.query(query, [list(TABLES)]) for key, query in queries.items()}
    result['buyer_referencing_functions'] = db.query("SELECT n.nspname,p.proname,p.oid::regprocedure::text signature,pg_get_functiondef(p.oid) definition,pg_get_userbyid(p.proowner) owner,p.prosecdef security_definer,p.proacl::text acl,p.proconfig settings FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.prokind='f' AND n.nspname IN ('public','private') AND p.prosrc ILIKE '%buyer%' ORDER BY 1,2,3")
    result['buyer_referencing_views'] = db.query("SELECT v.schemaname,v.viewname,v.definition,pg_get_userbyid(c.relowner) owner,c.reloptions options,c.relacl::text acl FROM pg_views v JOIN pg_namespace n ON n.nspname=v.schemaname JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=v.viewname WHERE v.schemaname IN ('public','private') AND v.definition ILIKE '%buyer%' ORDER BY 1,2")
    present = {row['relname'] for row in result['row_security']}
    if present != set(TABLES):
        raise RuntimeError('Buyer inventory missing tables: '+str(set(TABLES)-present))
    return result


def main():
    manifest_path = EVIDENCE/'acquisition-upgrade-manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest['production_apply_approved'] is not False:
        raise RuntimeError('Offline candidate manifest required')
    migrations = []
    for row in manifest['migrations']:
        source = (ROOT/'frontend/supabase/migrations'/row['file']).read_bytes()
        if hashlib.sha256(source).hexdigest() != row['sha256']:
            raise RuntimeError('Candidate hash mismatch: '+row['file'])
        migrations.append(source.decode())
    with tempfile.TemporaryDirectory(prefix='acq-buyer-inventory-',dir='/tmp') as folder:
        path = Path(folder)
        data = path/'data'
        def run(args):
            subprocess.run([str(x) for x in args], check=True, stdout=subprocess.DEVNULL,
                           timeout=60, env={'PATH':'/usr/bin:/bin','LANG':'C','PGCONNECT_TIMEOUT':'5'})
        run([PG/'initdb','-D',data,'-U','test_admin','--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'])
        with (data/'postgresql.conf').open('a') as config:
            config.write("\nlisten_addresses=''\nunix_socket_directories='"+folder+"'\n")
        started = False
        db = None
        try:
            run([PG/'pg_ctl','-D',data,'-l',path/'server.log','-w','start'])
            started = True
            run([PG/'createdb','-h',folder,'-U','test_admin','acquisition_upgrade'])
            db = DisposableDatabase(path)
            restore(db)
            verify(db)
            db.query('RESET ROLE; SET check_function_bodies=true; SET search_path=public,extensions')
            install_storage_fixture(db.query)
            for migration in migrations:
                db.query(migration)
            result = inspect(db)
            result.update(scope='Separate disposable full catalog plus candidate migrations; no hosted query, no migration-role or runtime acceptance claim',
                          manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                          migrations=manifest['migrations'], production_changed=False)
            output = EVIDENCE/'2026-11-01-buyer-local-catalog.json'
            output.write_text(json.dumps(result,indent=2,default=str)+'\n')
            print(json.dumps({'evidence':str(output),'counts':{key:len(value) for key,value in result.items() if isinstance(value,list)}}))
        finally:
            if db:
                db.connection.close()
            if started:
                run([PG/'pg_ctl','-D',data,'-m','immediate','-w','stop'])


if __name__ == '__main__':
    main()
