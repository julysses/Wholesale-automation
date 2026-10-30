"""Populated candidate upgrade in the baseline runner's disposable cluster only."""
from collections import Counter
import hashlib
import json
import sys

from rehearse_acquisition_baseline import CATALOG, EVIDENCE, ROOT, ident, qualified, grants

sys.path.insert(0,str(ROOT/'scripts'))
from acquisition_storage_fixture import install_storage_fixture

ADMIN='00000000-0000-4000-8000-000000000777'
LEAD='20000000-0000-4000-8000-000000000777'
RECEIPT='71000000-0000-4000-8000-000000000777'
JOB='72000000-0000-4000-8000-000000000777'
TURN='73000000-0000-4000-8000-000000000777'


def seed(db):
    # All content is synthetic; every transport remains held before legacy triggers run.
    for name in ('retell_sms_scheduler','retell_app_scheduler'):
        db.query('INSERT INTO private.'+name+'(singleton,enabled) VALUES(true,false)')
    db.query('INSERT INTO auth.users(id) VALUES(%s)',[ADMIN])
    db.query('INSERT INTO auth.sessions(id,user_id) VALUES(%s,%s)',[ADMIN,ADMIN])
    db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'upgrade-owner@example.test','admin','approved')",[ADMIN])
    db.query("INSERT INTO app_settings(key,value) VALUES('lead_owner_user_id',%s)",[ADMIN])
    db.query("INSERT INTO leads(id,property_address,city,owner_phone_1) VALUES(%s,'77 Synthetic Upgrade St','Dallas','+12145550177')",[LEAD])
    db.query("INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES('30000000-0000-4000-8000-000000000777','TX','Dallas','synthetic-upgrade-parcel',%s)",[LEAD])
    db.query("INSERT INTO facebook_lead_submissions(id,lead_id,leadgen_id,form_id,raw_answers,phone_number) VALUES(%s,%s,'synthetic-upgrade-lead','synthetic-upgrade-form','{}','+12145550177')",[RECEIPT,LEAD])
    db.query("INSERT INTO retell_form_sms_jobs(id,lead_id,facebook_submission_id,phone_number,due_at,expires_at,status) VALUES(%s,%s,%s,'+12145550177',now()-interval '1 day',now()-interval '1 hour','review')",[JOB,LEAD,RECEIPT])
    db.query("INSERT INTO private.retell_owner_retest_authorizations(job_id,lead_id,phone_number,operator_id,reason,created_at,expires_at,before_state) VALUES(%s,%s,'+12145550177',%s,'Synthetic historical authorization',now()-interval '2 days',now()-interval '2 days'+interval '10 minutes','{}')",[JOB,LEAD,ADMIN])
    db.query("INSERT INTO retell_api_sessions(id,lead_id,phone_number,sender_number,status) VALUES(%s,%s,'+12145550177','+12145550178','review')",[JOB,LEAD])
    db.query("INSERT INTO sms_events(id,lead_id,provider,direction,body,status) VALUES(%s,%s,'synthetic','inbound','Synthetic held history','review')",[TURN,LEAD])
    db.query("INSERT INTO retell_api_turns(id,session_id,inbound_sid,recipient_text,status,expires_at) VALUES(%s,%s,%s,'Synthetic held history','review',now()-interval '1 day')",[TURN,JOB,'SM'+'7'*32])
    db.query("INSERT INTO private.retell_generation_reconciliations(turn_id,session_id,request_id,event_id,messages,before_state,proof,note) VALUES(%s,%s,777,%s,'[]','{}','{}','Synthetic historical reconciliation')",[TURN,JOB,TURN])
    db.query("INSERT INTO audit_logs(entity_type,entity_id,action,actor) VALUES('legacy','synthetic-upgrade','retained','system')")
    db.query("INSERT INTO webhook_jobs(source,payload) VALUES('legacy_fixture','{\"synthetic_upgrade\":true}')")
    db.query("INSERT INTO campaigns(name) VALUES('Synthetic historical campaign')")
    db.query("INSERT INTO ad_campaigns(name,status) VALUES('Synthetic historical advertising','draft')")
    db.query("INSERT INTO ad_creatives(name,status) VALUES('Synthetic historical creative','draft')")
    db.query("INSERT INTO tasks(title,lead_id) VALUES('Synthetic historical task',%s)",[LEAD])


def fingerprints(db, tables):
    result={}
    for table in tables:
        columns=','.join(ident(c['name']) for c in table['columns'])
        rows=db.query('SELECT to_jsonb(row)::text AS payload FROM (SELECT '+columns+' FROM '+qualified(table)+') row')
        result[qualified(table)]=Counter(hashlib.sha256(r['payload'].encode()).hexdigest() for r in rows)
    return result


def run_upgrade(db):
    manifest=json.loads((EVIDENCE/'acquisition-upgrade-manifest.json').read_text())
    files=manifest['migrations']
    if manifest['production_apply_approved'] is not False or manifest['baseline']!='2026-10-30-upgrade-catalog.json':
        raise RuntimeError('Explicit offline candidate manifest required')
    names=[r['file'] for r in files]
    available=sorted(p.name for p in (ROOT/'frontend/supabase/migrations').glob('2026102*_acquisition*.sql'))
    if names!=available or len(names)!=len(set(names)):
        raise RuntimeError('Candidate manifest does not match the complete ordered acquisition sequence')
    deployed={m['version'] for m in CATALOG['migrations']}
    for row in files:
        path=ROOT/'frontend/supabase/migrations'/row['file']
        if row['file'].split('_',1)[0] in deployed or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise RuntimeError('Deployed or changed candidate migration: '+row['file'])
    install_storage_fixture(db.query)  # Explicit platform fixture, not hosted Storage acceptance.
    authority=json.loads((EVIDENCE/'2026-10-30-upgrade-storage-authority.json').read_text())
    db.query('CREATE ROLE supabase_storage_admin NOLOGIN NOINHERIT; CREATE ROLE dashboard_user NOLOGIN; ALTER SCHEMA storage OWNER TO supabase_admin')
    db.query('SET ROLE supabase_admin')
    grants(db,authority['schema']['acl'],'storage','SCHEMA')
    db.query('RESET ROLE')
    for table in authority['tables']:
        if table['owner']!='supabase_storage_admin':raise RuntimeError('Unexpected Storage owner')
        db.query('ALTER TABLE storage.'+ident(table['name'])+' OWNER TO supabase_storage_admin')
        db.query('SET ROLE supabase_storage_admin')
        grants(db,table['acl'],'storage.'+ident(table['name']),'TABLE')
        db.query('RESET ROLE')
    if db.query("SELECT pg_has_role('postgres','supabase_storage_admin','USAGE') AS inherited")[0]['inherited']:
        raise RuntimeError('Migration role must not inherit Storage ownership')
    if db.query("SELECT rolsuper FROM pg_roles WHERE rolname='postgres'")[0]['rolsuper']:
        raise RuntimeError('Migration role must not be superuser')
    seed(db)
    before=fingerprints(db,CATALOG['tables'])
    storage_before=db.query('SELECT bucket_id,name,metadata FROM storage.objects ORDER BY name')
    db.query('SET check_function_bodies=true; SET search_path=public,extensions; SET ROLE postgres')
    for row in files:
        print(json.dumps({'applying_candidate':row['file']}),flush=True)
        try:
            db.query((ROOT/'frontend/supabase/migrations'/row['file']).read_text())
            db.query('INSERT INTO supabase_migrations.schema_migrations(version,name) VALUES(%s,%s)',
                [row['file'].split('_',1)[0],row['file'].split('_',1)[1][:-4]])
        except Exception:
            db.query('ROLLBACK; RESET ROLE')
            raise
    db.query('RESET ROLE')
    after=fingerprints(db,CATALOG['tables'])
    changed=[name for name,rows in before.items() if rows-after[name]]
    if changed:raise RuntimeError('Historical rows changed or disappeared: '+', '.join(changed))
    if db.query('SELECT bucket_id,name,metadata FROM storage.objects ORDER BY name')!=storage_before:
        raise RuntimeError('Historical Storage fixture changed')
    for name in ('retell_sms_scheduler','retell_app_scheduler','acquisition_activation'):
        if db.query('SELECT enabled FROM private.'+name)!=[{'enabled':False}]:
            raise RuntimeError('Execution control changed: '+name)
    for name in ('acquisition_integrations','acquisition_evidence_verification_keys'):
        if db.query('SELECT count(*) AS n FROM private.'+name)[0]['n']!=0:
            raise RuntimeError('Candidate provisioned live integration/signing configuration')
    for table in ('net.test_requests','cron.job','vault.decrypted_secrets'):
        if db.query('SELECT count(*) AS n FROM '+table)[0]['n']!=0:raise RuntimeError('External execution state changed')
    from acquisition_upgrade_access import run_access_probes
    access = run_access_probes(db)
    if fingerprints(db,CATALOG['tables']) != after:
        raise RuntimeError('Access probes changed historical records')
    return {'access_probes':access,'populated_upgrade':'passed','candidate_migrations_applied':len(files),
        'historical_rows_preserved':sum(sum(x.values()) for x in before.values()),
        'historical_tables_with_rows':sum(bool(x) for x in before.values()),
        'historical_table_definitions_checked':len(before),'storage_fixture_preserved':True,
        'execution_controls_disabled':True,'production_rows_copied':0,'live_platform_acceptance':False}
