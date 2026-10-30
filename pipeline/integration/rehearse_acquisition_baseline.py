"""Restore and compare the current application catalog in a private disposable cluster.

No customer rows, auth sessions, vault secrets or working network/cron extensions.
Application functions, constraints, policies and triggers come from the snapshot.
"""
import json
from pathlib import Path
import hashlib
import os
import re
import subprocess
import tempfile

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT/'docs/acquisition-automation/evidence'
CATALOG = json.loads((EVIDENCE/'2026-10-30-upgrade-catalog.json').read_text())
OWNERS = json.loads((EVIDENCE/'2026-10-30-upgrade-ownership.json').read_text())
META = CATALOG
PG = Path(os.environ.get('PG_BIN','/opt/homebrew/opt/postgresql@17/bin'))
def ident(s): return '"'+s.replace('"','""')+'"'
def qualified(t): return ident(t['schema'])+'.'+ident(t['name'])
def literal(s): return "'"+s.replace("'","''")+"'"

def grants(db, acl, obj, kind):
    if acl is None: return
    db.query(f'REVOKE ALL ON {kind} {obj} FROM PUBLIC')
    mapping={'r':'SELECT','a':'INSERT','w':'UPDATE','d':'DELETE','D':'TRUNCATE','x':'REFERENCES','t':'TRIGGER','X':'EXECUTE','U':'USAGE','C':'CREATE','m':'MAINTAIN'}
    for entry in acl.strip('{}').split(','):
        role, value = entry.split('=',1)
        role=ident(role.strip('"')) if role else 'PUBLIC'
        rights=value.split('/')[0]
        for right in rights.replace('*',''):
            db.query(f'GRANT {mapping[right]} ON {kind} {obj} TO {role}'+(' WITH GRANT OPTION' if right+'*' in rights else ''))

def restore(db):
    expected_hash=json.loads((EVIDENCE/'2026-10-30-upgrade-baseline-report.json').read_text())['catalog_sha256']
    if hashlib.sha256((EVIDENCE/'2026-10-30-upgrade-catalog.json').read_bytes()).hexdigest()!=expected_hash:
        raise RuntimeError('Catalog hash differs from reviewed baseline report')
    if CATALOG['enums'] or CATALOG['sequences'] or any(c['identity'] for t in CATALOG['tables'] for c in t['columns']):
        raise RuntimeError('Extend explicit restore support for captured types/sequences/identity')
    relations={(r['schema'],r['name']) for r in CATALOG['tables']+CATALOG['views']}
    if relations!={(r['schema'],r['name']) for r in OWNERS['relations']} or {f['signature'] for f in CATALOG['functions']}!={f['signature'] for f in OWNERS['functions']}:
        raise RuntimeError('Ownership capture does not match catalog identities')
    if any(x['owner']!='postgres' for k in ('relations','functions','schemas') for x in OWNERS[k]):
        raise RuntimeError('Extend explicit ownership restoration')
    db.query('SET check_function_bodies=false; SET search_path=public,extensions,wholesale_ingest')
    for role in ['anon','authenticated','service_role','postgres','wholesale_ingestor','wholesale_worker','supabase_admin']:
        db.query(f'CREATE ROLE {ident(role)} NOLOGIN'+(' BYPASSRLS' if role in ['service_role','postgres','supabase_admin'] else ''))
    db.query('ALTER DATABASE acquisition_upgrade OWNER TO postgres')
    db.query('CREATE SCHEMA extensions; CREATE EXTENSION "uuid-ossp" WITH SCHEMA extensions; CREATE EXTENSION pgcrypto WITH SCHEMA extensions')
    db.query('GRANT USAGE ON SCHEMA extensions TO PUBLIC')
    for name in ['private','wholesale_ingest','auth','net','vault','cron','supabase_migrations']:
        db.query('CREATE SCHEMA '+ident(name))
    db.query('''CREATE TABLE auth.users(id uuid PRIMARY KEY);
    CREATE TABLE auth.sessions(id uuid PRIMARY KEY,user_id uuid REFERENCES auth.users(id),not_after timestamptz);
    CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$;
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT (auth.jwt()->>'sub')::uuid $$;
    CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT auth.jwt()->>'role' $$;
    CREATE TABLE net.test_requests(id bigserial PRIMARY KEY,url text);
    CREATE TABLE net._http_response(id bigint,status_code integer,timed_out boolean,content text);
    CREATE TABLE vault.decrypted_secrets(name text,decrypted_secret text);
    CREATE FUNCTION net.http_post(url text,body jsonb DEFAULT '{}',params jsonb DEFAULT '{}',headers jsonb DEFAULT '{}',timeout_milliseconds integer DEFAULT 1000)
    RETURNS bigint LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'External HTTP prohibited in rehearsal'; END $$;
    CREATE FUNCTION net.http_get(url text,params jsonb DEFAULT '{}',headers jsonb DEFAULT '{}',timeout_milliseconds integer DEFAULT 1000)
    RETURNS bigint LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'External HTTP prohibited in rehearsal'; END $$;
    CREATE TABLE cron.job(jobname text,active boolean);
    CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text);''')
    for name in ('public','private','wholesale_ingest'):
        db.query('ALTER SCHEMA '+ident(name)+' OWNER TO postgres')
    db.query('GRANT USAGE ON SCHEMA auth,net,vault,cron,supabase_migrations TO postgres; '
             'GRANT ALL ON ALL TABLES IN SCHEMA auth,net,vault,cron,supabase_migrations TO postgres; SET ROLE postgres')
    for t in CATALOG['tables']:
        columns=[]
        for c in t['columns']:
            assert not c['identity'], 'Extend restoration for identity columns'
            columns.append(ident(c['name'])+' '+c['type']+(' GENERATED ALWAYS AS ('+c['default']+') STORED' if c['generated'] else (' DEFAULT '+c['default'] if c['default'] else ''))+(' NOT NULL' if c['notnull'] else ''))
        db.query('CREATE TABLE '+qualified(t)+'('+','.join(columns)+')')
    for f in CATALOG['functions']: db.query(f['definition'])
    for kind in [('p','u','x'),('c',),('f',)]:
        for c in CATALOG['constraints']:
            if c['type'] in kind:
                db.query('ALTER TABLE '+ident(c['schema'])+'.'+ident(c['table'])+' ADD CONSTRAINT '+ident(c['name'])+' '+c['definition'])
    for index in CATALOG['indexes']: db.query(index)
    pending=list(CATALOG['views'])
    while pending:
        failed=[]
        for v in pending:
            try:
                options=v.get('options') or []
                if any(option!='security_invoker=true' for option in options):
                    raise RuntimeError('Unsupported captured view option')
                db.query('CREATE VIEW '+qualified(v)+(' WITH (security_invoker=true)' if options else '')+' AS '+v['definition'])
            except Exception as exc: failed.append(v); error=exc
        if len(failed)==len(pending): raise error
        pending=failed
    for trigger in CATALOG['triggers']: db.query(trigger)
    for p in CATALOG['policies']:
        command='CREATE POLICY '+ident(p['policyname'])+' ON '+ident(p['schemaname'])+'.'+ident(p['tablename'])
        command+=' AS '+p['permissive']+' FOR '+p['cmd']+' TO '+','.join('PUBLIC' if r=='public' else ident(r) for r in p['roles'])
        if p['qual']: command+=' USING ('+p['qual']+')'
        if p['with_check']: command+=' WITH CHECK ('+p['with_check']+')'
        db.query(command)
    for t in CATALOG['tables']:
        if t['rls']: db.query('ALTER TABLE '+qualified(t)+' ENABLE ROW LEVEL SECURITY')
        if t['force_rls']: db.query('ALTER TABLE '+qualified(t)+' FORCE ROW LEVEL SECURITY')
        grants(db,t['acl'],qualified(t),'TABLE')
    for v in CATALOG['views']: grants(db,v['acl'],qualified(v),'TABLE')
    for f in CATALOG['functions']: grants(db,f['acl'],f['signature'],'FUNCTION')
    for s in META['schema_acls']: grants(db,s['acl'],ident(s['schema']),'SCHEMA')
    # Preserve defaults applicable to future objects, mapping production owner to local admin.
    kinds={'r':'TABLES','f':'FUNCTIONS','S':'SEQUENCES','T':'TYPES'}
    for a in META['default_acls'] or []:
        if a['owner']!='postgres':raise RuntimeError('Unsupported default ACL owner')
        prefix='ALTER DEFAULT PRIVILEGES IN SCHEMA '+ident(a['schema'])
        db.query(prefix+' REVOKE ALL ON '+kinds[a['type']]+' FROM PUBLIC')
        for entry in a['acl'].strip('{}').split(','):
            role, value=entry.split('=',1); rights=value.split('/')[0]
            mapping={'r':'SELECT','a':'INSERT','w':'UPDATE','d':'DELETE','D':'TRUNCATE','x':'REFERENCES','t':'TRIGGER','X':'EXECUTE','U':'USAGE','m':'MAINTAIN'}
            for right in rights.replace('*',''):
                db.query(prefix+' GRANT '+mapping[right]+' ON '+kinds[a['type']]+' TO '+(ident(role) if role else 'PUBLIC'))
    for m in META['migrations']: db.query('INSERT INTO supabase_migrations.schema_migrations VALUES(%s,%s)',[m['version'],m['name']])
    db.query('RESET ROLE; SET search_path=public,extensions')


def verify(db, *, diagnostics=True):
    # Execute the same read-only catalog query against the restored database.
    actual=db.query((EVIDENCE/'upgrade-catalog-query.sql').read_text())[0]['catalog']
    errors=[]
    for key in ('tables','functions','constraints','indexes','triggers','policies','views','migrations','schema_acls','default_acls','enums','sequences'):
        def ordered(value):
            def normalize(row):
                if isinstance(row,dict):
                    return {k:(sorted(v.strip('{}').split(',')) if k=='acl' and v is not None else normalize(v)) for k,v in row.items()}
                if isinstance(row,list):return [normalize(x) for x in row]
                return row
            return sorted((json.dumps(normalize(x),sort_keys=True) for x in (value or [])))
        if ordered(actual[key])!=ordered(CATALOG[key]):
            errors.append(key)
            if diagnostics and key in ('tables','functions'):
                identity=lambda x:(x.get('schema'),x.get('name'),x.get('signature'))
                expected={identity(x):x for x in CATALOG[key]}
                for row in actual[key]:
                    previous=expected.get(identity(row),{})
                    differences=[field for field in row if row[field]!=previous.get(field)]
                    if differences:
                        print(json.dumps({'restore_difference':identity(row),'fields':differences,
                            'expected_acl':previous.get('acl'),'actual_acl':row.get('acl')}),flush=True)
                        break
    if errors:raise RuntimeError('Restored catalog differs in: '+', '.join(errors))
    owners=db.query("SELECT DISTINCT pg_get_userbyid(c.relowner) AS owner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND c.relkind IN ('r','v')")
    if owners!=[{'owner':'postgres'}]:raise RuntimeError('Restored relation ownership mismatch')
    functions=db.query("SELECT DISTINCT pg_get_userbyid(p.proowner) AS owner FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND p.prokind='f'")
    if functions!=[{'owner':'postgres'}]:raise RuntimeError('Restored function ownership mismatch')
    schemas=db.query("SELECT nspname AS schema,pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname IN ('public','private','wholesale_ingest')")
    if sorted(schemas,key=lambda x:x['schema'])!=sorted(OWNERS['schemas'],key=lambda x:x['schema']):
        raise RuntimeError('Restored schema ownership mismatch')
    for schema,name in [('cron','job'),('net','test_requests'),('vault','decrypted_secrets')]:
        if db.query('SELECT count(*) AS n FROM '+ident(schema)+'.'+ident(name))[0]['n']!=0:
            raise RuntimeError('Inert platform fixture acquired live state')
    return {'baseline_restore':'passed','catalog_sha256':hashlib.sha256((EVIDENCE/'2026-10-30-upgrade-catalog.json').read_bytes()).hexdigest(),
        'tables':len(CATALOG['tables']),'views':len(CATALOG['views']),'functions':len(CATALOG['functions']),
        'migrations':len(CATALOG['migrations']),'production_rows_copied':0,'candidate_migrations_applied':False,
        'platform_fixtures':['auth','net','vault','cron'],'live_platform_acceptance':False}


def verify_rejection_guards(db):
    changes={
        'view_security':'ALTER VIEW public.reportable_leads SET (security_invoker=false)',
        'widened_acl':'GRANT SELECT ON private.retell_app_scheduler TO PUBLIC',
        'function_security':'ALTER FUNCTION private.is_approved_admin() SECURITY INVOKER',
        'relation_owner':'ALTER TABLE private.retell_app_scheduler OWNER TO test_admin',
    }
    foreign_key=next(c for c in CATALOG['constraints'] if c['type']=='f' and c['table']=='leads')
    changes['missing_foreign_key']='ALTER TABLE '+ident(foreign_key['schema'])+'.'+ident(foreign_key['table'])+' DROP CONSTRAINT '+ident(foreign_key['name'])
    for name,sql in changes.items():
        db.query('BEGIN')
        try:
            db.query(sql)
            try:verify(db,diagnostics=False)
            except RuntimeError:pass
            else:raise AssertionError('Catalog verifier accepted '+name)
        finally:db.query('ROLLBACK')
    # Each mutation is rolled back. The unmodified baseline must still pass.
    result=verify(db)
    result['rejected_security_mutations']=list(changes)
    return result


class DisposableDatabase:
    def __init__(self, socket):
        # This path is supplied only by this runner's freshly created TemporaryDirectory.
        self.connection=psycopg2.connect(host=str(socket),dbname='acquisition_upgrade',user='test_admin',connect_timeout=5)
        self.connection.autocommit=True
    def query(self, statement, params=()):
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(statement,params or None)
            return [dict(row) for row in cursor.fetchall()] if cursor.description else []


def main(*, upgrade=False, postgrest=False):
    if not all((PG/name).is_file() for name in ('initdb','pg_ctl','createdb')):
        raise RuntimeError('Local PostgreSQL binaries required')
    library=os.environ.get('ACQUISITION_TEST_SUPAUTILS','')
    if upgrade and (not re.fullmatch(r'/[A-Za-z0-9/._-]+',library) or not Path(library).is_file()):
        raise RuntimeError('Populated upgrade requires an explicitly built local Supautils library')
    with tempfile.TemporaryDirectory(prefix='acq-upgrade-',dir='/tmp') as folder:
        path=Path(folder);data=path/'data'
        env={'PATH':'/usr/bin:/bin','HOME':folder,'TMPDIR':folder,'LANG':'C','PGCONNECT_TIMEOUT':'5'}
        def run(args):subprocess.run([str(x) for x in args],env=env,check=True,stdout=subprocess.DEVNULL,timeout=60)
        run([PG/'initdb','-D',data,'-U','test_admin','--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8'])
        with (data/'postgresql.conf').open('a') as out:
            out.write("\nlisten_addresses=''\nunix_socket_directories='"+folder+"'\n")
            if upgrade:
                out.write("shared_preload_libraries='"+library+"'\n")
                out.write("supautils.policy_grants='"+json.dumps({'postgres':['storage.objects','storage.buckets']})+"'\n")
        started=False;db=None
        try:
            run([PG/'pg_ctl','-D',data,'-l',path/'server.log','-w','start']);started=True
            run([PG/'createdb','-h',folder,'-U','test_admin','acquisition_upgrade'])
            db=DisposableDatabase(path)
            version=int(db.query("SELECT current_setting('server_version_num') AS version")[0]['version'])//10000
            if version!=int(CATALOG['server_version'].split('.')[0]):
                raise RuntimeError('PostgreSQL major version must match the captured baseline')
            restore(db)
            verify(db)
            print(json.dumps(verify_rejection_guards(db),sort_keys=True),flush=True)
            if upgrade:
                from rehearse_acquisition_upgrade import run_upgrade
                print(json.dumps(run_upgrade(db),sort_keys=True),flush=True)
                if postgrest:
                    from acquisition_postgrest import run_postgrest
                    print(json.dumps(run_postgrest(db,os.environ.get('ACQUISITION_TEST_POSTGREST',''),PG),sort_keys=True),flush=True)
        finally:
            if db:db.connection.close()
            if started:run([PG/'pg_ctl','-D',data,'-m','immediate','-w','stop'])


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--populated-upgrade',action='store_true')
    parser.add_argument('--postgrest',action='store_true')
    args=parser.parse_args()
    main(upgrade=args.populated_upgrade or args.postgrest,postgrest=args.postgrest)
