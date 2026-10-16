import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';

const migrations = new URL('../../frontend/supabase/migrations/', import.meta.url);
const fix = fs.readFileSync(new URL('20261016205323_reconcile_retell_intake_handoffs.sql', migrations), 'utf8');

test('intake handoff completion requires durable scheduling and preserves uncertain delivery', async t => {
 const db = new PGlite(); t.after(() => db.close());
 await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
 CREATE SCHEMA extensions;
 -- Deterministic identifier adapter only; production rollback QA uses uuid-ossp.
 CREATE FUNCTION extensions.uuid_generate_v5(uuid,text) RETURNS uuid LANGUAGE sql IMMUTABLE AS 'SELECT md5($1::text||$2)::uuid';
 CREATE TABLE public.app_notifications(id uuid PRIMARY KEY,lead_id uuid,type text,metadata jsonb,body text);
 CREATE TABLE public.retell_form_sms_jobs(id uuid PRIMARY KEY,lead_id uuid,status text);
 CREATE TABLE public.sms_events(id uuid PRIMARY KEY,status text);
 INSERT INTO public.sms_events VALUES(gen_random_uuid(),'undelivered');`);
 const original = fs.readFileSync(new URL('20261009004526_atomic_intake_alert_delivery.sql', migrations),'utf8');
 await db.exec(original.slice(original.indexOf('CREATE FUNCTION public.finish_intake_notification'), original.indexOf('CREATE OR REPLACE FUNCTION public.launch_monitor_findings')));
 const fixtures = [];
 for (const [sms, email, job, expected] of [
  ['no_consent_or_form_confirmation_disabled','accepted',false,'completed'],
  ['scheduled_retell_60_seconds','accepted',true,'completed'],
  ['scheduled_retell_60_seconds','accepted',false,'review'],
  ['scheduled_retell_60_seconds','unknown',true,'review'],
  ['schedule_unconfirmed','accepted',false,'review'],
  ['consent_or_suppression_hold','accepted',false,'review'],
  ['failed_or_blocked','accepted',false,'review'],
  ['unknown','accepted',false,'review'],
  ['confirmed_suppression','accepted',false,'review'],
  ['confirmed_suppression','unknown',false,'review'],
 ]) {
  const lead=crypto.randomUUID(), claim=crypto.randomUUID();
  await db.query(`INSERT INTO public.app_notifications VALUES(extensions.uuid_generate_v5('6ba7b811-9dad-11d1-80b4-00c04fd430c8','wholesaleos:intake-alert:'||$1),$1::uuid,'pipeline_step',$2::jsonb,'Original')`,[lead,JSON.stringify({delivery_state:'processing',delivery_claim:claim,claimed_at:'2026-10-15T12:00:00Z'})]);
  if(job) await db.query("INSERT INTO public.retell_form_sms_jobs VALUES(gen_random_uuid(),$1,'review')",[lead]);
  const outcomes={owner_email:email,seller_sms:sms};
  await db.query('SELECT public.finish_intake_notification($1,$2,$3,$4)',[lead,claim,JSON.stringify(outcomes),'Original channel outcome']);
  fixtures.push({lead,claim,outcomes,expected});
 }
 const channelsBefore=await db.query('SELECT * FROM public.retell_form_sms_jobs ORDER BY id');
 await db.exec(fix);
 await db.exec(fs.readFileSync(new URL('20261016210016_retell_next_contact_window_handoff.sql', migrations),'utf8'));
 await db.exec(fs.readFileSync(new URL('20261016223736_confirmed_suppression_handoff.sql', migrations),'utf8'));
 for(const {lead,claim,outcomes,expected} of fixtures){
  let row=(await db.query('SELECT metadata,body FROM public.app_notifications WHERE lead_id=$1',[lead])).rows[0];
  assert.equal(row.metadata.delivery_state,expected);
  assert.equal(row.metadata.seller_sms,outcomes.seller_sms);
  assert.equal(row.metadata.delivery_claim,claim);
  assert.equal(row.metadata.claimed_at,'2026-10-15T12:00:00Z');
  assert.equal(row.body,'Original channel outcome');
  const replay=(await db.query('SELECT public.finish_intake_notification($1,$2,$3,$4) AS result',[lead,claim,JSON.stringify(outcomes),'Retry'])).rows[0].result;
  assert.equal(replay.finished,false,'Resolved and review outcomes must never become replayable');
  await db.query("UPDATE public.app_notifications SET metadata=metadata||'{\"delivery_state\":\"processing\"}'::jsonb WHERE lead_id=$1",[lead]);
  const wrong=(await db.query('SELECT public.finish_intake_notification($1,$2,$3,$4) AS result',[lead,crypto.randomUUID(),JSON.stringify(outcomes),'Wrong claimant'])).rows[0].result;
  assert.equal(wrong.finished,false);
  const nextOutcomes=outcomes.seller_sms==='scheduled_retell_60_seconds'?{...outcomes,seller_sms:'scheduled_retell_next_contact_window'}:outcomes;
  const finished=(await db.query('SELECT public.finish_intake_notification($1,$2,$3,$4) AS result',[lead,claim,JSON.stringify(nextOutcomes),'Current handoff'])).rows[0].result;
  const currentExpected=outcomes.seller_sms==='confirmed_suppression' && outcomes.owner_email==='accepted'?'completed':expected;
  assert.equal(finished.delivery_state,currentExpected);
 }
 assert.deepEqual((await db.query('SELECT * FROM public.retell_form_sms_jobs ORDER BY id')).rows,channelsBefore.rows);
 assert.deepEqual((await db.query('SELECT status FROM public.sms_events')).rows,[{status:'undelivered'}]);
 for(const role of ['anon','authenticated']){
  const privilege=(await db.query("SELECT has_function_privilege($1,'public.finish_intake_notification(uuid,uuid,jsonb,text)','EXECUTE') AS allowed",[role])).rows[0];
  assert.equal(privilege.allowed,false);
 }
});
