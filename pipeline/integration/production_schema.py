"""Restore catalog DDL only into a validated disposable local database.

No customer rows, auth sessions, vault secrets or working network/cron extensions.
Application functions, constraints, policies and triggers come from the snapshot.
"""
import json
from pathlib import Path
from tests.local_journey_db import Database

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT/'docs/facebook-release/production-catalog.json').read_text())
META = json.loads((ROOT/'docs/facebook-release/production-metadata.json').read_text())
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
    db.query('SET check_function_bodies=false; SET search_path=public,extensions,wholesale_ingest')
    for role in ['anon','authenticated','service_role','postgres','wholesale_ingestor','wholesale_worker','supabase_admin']:
        db.query(f'CREATE ROLE {ident(role)} NOLOGIN'+(' BYPASSRLS' if role in ['service_role','postgres','supabase_admin'] else ''))
    db.query('CREATE SCHEMA extensions; CREATE EXTENSION "uuid-ossp" WITH SCHEMA extensions; CREATE EXTENSION pgcrypto WITH SCHEMA extensions')
    db.query('GRANT USAGE ON SCHEMA extensions TO PUBLIC')
    for name in ['private','wholesale_ingest','auth','net','vault','cron','supabase_migrations']:
        db.query('CREATE SCHEMA '+ident(name))
    db.query('''CREATE TABLE auth.users(id uuid PRIMARY KEY);
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
    CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.role',true),'') $$;
    CREATE TABLE net.test_requests(id bigserial PRIMARY KEY,url text);
    CREATE TABLE net._http_response(id bigint,status_code integer,timed_out boolean,content text);
    CREATE TABLE vault.decrypted_secrets(name text,decrypted_secret text);
    CREATE FUNCTION net.http_post(url text,body jsonb DEFAULT '{}',params jsonb DEFAULT '{}',headers jsonb DEFAULT '{}',timeout_milliseconds integer DEFAULT 1000)
    RETURNS bigint LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'External HTTP prohibited in rehearsal'; END $$;
    CREATE FUNCTION net.http_get(url text,params jsonb DEFAULT '{}',headers jsonb DEFAULT '{}',timeout_milliseconds integer DEFAULT 1000)
    RETURNS bigint LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'External HTTP prohibited in rehearsal'; END $$;
    CREATE TABLE cron.job(jobname text,active boolean);
    CREATE TABLE supabase_migrations.schema_migrations(version text PRIMARY KEY,name text);''')
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
            try: db.query('CREATE VIEW '+qualified(v)+' AS '+v['definition'])
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
    for f in CATALOG['functions']: grants(db,f['acl'],f['signature'],'FUNCTION')
    for s in META['schema_acls']: grants(db,s['acl'],ident(s['schema']),'SCHEMA')
    # Preserve defaults applicable to future objects, mapping production owner to local admin.
    kinds={'r':'TABLES','f':'FUNCTIONS','S':'SEQUENCES','T':'TYPES'}
    for a in META['default_acls'] or []:
        prefix='ALTER DEFAULT PRIVILEGES IN SCHEMA '+ident(a['schema'])
        db.query(prefix+' REVOKE ALL ON '+kinds[a['type']]+' FROM PUBLIC')
        for entry in a['acl'].strip('{}').split(','):
            role, value=entry.split('=',1); rights=value.split('/')[0]
            mapping={'r':'SELECT','a':'INSERT','w':'UPDATE','d':'DELETE','D':'TRUNCATE','x':'REFERENCES','t':'TRIGGER','X':'EXECUTE','U':'USAGE','m':'MAINTAIN'}
            for right in rights.replace('*',''):
                db.query(prefix+' GRANT '+mapping[right]+' ON '+kinds[a['type']]+' TO '+(ident(role) if role else 'PUBLIC'))
    for m in META['migrations']: db.query('INSERT INTO supabase_migrations.schema_migrations VALUES(%s,%s)',[m['version'],m['name']])
    for j in META['pause']['cron']: db.query('INSERT INTO cron.job VALUES(%s,false)',[j['jobname']])
    for name in ['retell_sms_scheduler','retell_app_scheduler']:
        db.query('INSERT INTO private.'+name+'(singleton,enabled) VALUES(true,false)')
    db.query("INSERT INTO auth.users VALUES('00000000-0000-4000-8000-000000000777')")
    db.query("INSERT INTO profiles(id,email,role,status) VALUES('00000000-0000-4000-8000-000000000777','owner@example.test','admin','approved')")
    db.query("INSERT INTO app_settings(key,value) VALUES('lead_owner_user_id','00000000-0000-4000-8000-000000000777')")
    print(json.dumps({'catalog_restore':'passed','tables':len(CATALOG['tables']),'functions':len(CATALOG['functions']),'constraints':len(CATALOG['constraints']),'triggers':len(CATALOG['triggers']),'policies':len(CATALOG['policies']),'production_rows_copied':0}),flush=True)

if __name__=='__main__':
    db=Database()
    try: restore(db)
    finally: db.connection.close()
