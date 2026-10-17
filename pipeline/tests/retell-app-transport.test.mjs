import test from 'node:test';
import assert from 'node:assert/strict';
import {PGlite} from '@electric-sql/pglite';
import {fixture,job,native,phone,sender,sid} from './retell-app-transport-fixture.mjs';
async function setup(t){
 const db=new PGlite();t.after(()=>db.close());
 return fixture(db);
}

test('transport ownership is immutable and native/app/direct-Twilio claims cannot duplicate each other',async t=>{
 const {q,rpc}=await setup(t);
 assert.deepEqual(await q("select delivery_transport,delivery_body,delivery_sender,status,chat_id,reason from public.retell_form_sms_jobs where id='00000000-0000-4000-8000-000000000999'"),
  [{delivery_transport:'retell_native',delivery_body:null,delivery_sender:null,status:'accepted',chat_id:'chat_legacy',reason:'Original native provider receipt'}]);
 for(const patch of ["delivery_transport='retell_native',delivery_body=null,delivery_sender=null","phone_number='+12145550199'","delivery_body='Changed body'","delivery_sender='+14695550101'"]){
  await assert.rejects(q(`update public.retell_form_sms_jobs set ${patch} where id=$1`,[job]),/immutable/);
 }
 assert.deepEqual(await q('select id from public.claim_retell_form_sms_matching(3,$1)',[job]),[]);
 assert.deepEqual(await q('select id from public.claim_retell_app_ack($1)',[native]),[]);
 assert.deepEqual(await q('select id from public.claim_retell_app_ack($1)',[job]),[{id:job}]);
 assert.deepEqual(await q('select id from public.claim_retell_app_ack($1)',[job]),[]);
 assert.deepEqual(await q('select provider,status,body from public.sms_events where id=$1',[job]),[{provider:'twilio',status:'submitting',body:'Thanks for your property inquiry. Reply STOP to opt out.'}]);
 assert.equal((await rpc('claim_twilio_sms',[crypto.randomUUID(),job,phone,'Duplicate'])).claimed,false);
 assert.deepEqual(await q('select id from public.claim_retell_form_sms(3)'),[{id:native}]);
 assert.equal((await q('select provider from public.sms_events where id=$1',[native]))[0].provider,'retell');
 await assert.rejects(q('select * from public.claim_retell_app_ack(null)'),/Exact inquiry/);
});

test('only matching committed carrier replies enqueue once; spoofed bindings and controls never create a turn',async t=>{
 const {q,rpc,ack,inbound}=await setup(t);await ack();
 for(const patch of [{From:'+12145550199'},{To:'+14695550199'},{MessageSid:'bad'},{crm_opt_out:true},{crm_opt_out:null},
   {Body:'STOP'},{Body:'help!'},{Body:'START'},{Body:'Normal words',OptOutType:'STOP'},{Body:'x'.repeat(1601)}]){
  const id=await inbound(crypto.randomUUID(),patch);assert.equal((await rpc('enqueue_retell_api_turn',[job,id])).queued,false,JSON.stringify(patch));
 }
 for(const alteration of ["lead_id=null","provider='retell'","direction='outbound'","status='unknown'","opt_out=true","body='changed independently'","created_at=now()-interval '20 minutes'","created_at=now()+interval '1 minute'"]){
  const id=await inbound();await q(`update public.sms_events set ${alteration} where id=$1`,[id]);
  assert.equal((await rpc('enqueue_retell_api_turn',[job,id])).queued,false,alteration);
 }
 assert.equal((await q('select count(*)::int n from public.retell_api_turns'))[0].n,0);
 const event=await inbound();assert.equal((await rpc('enqueue_retell_api_turn',[job,event])).queued,true);
 assert.equal((await rpc('enqueue_retell_api_turn',[job,event])).reason,'existing_turn');
 const row=(await q('select recipient_text,expires_at-created_at as window from public.retell_api_turns where id=$1',[event]))[0];
 assert.equal(row.recipient_text,'  Can Julio call tomorrow?\nThanks. ');
 assert.equal((await q("select expires_at-created_at=interval '15 minutes' correct from public.retell_api_turns where id=$1",[event]))[0].correct,true);
 const duplicate=await inbound(crypto.randomUUID(),{MessageSid:'SM'+event.replaceAll('-','')});
 await assert.rejects(rpc('enqueue_retell_api_turn',[job,duplicate]),/identity conflict/);
});

test('suppression and unconfirmed initial delivery prevent conversation creation',async t=>{
 const {q,rpc,ack,inbound}=await setup(t);await ack();const event=await inbound();
 await q("insert into public.test_suppression values($1)",[phone]);
 assert.equal((await rpc('enqueue_retell_api_turn',[job,event])).queued,false);
 await q('delete from public.test_suppression');
 for(const status of ['unknown','submitting','undelivered','failed']){
  await q('update public.sms_events set status=$2 where id=$1',[job,status]);
  assert.equal((await rpc('enqueue_retell_api_turn',[job,event])).queued,false);
 }
 assert.equal((await q('select count(*)::int n from public.retell_api_sessions'))[0].n,0);
});

test('one-shot session and generation claims serialize turns, bind receipts and preserve exact output',async t=>{
 const {q,rpc,ack,inbound}=await setup(t);await ack();const first=await inbound(),second=await inbound();
 await q("update public.sms_events set created_at=created_at-interval '1 second' where id=$1",[first]);
 for(const id of [first,second])assert.equal((await rpc('enqueue_retell_api_turn',[job,id])).queued,true);
 assert.equal((await rpc('claim_retell_api_turn',[second,'agent_test',2])).reason,'previous_turn_unfinished');
 const claimed=await rpc('claim_retell_api_turn',[first,'agent_test',2]);assert.equal(claimed.claimed,true);assert.equal(claimed.create_session,true);
 assert.equal(claimed.recipient_text,'  Can Julio call tomorrow?\nThanks. ');assert.equal(claimed.session_id,job);
 assert.equal((await rpc('claim_retell_api_turn',[first,'agent_test',2])).claimed,false);
 assert.equal((await rpc('claim_retell_api_turn',[second,'agent_test',2])).claimed,false);
 assert.equal((await rpc('bind_retell_api_session',[first,'chat_synthetic'])).bound,true);
 assert.equal((await rpc('bind_retell_api_session',[first,'chat_synthetic'])).replayed,true);
 await assert.rejects(rpc('bind_retell_api_session',[first,'chat_other']),/conflict/);
 const messages=[{message_id:'m1',content:' First response. '},{message_id:'m2',content:'Second line.'}];
 assert.equal((await rpc('save_retell_api_generation',[first,JSON.stringify(messages)])).dispatch_authorized,false);
 assert.equal((await rpc('save_retell_api_generation',[first,JSON.stringify(messages)])).replayed,true);
 await assert.rejects(rpc('save_retell_api_generation',[first,JSON.stringify([{message_id:'m1',content:'Changed'}])]),/conflict/);
 assert.equal((await rpc('claim_retell_api_turn',[second,'agent_test',2])).claimed,false,'Generated but undispatched turn still blocks');
 assert.equal((await q('select count(*)::int n from public.sms_events where direction=\'outbound\''))[0].n,1,'Generation never inserts an SMS');
 // Later dispatch will own this transition; this fixture proves queue ordering only.
 await q("update public.retell_api_turns set status='submitting' where id=$1",[first]);
 await q("update public.retell_api_turns set status='accepted' where id=$1",[first]);
 assert.equal((await rpc('claim_retell_api_turn',[second,'agent_other',2])).reason,'session_release_mismatch');
 const next=await rpc('claim_retell_api_turn',[second,'agent_test',2]);assert.equal(next.claimed,true);assert.equal(next.create_session,false);assert.equal(next.chat_id,'chat_synthetic');
 for(const bad of [[],[{message_id:'m1',content:'a'},{message_id:'m1',content:'b'}],[{message_id:'m1',content:'a',role:'agent'}],[{message_id:'m1',content:'x'.repeat(1601)}],[{content:'no id'}]])await assert.rejects(rpc('save_retell_api_generation',[second,JSON.stringify(bad)]));
});

test('expired and suppressed queued turns cannot acquire provider work; browser roles have no access',async t=>{
 const {db,q,rpc,ack,inbound}=await setup(t);await ack();const event=await inbound();await rpc('enqueue_retell_api_turn',[job,event]);
 await q('insert into public.test_suppression values($1)',[phone]);
 assert.equal((await rpc('claim_retell_api_turn',[event,'agent_test',2])).reason,'expired_or_suppressed');
 assert.equal((await q('select status from public.retell_api_turns'))[0].status,'stopped');
 for(const fn of ['claim_retell_form_sms_transport(integer,uuid,text)','claim_retell_app_ack(uuid)','enqueue_retell_api_turn(uuid,uuid)','claim_retell_api_turn(uuid,text,integer)','bind_retell_api_session(uuid,text)','save_retell_api_generation(uuid,jsonb)']){
  for(const role of ['anon','authenticated'])assert.equal((await q('select has_function_privilege($1,$2,\'EXECUTE\') allowed',[role,'public.'+fn]))[0].allowed,false);
  assert.equal((await q('select prosecdef from pg_proc where oid=$1::regprocedure',['public.'+fn]))[0].prosecdef,false);
 }
 await db.exec('set role authenticated');
 for(const table of ['retell_api_sessions','retell_api_turns'])await assert.rejects(q('select * from public.'+table),/permission denied/);
 await assert.rejects(rpc('claim_retell_api_turn',[event,'agent_test',2]),/permission denied/);
});


test('interrupted generation stays held without replay or mutation of carrier input',async t=>{
 const {q,rpc,ack,inbound}=await setup(t);await ack();const event=await inbound();await rpc('enqueue_retell_api_turn',[job,event]);
 await rpc('claim_retell_api_turn',[event,'agent_test',2]);
 for(const patch of ["status='queued'","recipient_text='fabricated'","expires_at=now()+interval '1 hour'","inbound_sid='SMbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'"]){
  await assert.rejects(q(`update public.retell_api_turns set ${patch} where id=$1`,[event]),/immutable/);
 }
 assert.equal((await rpc('hold_retell_api_turn',[event,'generating','Wrong expected phase'])).held,false);
 assert.equal((await rpc('hold_retell_api_turn',[event,'creating_session','Provider outcome uncertain'])).held,true);
 assert.equal((await rpc('claim_retell_api_turn',[event,'agent_test',2])).claimed,false);
 assert.equal((await q('select status from public.retell_api_sessions'))[0].status,'review');
 await assert.rejects(q("update public.retell_api_sessions set status='pending' where id=$1",[job]),/immutable/);
 await assert.rejects(q("update public.retell_api_sessions set agent_version=3 where id=$1",[job]),/immutable/);
});

test('a queued reply that expires before claiming is stopped and never renewed',async t=>{
 const {q,rpc,ack,inbound}=await setup(t);await ack();const event=await inbound();await rpc('enqueue_retell_api_turn',[job,event]);
 // Advance fixture time before installing the immutable expiry guard again.
 await q('alter table public.retell_api_turns disable trigger protect_retell_api_turn');
 await q("update public.retell_api_turns set expires_at=now()-interval '1 second' where id=$1",[event]);
 await q('alter table public.retell_api_turns enable trigger protect_retell_api_turn');
 assert.equal((await rpc('claim_retell_api_turn',[event,'agent_test',2])).reason,'expired_or_suppressed');
 assert.equal((await rpc('claim_retell_api_turn',[event,'agent_test',2])).claimed,false);
 assert.equal((await q('select status from public.retell_api_turns'))[0].status,'stopped');
});

test('acknowledgment binding and reply timing cannot be inferred from phone alone',async t=>{
 const {q,rpc,ack,inbound}=await setup(t);await ack();const event=await inbound();
 const original=(await q('select raw_payload,body,created_at from public.sms_events where id=$1',[job]))[0];
 for(const patch of ["body='unrelated message'","created_at=now()+interval '1 second'","raw_payload=raw_payload-'provider_sid'","raw_payload=raw_payload-'form_job_id'","raw_payload=raw_payload||'{\"sender_number\":\"+14695550199\"}'::jsonb"]){
  await q(`update public.sms_events set ${patch} where id=$1`,[job]);
  assert.equal((await rpc('enqueue_retell_api_turn',[job,event])).queued,false,patch);
  await q('update public.sms_events set raw_payload=$2,body=$3,created_at=$4 where id=$1',[job,JSON.stringify(original.raw_payload),original.body,original.created_at]);
 }
 assert.equal((await rpc('enqueue_retell_api_turn',[job,event])).queued,true);
 for(const table of ['retell_api_sessions','retell_api_turns']){
  assert.equal((await q('select relrowsecurity from pg_class where oid=$1::regclass',['public.'+table]))[0].relrowsecurity,true);
  for(const role of ['anon','authenticated'])assert.equal((await q("select has_table_privilege($1,$2,'INSERT,UPDATE,DELETE,SELECT') allowed",[role,'public.'+table]))[0].allowed,false);
 }
});
