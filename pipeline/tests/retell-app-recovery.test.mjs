import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
import {fixture,job,native} from './retell-app-transport-fixture.mjs';
import {installRecovery} from './retell-app-recovery-fixture.mjs';
async function setup(t){
 const db=new PGlite();t.after(()=>db.close());const f=await fixture(db);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261017013643_retell_app_twilio_outbox.sql',import.meta.url),'utf8'));
 await installRecovery(db);
 const turn=async(stage='queued')=>{
  await f.ack();const id=await f.inbound();assert.equal((await f.rpc('enqueue_retell_api_turn',[job,id])).queued,true);
  if(stage!=='queued')await f.rpc('claim_retell_api_turn',[id,'agent_test',2]);
  if(['generating','generated','submitting'].includes(stage))await f.rpc('bind_retell_api_session',[id,'chat_recovery']);
  if(['generated','submitting'].includes(stage))await f.rpc('save_retell_api_generation',[id,JSON.stringify([{message_id:'m1',content:'Synthetic response'}])]);
  if(stage==='submitting')await f.rpc('claim_retell_app_reply',[id]);
  return id;
 };
 return {...f,turn};
}

test('ack recovery is exact, respects fresh work, holds uncertainty, and never rewrites receipt',async t=>{
 const {q,rpc}=await setup(t);
 await q('select id from public.claim_retell_app_ack($1)',[job]);
 assert.equal((await rpc('recover_retell_app_ack',[job])).recovered,false);
 assert.equal((await rpc('recover_retell_app_ack',[native])).reason,'unrelated_job');
 await q("update public.retell_form_sms_jobs set claimed_at=now()-interval '6 minutes' where id=$1",[job]);
 const before=await q('select * from public.sms_events');
 assert.equal((await rpc('recover_retell_app_ack',[job])).status,'review');
 assert.deepEqual(await q('select * from public.sms_events'),before);
 assert.equal((await rpc('recover_retell_app_ack',[job])).recovered,false);
 assert.equal((await q('select id from public.claim_retell_app_ack($1)',[job])).length,0);
});

test('known carrier delivery repairs stale ack without manufacturing another SMS',async t=>{
 const {q,rpc}=await setup(t);
 await q('select id from public.claim_retell_app_ack($1)',[job]);
 await q("update public.retell_form_sms_jobs set claimed_at=now()-interval '6 minutes' where id=$1",[job]);
 await q("update public.sms_events set status='delivered',raw_payload=raw_payload||jsonb_build_object('provider_sid',$2::text) where id=$1",[job,'SM'+'c'.repeat(32)]);
 const before=await q('select * from public.sms_events');
 assert.equal((await rpc('recover_retell_app_ack',[job])).status,'accepted');
 assert.deepEqual(await q('select * from public.sms_events'),before);
});

test('stale creation and completion remain held and appear in operator monitoring',async t=>{
 for(const stage of ['creating_session','generating'])await t.test(stage,async sub=>{
  const {q,rpc,turn}=await setup(sub);const id=await turn(stage);
  assert.equal((await rpc('recover_retell_api_turn',[id])).recovered,false);
  await q("update public.retell_api_turns set claimed_at=now()-interval '6 minutes' where id=$1",[id]);
  assert.ok((await q('select * from public.launch_monitor_findings()')).some(r=>r.reference===id));
  assert.equal((await rpc('recover_retell_api_turn',[id])).status,'review');
  assert.equal((await rpc('recover_retell_api_turn',[id])).recovered,false);
  assert.equal((await rpc('claim_retell_api_turn',[id,'agent_test',2])).claimed,false);
  assert.equal((await q('select status from public.retell_api_sessions where id=$1',[job]))[0].status,'review');
  const count=(await q('select count(*)::int n from public.sms_events'))[0].n;
  assert.equal((await rpc('scan_launch_monitor',[])).created,2);
  assert.equal((await rpc('scan_launch_monitor',[])).created,0);
  assert.equal((await q('select count(*)::int n from public.sms_events'))[0].n,count);
  const tasks=await q('select * from public.tasks');assert.equal(tasks.length,2);
  assert.ok(tasks.every(x=>x.assigned_to==='00000000-0000-4000-8000-000000000777'));
 });
});

test('reply recovery ages the dispatch receipt rather than generation claim and preserves late delivery',async t=>{
 const {q,rpc,turn}=await setup(t);const id=await turn('submitting');
 await q("update public.retell_api_turns set claimed_at=now()-interval '6 minutes' where id=$1",[id]);
 assert.equal((await rpc('recover_retell_api_turn',[id])).reason,'dispatch_still_fresh');
 const message=(await q('select outbound_id from public.retell_api_turns where id=$1',[id]))[0].outbound_id;
 await q("update public.sms_events set created_at=now()-interval '6 minutes',status='delivered',raw_payload=raw_payload||jsonb_build_object('provider_sid',$2::text) where id=$1",[message,'SM'+'d'.repeat(32)]);
 const before=await q('select * from public.sms_events order by id');
 assert.equal((await rpc('recover_retell_api_turn',[id])).status,'accepted');
 assert.deepEqual(await q('select * from public.sms_events order by id'),before);
 assert.equal((await q('select status from public.retell_api_sessions where id=$1',[job]))[0].status,'ready');
});

test('unconfirmed dispatch is held without losing exact carrier evidence or creating another outbox',async t=>{
 const {q,rpc,turn}=await setup(t);const id=await turn('submitting');
 const message=(await q('select outbound_id from public.retell_api_turns where id=$1',[id]))[0].outbound_id;
 await q("update public.sms_events set created_at=now()-interval '6 minutes' where id=$1",[message]);
 const before=await q('select * from public.sms_events order by id');
 assert.equal((await rpc('recover_retell_api_turn',[id])).status,'review');
 assert.equal((await rpc('claim_retell_app_reply',[id])).claimed,false);
 assert.deepEqual(await q('select * from public.sms_events order by id'),before);
 // A later carrier receipt remains useful, but cannot reopen a held operation.
 await q("update public.sms_events set status='delivered',raw_payload=raw_payload||jsonb_build_object('provider_sid',$2::text) where id=$1",[message,'SM'+'e'.repeat(32)]);
 await rpc('sync_retell_app_outcome',[message]);
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[id]))[0].status,'review');
});

test('expired unprocessed input stops; generated-but-unsent output holds the conversation',async t=>{
 for(const stage of ['queued','generated'])await t.test(stage,async sub=>{
  const {q,rpc,turn,inbound}=await setup(sub);const first=await turn('generated');
  // Insert a synthetic historical expired row. Production triggers forbid
  // changing a saved turn deadline, so tests do not bypass that protection.
  await q("update public.retell_api_turns set status='stopped' where id=$1",[first]);
  const id=await inbound();
  await q(`insert into public.retell_api_turns(id,session_id,inbound_sid,recipient_text,status,created_at,expires_at,generated_messages)
   values($1,$2,$3,'Historical input',$4,now()-interval '20 minutes',now()-interval '5 minutes',$5)`,
   [id,job,'SM'+id.replaceAll('-',''),stage,stage==='generated'?JSON.stringify([{message_id:'old',content:'Unsent reply'}]):null]);
  assert.equal((await rpc('recover_retell_api_turn',[id])).status,stage==='queued'?'stopped':'review');
  assert.equal((await rpc('claim_retell_api_turn',[id,'agent_test',2])).claimed,false);
  assert.equal((await q("select count(*)::int n from public.sms_events where direction='outbound'"))[0].n,1);
 });
});

test('monitor and recovery are server-only invoker functions with empty search paths',async t=>{
 const {q}=await setup(t);
 for(const fn of ['recover_retell_app_ack(uuid)','recover_retell_api_turn(uuid)','retell_app_monitor_findings()']){
  for(const role of ['anon','authenticated'])assert.equal((await q("select has_function_privilege($1,$2,'EXECUTE') allowed",[role,'public.'+fn]))[0].allowed,false);
  const meta=(await q('select prosecdef,proconfig from pg_proc where oid=$1::regprocedure',['public.'+fn]))[0];
  assert.equal(meta.prosecdef,false);assert.ok(meta.proconfig.includes('search_path=""'));
 }
});

test('late acknowledgment failure holds a pending session before any generation claim',async t=>{
 const {q,rpc,turn}=await setup(t);const id=await turn('queued');
 await q("update public.sms_events set status='undelivered' where id=$1",[job]);
 await rpc('sync_retell_app_outcome',[job]);
 assert.equal((await q('select status from public.retell_api_sessions where id=$1',[job]))[0].status,'review');
 assert.equal((await rpc('claim_retell_api_turn',[id,'agent_test',2])).claimed,false);
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[id]))[0].status,'queued');
});
