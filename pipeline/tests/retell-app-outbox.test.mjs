import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
import {fixture,job,phone} from './retell-app-transport-fixture.mjs';
async function setup(t){
 const db=new PGlite();t.after(()=>db.close());const f=await fixture(db);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261017013643_retell_app_twilio_outbox.sql',import.meta.url),'utf8'));
 const generate=async()=>{
  const id=await f.inbound();await f.rpc('enqueue_retell_api_turn',[job,id]);
  const claim=await f.rpc('claim_retell_api_turn',[id,'agent_test',2]);assert.equal(claim.claimed,true);
  if(claim.create_session)await f.rpc('bind_retell_api_session',[id,'chat_outbox']);
  await f.rpc('save_retell_api_generation',[id,JSON.stringify([{message_id:'m_'+id,content:'First line.'},{message_id:'second_'+id,content:'Second line.'}])]);
  return id;
 };
 const receipt=async(id,status)=>{await f.q("update public.sms_events set status=$2,raw_payload=raw_payload||jsonb_build_object('provider_sid',$3::text) where id=$1",[id,status,'SM'+id.replaceAll('-','')]);return f.rpc('sync_retell_app_outcome',[id]);};
 return {...f,generate,receipt};
}

test('reply outbox uses exact generated content, no duplicate claim, and exact verified carrier outcome',async t=>{
 const {q,rpc,ack,generate,receipt}=await setup(t);await ack();const turn=await generate();
 const claim=await rpc('claim_retell_app_reply',[turn]);assert.equal(claim.claimed,true);assert.equal(claim.body,'First line.\nSecond line.');
 assert.equal((await rpc('claim_retell_app_reply',[turn])).claimed,false);
 const e=(await q('select * from public.sms_events where id=$1',[claim.message_id]))[0];
 assert.equal(e.provider,'twilio');assert.equal(e.status,'submitting');assert.equal(e.raw_payload.api_turn_id,turn);assert.equal(e.body,claim.body);
 assert.equal((await receipt(claim.message_id,'delivered')).carrier_status,'delivered');
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[turn]))[0].status,'accepted');
 assert.equal((await q('select status from public.retell_api_sessions'))[0].status,'ready');
 // Another actual inbound reply may receive one response despite initial
 // prospecting cooldown; it must still win its own exact carrier-bound claim.
 const next=await generate();assert.equal((await rpc('claim_retell_app_reply',[next])).claimed,true);
 assert.equal((await q('select count(*)::int n from public.sms_events where direction=\'outbound\''))[0].n,3);
});

test('late failure holds conversation; a later success never silently reopens it',async t=>{
 const {q,rpc,ack,generate,receipt}=await setup(t);await ack();const turn=await generate();const c=await rpc('claim_retell_app_reply',[turn]);
 await receipt(c.message_id,'accepted');await receipt(c.message_id,'undelivered');
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[turn]))[0].status,'review');
 assert.equal((await q('select status from public.retell_api_sessions'))[0].status,'review');
 await receipt(c.message_id,'delivered');
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[turn]))[0].status,'review');
 assert.equal((await rpc('claim_retell_app_reply',[turn])).claimed,false);
});

test('changed suppression and carrier evidence prevent dispatch after generation',async t=>{
 for(const condition of ['suppressed','input','control','unresolved_sms','unresolved_call']){
  await t.test(condition,async sub=>{
   const {q,rpc,ack,generate}=await setup(sub);await ack();const turn=await generate();
   if(condition==='suppressed')await q('insert into public.test_suppression values($1)',[phone]);
   if(condition==='input')await q("update public.sms_events set raw_payload=raw_payload||'{\"Body\":\"changed\"}'::jsonb where id=$1",[turn]);
   if(condition==='control')await q("update public.sms_events set raw_payload=raw_payload||'{\"OptOutType\":\"STOP\"}'::jsonb where id=$1",[turn]);
   if(condition==='unresolved_sms')await q("insert into public.sms_events(id,provider,direction,phone_number,status) values(gen_random_uuid(),'twilio','outbound',$1,'unknown')",[phone]);
   if(condition==='unresolved_call')await q("insert into public.retell_call_requests(id,phone_number,status,created_at) values(gen_random_uuid(),$1,'submitting',now())",[phone]);
   assert.equal((await rpc('claim_retell_app_reply',[turn])).claimed,false);
   assert.equal((await q('select outbound_id from public.retell_api_turns where id=$1',[turn]))[0].outbound_id,null);
  });
 }
});

test('acknowledgment sync preserves receipt and requires exact app mapping',async t=>{
 const {q,rpc}=await setup(t);await q('select id from public.claim_retell_app_ack($1)',[job]);
 assert.equal((await rpc('sync_retell_app_outcome',[job])).carrier_accepted,false);
 await q("update public.sms_events set status='delivered',raw_payload=raw_payload||jsonb_build_object('provider_sid',$2::text) where id=$1",[job,'SM'+'c'.repeat(32)]);
 const before=await q('select * from public.sms_events where id=$1',[job]);
 await rpc('sync_retell_app_outcome',[job]);await rpc('sync_retell_app_outcome',[job]);
 assert.deepEqual(await q('select * from public.sms_events where id=$1',[job]),before);
 assert.equal((await q('select status from public.retell_form_sms_jobs where id=$1',[job]))[0].status,'accepted');
 await q("update public.sms_events set raw_payload=raw_payload||'{\"sender_number\":\"+12145550100\"}'::jsonb where id=$1",[job]);
 await assert.rejects(rpc('sync_retell_app_outcome',[job]),/identity mismatch/);
 const unrelated=crypto.randomUUID();await q("insert into public.sms_events(id,provider,direction,status) values($1,'twilio','outbound','sent')",[unrelated]);
 assert.equal((await rpc('sync_retell_app_outcome',[unrelated])).reason,'unrelated_receipt');
 for(const fn of ['claim_retell_app_reply(uuid)','sync_retell_app_outcome(uuid)'])for(const role of ['anon','authenticated'])assert.equal((await q("select has_function_privilege($1,$2,'EXECUTE') allowed",[role,'public.'+fn]))[0].allowed,false);
});

test('operator hold preserves a verified delivery receipt and prevents later turns',async t=>{
 const {q,rpc,ack,generate,receipt}=await setup(t);await ack();const turn=await generate();const c=await rpc('claim_retell_app_reply',[turn]);
 await receipt(c.message_id,'delivered');const before=await q('select * from public.sms_events where id=$1',[c.message_id]);
 assert.equal((await rpc('review_retell_app_dispatch',[c.message_id,'Conflicting API response; retain callback evidence'])).held,true);
 assert.deepEqual(await q('select * from public.sms_events where id=$1',[c.message_id]),before);
 assert.equal((await q('select status from public.retell_api_sessions'))[0].status,'review');
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[turn]))[0].status,'review');
 await rpc('sync_retell_app_outcome',[c.message_id]);
 assert.equal((await q('select status from public.retell_api_turns where id=$1',[turn]))[0].status,'review');
});
