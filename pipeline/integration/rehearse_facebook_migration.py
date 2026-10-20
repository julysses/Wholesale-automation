"""Rehearse the one Facebook migration; never accepts a non-disposable DSN."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from uuid import uuid4
from production_schema import CATALOG, ROOT, qualified
from tests.local_journey_db import Database
from tools.facebook_inquiry import save_submission

MIGRATION=ROOT/'frontend/supabase/migrations/20261020184154_facebook_inquiry_sms_receipts.sql'
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def rows(db):
    return {qualified(t):db.query('SELECT to_jsonb(t)'+("-'facebook_submission_id'" if t['name']=='retell_form_sms_jobs' else '')+' AS row FROM '+qualified(t)+' t ORDER BY to_jsonb(t)::text') for t in CATALOG['tables']}
def functions(db):
    return {r['signature']:r for r in db.query("SELECT p.oid::regprocedure::text signature,pg_get_functiondef(p.oid) definition,p.proacl::text acl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND p.prokind='f'")}
def assert_rejected(db,statement,params=()):
    try: db.query(statement,params)
    except Exception: return
    raise AssertionError('Expected database rejection: '+statement)

def rehearse(db):
    # Synthetic old website work covers both transports and all preexisting statuses.
    counter=0
    for transport in ['app_twilio','retell_native']:
        for status in ['scheduled','processing','accepted','stopped','review']:
            counter+=1
            ident=str(uuid4()); phone=f'+121455508{counter:02d}'
            db.query("INSERT INTO leads(id,property_address,city,dnc,status) VALUES(%s,'Synthetic retained property','Dallas',true,'dnc')",[ident])
            db.query("INSERT INTO lead_form_submissions(id,lead_id,raw_answers) VALUES(%s,%s,'{\"sms_opt_in\":false}')",[ident,ident])
            db.query("INSERT INTO retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at,status,delivery_transport,delivery_body,delivery_sender,reason) VALUES(%s,%s,%s,%s,now()-interval '2 days',now()-interval '1 day',%s,%s,%s,%s,'Synthetic held or historical work; never replay')",[ident,ident,ident,phone,status,transport,'Synthetic acknowledgment' if transport=='app_twilio' else None,'+14695550101' if transport=='app_twilio' else None])
            db.query("INSERT INTO sms_events(id,lead_id,provider,direction,phone_number,status,raw_payload) VALUES(%s,%s,'twilio','outbound',%s,'undelivered','{\"provider_sid\":\"SMaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"ErrorCode\":\"30007\"}')",[ident,ident,phone])
            if transport=='app_twilio':
                db.query("INSERT INTO retell_api_sessions(id,lead_id,phone_number,sender_number,status) VALUES(%s,%s,%s,'+14695550101','review')",[ident,ident,phone])
                db.query("INSERT INTO retell_api_turns(id,session_id,inbound_sid,recipient_text,status,expires_at) VALUES(%s,%s,%s,'Synthetic held reply','review',now()-interval '1 day')",[ident,ident,'SM'+ident.replace('-','')])
    db.query("INSERT INTO email_messages(id,recipient,subject,provider,status) VALUES(%s,'owner@example.test','Synthetic retained receipt','sendgrid','delivered')",[str(uuid4())])
    before=rows(db); oldfuncs=functions(db)
    history=db.query('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version')
    db.query('BEGIN')
    db.query(MIGRATION.read_text())
    assert rows(db)==before
    db.query('ROLLBACK')
    assert rows(db)==before and functions(db)==oldfuncs
    assert db.query("SELECT to_regclass('public.facebook_lead_submissions') name")[0]['name'] is None
    db.query('BEGIN'); db.query(MIGRATION.read_text()); db.query('COMMIT')
    assert rows(db)==before
    afterfuncs=functions(db)
    changed=[k for k in oldfuncs if oldfuncs[k]!=afterfuncs[k]]
    assert changed==['protect_retell_form_transport()'],changed
    assert oldfuncs[changed[0]]['acl']==afterfuncs[changed[0]]['acl']
    assert set(afterfuncs)-set(oldfuncs)=={'protect_facebook_submission()'}
    assert db.query('SELECT * FROM supabase_migrations.schema_migrations ORDER BY version')==history
    assert db.query("SELECT to_regprocedure('private.reconcile_empty_retell_session(uuid)') absent")[0]['absent'] is None
    lead,receipt,job=[str(uuid4()) for _ in range(3)];phone='+12145550951'
    from uuid import NAMESPACE_URL, uuid5
    receipt=str(uuid5(NAMESPACE_URL,'wholesaleos:facebook:submission:local-concurrent-lead'))
    db.query("INSERT INTO leads(id,property_address,city) VALUES(%s,'Synthetic native property','Dallas')",[lead])
    def competing(_):
        c=Database()
        try:
            c.query('SET ROLE service_role')
            saved=save_submission(c,lead,{'_facebook_consent':{'leadgen_id':'local-concurrent-lead',
                'form_id':'local-form','submitted_at':'2026-10-20T17:00:00Z','phone':phone}})
            assert saved['_facebook_consent']['leadgen_id']=='local-concurrent-lead'
            try:
                queued=c.query("INSERT INTO retell_form_sms_jobs(id,lead_id,facebook_submission_id,phone_number,due_at,expires_at,delivery_transport,delivery_body,delivery_sender) VALUES(%s,%s,%s,%s,now()-interval '1 minute',now()+interval '10 minutes','app_twilio','Synthetic acknowledgment','+14695550101') ON CONFLICT(id) DO NOTHING RETURNING id",[job,lead,receipt,phone])
            except Exception as exc:
                assert getattr(exc,'pgcode',None)=='23505'
                assert c.query('SELECT id FROM retell_form_sms_jobs WHERE id=%s',[job])
                queued=[]
            claimed=c.query('SELECT id FROM claim_retell_app_ack(%s)',[job])
            return 1,len(queued),len(claimed)
        finally:c.connection.close()
    with ThreadPoolExecutor(max_workers=8) as pool: outcomes=list(pool.map(competing,range(8)))
    assert [sum(r[i] for r in outcomes) for i in range(3)]==[8,1,1],outcomes
    assert len(db.query('SELECT id FROM facebook_lead_submissions WHERE lead_id=%s',[lead]))==1
    assert_rejected(db,'UPDATE facebook_lead_submissions SET raw_answers=\'{}\' WHERE id=%s',[receipt])
    assert_rejected(db,'DELETE FROM facebook_lead_submissions WHERE id=%s',[receipt])
    assert_rejected(db,'UPDATE retell_form_sms_jobs SET facebook_submission_id=NULL WHERE id=%s',[job])
    assert_rejected(db,"INSERT INTO retell_form_sms_jobs(id,lead_id,submission_id,facebook_submission_id,phone_number,due_at,expires_at) VALUES(%s,%s,(SELECT id FROM lead_form_submissions LIMIT 1),%s,%s,now(),now())",[str(uuid4()),lead,receipt,phone])
    for role in ['anon','authenticated']:
        for privilege in ['SELECT','INSERT','UPDATE','DELETE']:
            assert db.query('SELECT has_table_privilege(%s,\'public.facebook_lead_submissions\',%s) allowed',[role,privilege])[0]['allowed'] is False
        db.query('SET ROLE '+role)
        assert_rejected(db,'SELECT * FROM facebook_lead_submissions')
        db.query('RESET ROLE')
    for privilege in ['UPDATE','DELETE']:
        assert db.query("SELECT has_table_privilege('service_role','public.facebook_lead_submissions',%s) allowed",[privilege])[0]['allowed'] is False
    assert db.query("SELECT relrowsecurity enabled FROM pg_class WHERE oid='public.facebook_lead_submissions'::regclass")[0]['enabled'] is True
    assert not db.query('SELECT * FROM net.test_requests')
    assert not db.query('SELECT * FROM cron.job WHERE active')
    assert not db.query('SELECT * FROM private.retell_sms_scheduler WHERE enabled')
    assert not db.query('SELECT * FROM private.retell_app_scheduler WHERE enabled')
    print(json.dumps({'migration_rehearsal':'passed','rollback_before_commit':'passed','retained_table_data_sha256':digest(before),'unchanged_tables':len(before),'existing_jobs':10,'held_sessions_and_turns':5,'preserved_migration_history':len(history),'changed_existing_functions':changed,'concurrent_workers':8,'receipts':1,'jobs':1,'ack_claims':1,'provider_calls':0,'migration_sha256':hashlib.sha256(MIGRATION.read_bytes()).hexdigest()}),flush=True)

if __name__=='__main__':
    db=Database()
    try: rehearse(db)
    finally: db.connection.close()
