import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
const root=new URL('../../frontend/supabase/migrations/',import.meta.url);
const migration=fs.readFileSync(new URL('20261019195020_sms_reply_notification_handoff.sql',root),'utf8');
const owner='00000000-0000-4000-8000-000000000001',assignee='00000000-0000-4000-8000-000000000002',lead='00000000-0000-4000-8000-000000000003',phone='+12145550196';
async function fixture(t){
 const db=new PGlite();t.after(()=>db.close());
 await db.exec(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role;
 CREATE TABLE public.profiles(id uuid PRIMARY KEY,status text);
 CREATE TABLE public.app_settings(key text PRIMARY KEY,value text);
 CREATE TABLE public.leads(id uuid PRIMARY KEY,assigned_to uuid,owner_phone_1 text,owner_phone_2 text,owner_phone_3 text,created_at timestamptz DEFAULT now(),dnc boolean DEFAULT false,status text DEFAULT 'new',sms_sequence_active boolean DEFAULT true,email_sequence_active boolean DEFAULT true,ai_calling_paused boolean DEFAULT false);
 CREATE TABLE public.tasks(id uuid PRIMARY KEY,lead_id uuid,title text,description text,priority text,status text,type text,assigned_to uuid,due_date timestamptz);
 CREATE TABLE public.sms_events(id uuid PRIMARY KEY,lead_id uuid,provider text,direction text,phone_number text,body text,status text,opt_out boolean,raw_payload jsonb,created_at timestamptz DEFAULT now());
 CREATE TABLE public.dnc_registry(id uuid PRIMARY KEY,phone_number text,lead_id uuid,reason text,source text,opt_out_keyword text,raw_payload jsonb);
 CREATE TABLE public.app_notifications(id uuid PRIMARY KEY,recipient_id uuid,recipient_role text,type text,title text,body text,action_url text,lead_id uuid,metadata jsonb);
 CREATE FUNCTION public.intake_phone_status(text,uuid,text) RETURNS jsonb LANGUAGE sql AS $$ SELECT jsonb_build_object('suppressed',exists(select 1 from public.dnc_registry where phone_number=$1)) $$;
 INSERT INTO public.profiles VALUES('${owner}','approved'),('${assignee}','approved');
 INSERT INTO public.app_settings VALUES('lead_owner_user_id','${owner}');
 INSERT INTO public.leads(id,owner_phone_1) VALUES('${lead}','${phone}');`);
 const old=fs.readFileSync(new URL('20261015192903_retell_form_sms_production.sql',root),'utf8').split('-- Commit carrier replies')[1];await db.exec('-- Commit carrier replies'+old);
 const q=async(s,a=[])=>(await db.query(s,a)).rows;
 const receipt=async(body='Please call ASAP',id=crypto.randomUUID())=>{const result=await q("select public.record_twilio_event($1,'inbound',$2) result",[id,JSON.stringify({MessageSid:'SM'+id.replaceAll('-',''),From:phone,Body:body})]);return{id,result:result[0].result};};
 return{db,q,receipt};
}
test('repairs missing task owner/due, routes new replies, and keeps carrier retry idempotent',async t=>{
 const {db,q,receipt}=await fixture(t);const old=await receipt();
 await db.exec(migration);let task=(await q('select * from public.tasks where id=$1',[old.id]))[0];
 assert.equal(task.assigned_to,owner);assert.ok(task.due_date);assert.equal((await q('select recipient_id from public.app_notifications where id=$1',[old.id]))[0].recipient_id,owner);
 await q('update public.leads set assigned_to=$1',[assignee]);const fresh=await receipt();task=(await q('select * from public.tasks where id=$1',[fresh.id]))[0];assert.equal(task.assigned_to,assignee);assert.ok(task.due_date);
 assert.equal((await receipt('Please call ASAP',fresh.id)).result.duplicate,true);assert.equal((await q('select count(*)::int n from public.tasks'))[0].n,2);
 assert.equal((await q("select has_function_privilege('authenticated','public.record_twilio_event(uuid,text,jsonb)','execute') allowed"))[0].allowed,false);
});
test('STOP still suppresses/cancels atomically and later replies cannot re-open tasks',async t=>{
 const {db,q,receipt}=await fixture(t);await db.exec(migration);await receipt();
 await q("update public.profiles set status='pending'");await receipt('STOP');await receipt('call me');await receipt('START');
 assert.equal((await q('select dnc from public.leads'))[0].dnc,true);assert.deepEqual((await q('select status from public.tasks')).map(x=>x.status),['cancelled']);
 await db.exec(migration);assert.equal((await q('select status from public.tasks'))[0].status,'cancelled');
});
test('missing approved owner does not lose a receipt, and backfill preserves operator decisions',async t=>{
 const {db,q,receipt}=await fixture(t);const existing=await receipt();
 await q("update public.tasks set assigned_to=$1,due_date='2026-12-01'",[assignee]);await db.exec(migration);
 assert.equal((await q('select assigned_to from public.tasks'))[0].assigned_to,assignee);
 await q("update public.profiles set status='pending'");const fresh=await receipt();const task=(await q('select * from public.tasks where id=$1',[fresh.id]))[0];assert.equal(task.assigned_to,null);assert.ok(task.due_date);
 assert.equal((await q('select count(*)::int n from public.app_notifications'))[0].n,2);assert.ok(existing.id);
});
