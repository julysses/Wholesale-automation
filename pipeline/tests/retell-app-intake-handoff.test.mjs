import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
const migration=fs.readFileSync(new URL('../../frontend/supabase/migrations/20261017022551_retell_app_intake_handoff.sql',import.meta.url),'utf8');

test('app/native handoffs require the matching saved lead and transport without claiming delivery or reopening history',async t=>{
 const db=new PGlite();t.after(()=>db.close());
 await db.exec(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role;
 CREATE SCHEMA extensions;
 CREATE FUNCTION extensions.uuid_generate_v5(uuid,text) RETURNS uuid LANGUAGE sql IMMUTABLE AS 'SELECT md5($1::text||$2)::uuid';
 CREATE TABLE public.app_notifications(id uuid PRIMARY KEY,lead_id uuid,type text,metadata jsonb,body text);
 CREATE TABLE public.retell_form_sms_jobs(id uuid PRIMARY KEY,lead_id uuid,status text,delivery_transport text);
 CREATE TABLE public.sms_events(id uuid PRIMARY KEY,status text);
 INSERT INTO public.app_notifications VALUES(gen_random_uuid(),gen_random_uuid(),'pipeline_step','{"delivery_state":"review","seller_sms":"schedule_unconfirmed"}','Historical uncertainty');
 INSERT INTO public.sms_events VALUES(gen_random_uuid(),'undelivered');`);
 const historical=(await db.query('select * from public.app_notifications')).rows;
 await db.exec(migration);
 assert.deepEqual((await db.query('select * from public.app_notifications')).rows,historical,'No historical claims or outcomes rewritten');
 for(const [outcome,transport] of [
  ['scheduled_app_twilio_60_seconds','app_twilio'],
  ['scheduled_app_twilio_next_contact_window','app_twilio'],
  ['existing_app_twilio_job','app_twilio'],
  ['scheduled_retell_60_seconds','retell_native'],
  ['scheduled_retell_next_contact_window','retell_native'],
  ['existing_retell_native_job','retell_native'],
 ]){
  for(const evidence of ['matching','missing','wrong_lead','wrong_transport','unknown_email']){
   const lead=crypto.randomUUID(),claim=crypto.randomUUID(),job=crypto.randomUUID();
   const metadata={delivery_state:'processing',delivery_claim:claim,claimed_at:'2026-10-16T12:00:00Z'};
   await db.query(`insert into public.app_notifications values(extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','wholesaleos:intake-alert:'||$1),$1::uuid,'pipeline_step',$2::jsonb,'Before')`,[lead,JSON.stringify(metadata)]);
   if(evidence!=='missing')await db.query('insert into public.retell_form_sms_jobs values($1,$2,$3,$4)',[job,evidence==='wrong_lead'?crypto.randomUUID():lead,'review',evidence==='wrong_transport'?(transport==='app_twilio'?'retell_native':'app_twilio'):transport]);
   const outcomes={owner_email:evidence==='unknown_email'?'unknown':'accepted',seller_sms:outcome,
    delivery_claim:'must-not-replace',claimed_at:'must-not-replace',delivery_state:'must-not-replace'};
   const finish=async claimant=>(await db.query('select public.finish_intake_notification($1,$2,$3,$4) r',[lead,claimant,JSON.stringify(outcomes),'Durable handoff; delivery unconfirmed'])).rows[0].r;
   assert.equal((await finish(crypto.randomUUID())).finished,false,'Wrong claimant cannot finish');
   const result=await finish(claim);
   assert.equal(result.finished,true);
   assert.equal(result.delivery_state,evidence==='matching'?'completed':'review',`${outcome}: ${evidence}`);
   const row=(await db.query('select metadata,body from public.app_notifications where lead_id=$1',[lead])).rows[0];
   assert.equal(row.metadata.seller_sms,outcome);
   assert.equal(row.metadata.delivery_claim,claim);assert.equal(row.metadata.claimed_at,metadata.claimed_at);
   assert.equal(row.body,'Durable handoff; delivery unconfirmed');
   assert.equal((await finish(claim)).finished,false,'No provider replay from completed/review notification');
  }
 }
 // Unknown scheduling/consent must remain review even with a matching app job.
 for(const outcome of ['schedule_unconfirmed','consent_or_suppression_hold','app_transport_configuration_hold','unknown']){
  const lead=crypto.randomUUID(),claim=crypto.randomUUID();
  await db.query(`insert into public.app_notifications values(extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','wholesaleos:intake-alert:'||$1),$1::uuid,'pipeline_step',$2::jsonb,'Before')`,[lead,JSON.stringify({delivery_state:'processing',delivery_claim:claim})]);
  await db.query("insert into public.retell_form_sms_jobs values(gen_random_uuid(),$1,'scheduled','app_twilio')",[lead]);
  const result=(await db.query('select public.finish_intake_notification($1,$2,$3,$4) r',[lead,claim,JSON.stringify({owner_email:'accepted',seller_sms:outcome}),'Uncertainty'])).rows[0].r;
  assert.equal(result.delivery_state,'review');
 }
 assert.deepEqual((await db.query('select status from public.sms_events')).rows,[{status:'undelivered'}]);
 assert.equal((await db.query("select count(*)::int n from public.retell_form_sms_jobs where status not in ('review','scheduled')")).rows[0].n,0);
 for(const role of ['anon','authenticated'])assert.equal((await db.query("select has_function_privilege($1,'public.finish_intake_notification(uuid,uuid,jsonb,text)','EXECUTE') allowed",[role])).rows[0].allowed,false);
 assert.equal((await db.query("select has_function_privilege('service_role','public.finish_intake_notification(uuid,uuid,jsonb,text)','EXECUTE') allowed")).rows[0].allowed,true);
});
