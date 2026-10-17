import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
import {fixture,job,native,phone} from './retell-app-transport-fixture.mjs';
import {installRecovery} from './retell-app-recovery-fixture.mjs';
import {installAutomatic} from './retell-app-automatic-fixture.mjs';
async function setup(t){
 const db=new PGlite();t.after(()=>db.close());const f=await fixture(db);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261017013643_retell_app_twilio_outbox.sql',import.meta.url),'utf8'));
 await installRecovery(db);await installAutomatic(db);
 const pick=(target=null,first=false,phones=null)=>f.rpc('pick_retell_app_work',[target,first,phones]);
 const tick=async()=>(await f.q('select private.tick_retell_app_sms() result'))[0].result;
 const enable=()=>f.q('update private.retell_app_scheduler set enabled=true,start_hour=0,end_hour=24');
 return {...f,pick,tick,enable};
}

test('installation is inert and private scheduler controls are unavailable to API roles',async t=>{
 const {q,tick}=await setup(t);
 assert.equal((await tick()).status,'disabled');
 assert.equal((await q('select enabled from private.retell_app_scheduler'))[0].enabled,false);
 assert.equal((await q('select active from cron.job'))[0].active,false);
 assert.equal((await q('select count(*)::int n from net.test_requests'))[0].n,0);
 for(const role of ['anon','authenticated','service_role']){
  assert.equal((await q("select has_function_privilege($1,'private.tick_retell_app_sms()','EXECUTE') allowed",[role]))[0].allowed,false);
  assert.equal((await q("select has_table_privilege($1,'private.retell_app_scheduler','UPDATE') allowed",[role]))[0].allowed,false);
 }
 for(const role of ['anon','authenticated'])assert.equal((await q("select has_function_privilege($1,'public.pick_retell_app_work(uuid,boolean,text[])','EXECUTE') allowed",[role]))[0].allowed,false);
});

test('selection leases only eligible app work, no native or out-of-scope jobs, and never creates SMS',async t=>{
 const {q,pick}=await setup(t);
 assert.equal((await pick(native,true,[phone])).selected,false);
 assert.equal((await pick(null,false,[])).selected,false);
 assert.equal((await pick(null,false,['+12145550199'])).selected,false);
 const result=await pick(job,true,[phone]);assert.equal(result.reference,job);assert.equal(result.action,'ack');
 assert.equal((await pick()).selected,false);
 assert.equal((await q('select status from public.retell_form_sms_jobs where id=$1',[job]))[0].status,'scheduled');
 assert.equal((await q('select count(*)::int n from public.sms_events'))[0].n,0);
 await q("update public.retell_form_sms_jobs set auto_selected_at=now()-interval '91 seconds' where id=$1",[job]);
 assert.equal((await pick()).reference,job,'Only a selection was lost; no provider claim was made');
 await assert.rejects(pick(null,true),/Finite test scope/);
 await assert.rejects(pick(null,false,['bad']),/Invalid recipient scope/);
});

test('automatic selection advances acknowledgment to actual reply generation to dispatch with one test turn maximum',async t=>{
 const {q,rpc,ack,inbound,pick}=await setup(t);
 assert.equal((await pick(job,true,[phone])).action,'ack');await ack();
 const first=await inbound();await rpc('enqueue_retell_api_turn',[job,first]);
 assert.equal((await pick(job,true,[phone])).action,'generate');
 assert.equal((await pick(job,true,[phone])).selected,false);
 await rpc('claim_retell_api_turn',[first,'agent_test',2]);
 assert.equal((await pick(job,true,[phone])).selected,false,'Claimed generation is never selected for replay');
 await rpc('bind_retell_api_session',[first,'chat_auto']);
 await rpc('save_retell_api_generation',[first,JSON.stringify([{message_id:'m1',content:'Actual response'}])]);
 assert.equal((await pick(job,true,[phone])).action,'reply','Status transition clears selection-only lease');
 const claim=await rpc('claim_retell_app_reply',[first]);assert.equal(claim.claimed,true);
 assert.equal((await pick()).selected,false,'Submitting is never selected again');
 await q("update public.sms_events set status='delivered',raw_payload=raw_payload||jsonb_build_object('provider_sid',$2::text) where id=$1",[claim.message_id,'SM'+'b'.repeat(32)]);
 await rpc('sync_retell_app_outcome',[claim.message_id]);
 const second=await inbound();await rpc('enqueue_retell_api_turn',[job,second]);
 assert.equal((await pick(job,true,[phone])).selected,false,'Bounded acceptance does not respond to a second turn');
 assert.equal((await pick(null,false,[phone])).reference,second,'Verified production mode may continue genuine conversations');
});

test('expiry and review holds prevent automatic selections',async t=>{
 const {q,rpc,ack,inbound,pick}=await setup(t);await ack();const id=await inbound();await rpc('enqueue_retell_api_turn',[job,id]);
 await rpc('claim_retell_api_turn',[id,'agent_test',2]);
 await rpc('hold_retell_api_turn',[id,'creating_session','Uncertain creation']);
 assert.equal((await pick()).selected,false);
});

test('scheduler posts only to the fixed app endpoint, serializes HTTP work and leaves provider claims to workers',async t=>{
 const {q,tick,enable}=await setup(t);await enable();
 const first=await tick();assert.equal(first.status,'requested');
 assert.equal((await tick()).status,'in_flight');
 const requests=await q('select * from net.test_requests');assert.equal(requests.length,1);
 assert.equal(requests[0].url,'https://wholesale-automation.vercel.app/webhooks/_worker/retell-app/automatic');
 assert.deepEqual(requests[0].body,{});assert.equal(requests[0].timeout_milliseconds,60000);
 assert.equal((await q('select count(*)::int n from public.sms_events'))[0].n,0);
 await q("insert into net._http_response values($1,200,false,'{\"status\":\"processed\"}')",[first.request_id]);
 assert.equal((await tick()).status,'requested');
});

test('disabled, invalid, timed-out and failed worker receipts stop the scheduler without another HTTP request',async t=>{
 for(const response of [[200,false,'{"status":"disabled"}'],[200,false,'not-json'],[503,false,'{}'],[200,true,'{}']])await t.test(JSON.stringify(response),async sub=>{
  const {q,tick,enable}=await setup(sub);await enable();const first=await tick();
  await q('insert into net._http_response values($1,$2,$3,$4)',[first.request_id,...response]);
  assert.equal((await tick()).requested,false);
  assert.equal((await q('select enabled from private.retell_app_scheduler'))[0].enabled,false);
  assert.equal((await q('select count(*)::int n from net.test_requests'))[0].n,1);
  assert.ok((await q('select category from public.launch_monitor_findings()')).some(r=>r.category==='retell_app_scheduler'));
 });
});

test('missing HTTP completion stops instead of resubmitting an uncertain request',async t=>{
 const {q,tick,enable}=await setup(t);await enable();await tick();
 await q("update private.retell_app_scheduler set last_requested_at=now()-interval '91 seconds'");
 assert.equal((await tick()).status,'worker_http_unconfirmed');
 assert.equal((await q('select count(*)::int n from net.test_requests'))[0].n,1);
});

test('native scheduler, missing credential and contact window gates cause no HTTP request',async t=>{
 const {q,tick,enable}=await setup(t);await enable();
 await q('update private.retell_sms_scheduler set enabled=true');
 assert.equal((await tick()).status,'native_scheduler_enabled');
 await q('update private.retell_sms_scheduler set enabled=false');
 await q('delete from vault.decrypted_secrets');
 assert.equal((await tick()).status,'missing_worker_credential');
 const hour=(await q("select extract(hour from now() at time zone 'America/Chicago')::int current_hour"))[0].current_hour;
 await q('update private.retell_app_scheduler set start_hour=$1,end_hour=$2',[hour===0?1:0,hour===0?2:1]);
 assert.equal((await tick()).status,'outside_contact_hours');
 assert.equal((await q('select count(*)::int n from net.test_requests'))[0].n,0);
});

test('a selection-only hold cannot starve another inquiry and expired inquiries are not selected',async t=>{
 const {q,pick}=await setup(t);const other=crypto.randomUUID();
 await q('insert into public.leads(id) values($1)',[other]);await q('insert into public.lead_form_submissions(id) values($1)',[other]);
 await q(`insert into public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at,delivery_transport,delivery_body,delivery_sender)
  values($1,$1,$1,'+12145550195',now(),now()+interval '10 minutes','app_twilio','Synthetic inquiry','+14695550100')`,[other]);
 assert.equal((await pick()).reference,job);
 assert.equal((await pick()).reference,other);
 await q("update public.retell_form_sms_jobs set auto_selected_at=null,expires_at=now()-interval '1 second' where id=$1",[job]);
 assert.equal((await pick()).selected,false);
});
