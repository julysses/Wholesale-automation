/** Selected real intake/transport RPCs on a disposable test schema, never remote. */
import fs from 'node:fs';
import assert from 'node:assert/strict';
import postgres from '../node_modules/postgres/src/index.js';
import {fixture} from '../tests/retell-app-transport-fixture.mjs';
import {installRecovery} from '../tests/retell-app-recovery-fixture.mjs';
import {installAutomatic} from '../tests/retell-app-automatic-fixture.mjs';
const url = new URL(process.env.SMS_TEST_ADMIN_URL);
if(url.hostname!=='127.0.0.1'||url.pathname!=='/wholesale_sms_test') throw Error('Disposable database required');
const sql=postgres(url.href,{max:8,onnotice:()=>{}});
const db={exec:async text=>{await sql.unsafe(text).simple();},
 query:async(text,args=[])=>({rows:[...await sql.unsafe(text,args)]})};
const read=name=>fs.readFileSync(new URL('../../frontend/supabase/migrations/'+name,import.meta.url),'utf8');
try {
 await fixture(db);
 await db.exec(read('20261017013643_retell_app_twilio_outbox.sql'));
 await installRecovery(db);
 await installAutomatic(db); // net/cron are table-only stubs; schedulers stay false.
 await db.exec(`
 CREATE SCHEMA extensions;
 CREATE EXTENSION "uuid-ossp" WITH SCHEMA extensions;
 ALTER TABLE public.leads
  ALTER COLUMN id SET DEFAULT gen_random_uuid(),
  ADD COLUMN assigned_to uuid, ADD COLUMN created_at timestamptz DEFAULT now(),
  ADD COLUMN owner_phone_1 text,ADD COLUMN owner_phone_2 text,ADD COLUMN owner_phone_3 text,
  ADD COLUMN owner_first_name text,ADD COLUMN owner_last_name text,ADD COLUMN owner_email text,
  ADD COLUMN property_address text,ADD COLUMN city text,ADD COLUMN state text,ADD COLUMN zip_code text,
  ADD COLUMN source text,ADD COLUMN inbound_channel text,ADD COLUMN internal_notes text,
  ADD COLUMN sms_sequence_active boolean DEFAULT false,ADD COLUMN email_sequence_active boolean DEFAULT false,
  ADD COLUMN contact_attempts integer DEFAULT 0,ADD COLUMN form_submission_id uuid,ADD COLUMN ad_campaign_id uuid,
  ADD COLUMN precision_tier integer,ADD COLUMN ai_qualification_summary text,
  ADD COLUMN score_motivation int,ADD COLUMN score_timeline int,ADD COLUMN score_equity int,
  ADD COLUMN score_condition int,ADD COLUMN score_flexibility int,ADD COLUMN priority_tier text,
  ADD COLUMN motivation_tag text,ADD COLUMN asking_price numeric;
 CREATE TABLE public.lead_form_configs(id uuid PRIMARY KEY,slug text UNIQUE,questions jsonb,
  active boolean DEFAULT true,send_confirmation_sms boolean DEFAULT true,thank_you_message text);
 ALTER TABLE public.lead_form_submissions
  ALTER COLUMN id SET DEFAULT gen_random_uuid(),
  ALTER COLUMN created_at SET DEFAULT now()-interval '2 minutes',ADD COLUMN form_id uuid REFERENCES public.lead_form_configs(id),
  ADD COLUMN raw_answers jsonb DEFAULT '{}',ADD COLUMN ip_address text,ADD COLUMN user_agent text,
  ADD COLUMN utm_source text,ADD COLUMN utm_medium text,ADD COLUMN utm_campaign text,
  ADD COLUMN computed_motivation_tag text,ADD COLUMN computed_timeline text,ADD COLUMN computed_condition text;
 ALTER TABLE public.app_notifications ADD COLUMN recipient_role text;
 CREATE TABLE public.dnc_registry(id uuid PRIMARY KEY,phone_number text,lead_id uuid,email text,reason text,source text,opt_out_keyword text,raw_payload jsonb);
 DROP TABLE public.email_delivery_events; DROP TABLE public.email_messages;
 `);
 await db.exec(read('20261007162642_sendgrid_delivery_receipts.sql'));
 // Real production suppression; retained reviewed-opt-in stub always refuses reactivation.
 await db.exec(read('20261015203524_preserve_unclassified_dnc.sql'));
 await db.exec(read('20261008235729_durable_public_intake_reference.sql'));
 const atomic=read('20261009004526_atomic_intake_alert_delivery.sql');
 await db.exec(atomic.slice(0,atomic.indexOf('CREATE OR REPLACE FUNCTION public.launch_monitor_findings')));
 await db.exec(read('20261017022551_retell_app_intake_handoff.sql'));
 await db.exec(read('20261019195020_sms_reply_notification_handoff.sql'));
 await db.exec(read('20261020184154_facebook_inquiry_sms_receipts.sql'));
 // Genuine competing transactions exercise the new native source relationship.
 const lead=crypto.randomUUID(), receipt=crypto.randomUUID(), job=crypto.randomUUID();
 await sql`insert into public.leads(id) values(${lead})`;
 const receipts=await Promise.all(Array.from({length:8},()=>sql`
  insert into public.facebook_lead_submissions(id,lead_id,leadgen_id,form_id,submitted_at,phone_number,raw_answers)
  values(${receipt},${lead},'local-concurrent-meta','local-form','2026-10-20T17:00:00Z','+12145550999','{}')
  on conflict(id) do nothing returning id`));
 assert.equal(receipts.filter(r=>r.length).length,1);
 const queues=await Promise.all(Array.from({length:8},()=>sql`
  insert into public.retell_form_sms_jobs(id,lead_id,facebook_submission_id,phone_number,due_at,expires_at,
   delivery_transport,delivery_body,delivery_sender)
  values(${job},${lead},${receipt},'+12145550999',now()-interval '1 minute',now()+interval '10 minutes',
   'app_twilio','Synthetic concurrency acknowledgment','+14695550101')
  on conflict(id) do nothing returning id`));
 assert.equal(queues.filter(r=>r.length).length,1);
 const claims=await Promise.all(Array.from({length:8},()=>sql`select id from public.claim_retell_app_ack(${job})`));
 assert.equal(claims.filter(r=>r.length).length,1);
 assert.equal((await sql`select count(*)::int n from public.sms_events where id=${job}`)[0].n,1);
 console.log(JSON.stringify({native_concurrency:'passed',workers:8,receipts:1,jobs:1,ack_claims:1,provider_calls:0}));
 console.log('Disposable lead journey schema installed; no external extensions or schedules activated.');
} finally {await sql.end();}
