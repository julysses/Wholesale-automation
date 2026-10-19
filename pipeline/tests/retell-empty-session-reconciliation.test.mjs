import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
import {fixture,job} from './retell-app-transport-fixture.mjs';
const migration=fs.readFileSync(new URL('../../frontend/supabase/migrations/20261019213545_retell_empty_session_reconciliation.sql',import.meta.url),'utf8');
async function setup(t){
 const db=new PGlite();t.after(()=>db.close());const f=await fixture(db);
 await db.exec(`CREATE SCHEMA private; CREATE SCHEMA net;
 CREATE TABLE net._http_response(id bigint PRIMARY KEY,status_code int,timed_out boolean,content text,created timestamptz DEFAULT now());`);
 await db.exec(migration);await f.ack();const old=await f.inbound();await f.rpc('enqueue_retell_api_turn',[job,old]);
 await f.rpc('claim_retell_api_turn',[old,'agent_test',2]);await f.rpc('hold_retell_api_turn',[old,'creating_session','Original version validation failure']);
 const proof={status:'inspected',session_id:job,chat_id:'chat_test',dispatch_authorized:false,
 checks:{chat_id:true,chat_type:true,agent_id:true,metadata:true,ongoing:true,pinned_version_valid:true},
 history_shape:{transcript:{type:'str',empty:true},message_with_tool_calls:{type:'list',empty:true}}};
 const save=async()=>f.q('insert into net._http_response(id,status_code,timed_out,content) values(1,200,false,$1) on conflict(id) do update set content=excluded.content',[JSON.stringify(proof)]);
 const reconcile=()=>f.q("select private.reconcile_empty_retell_session($1,'chat_test',1,'Reviewed authenticated empty provider chat; never replay old input') result",[job]);
 await save();return {...f,old,proof,save,reconcile};
}
test('operator reconciles empty chat, stops historical input and preserves evidence; only fresh input can generate',async t=>{
 const f=await setup(t);const before=(await f.q('select * from public.retell_api_turns where id=$1',[f.old]))[0];
 assert.deepEqual((await f.reconcile())[0].result,{reconciled:true,stopped_turns:1,dispatch_authorized:false});
 const after=(await f.q('select * from public.retell_api_turns where id=$1',[f.old]))[0];
 for(const key of ['id','session_id','inbound_sid','recipient_text','created_at','expires_at','claimed_at','generated_messages','outbound_id'])assert.deepEqual(after[key],before[key]);
 assert.equal(after.status,'stopped');
 const audit=(await f.q('select * from private.retell_empty_session_reconciliations'))[0];
 assert.equal(audit.previous_turns[0].reason,'Original version validation failure');
 assert.equal((await f.rpc('claim_retell_api_turn',[f.old,'agent_test',2])).claimed,false);
 await assert.rejects(f.reconcile(),/unresolved/);
 const fresh=await f.inbound();assert.equal((await f.rpc('enqueue_retell_api_turn',[job,fresh])).queued,true);
 const claim=await f.rpc('claim_retell_api_turn',[fresh,'agent_test',2]);assert.equal(claim.claimed,true);assert.equal(claim.create_session,false);assert.equal(claim.chat_id,'chat_test');
 await f.rpc('hold_retell_api_turn',[fresh,'generating','Fresh uncertain operation']);
 await f.q("update public.retell_api_turns set status='stopped' where id=$1",[fresh]);
 await assert.rejects(f.q("update public.retell_api_sessions set status='ready' where id=$1",[job]),/immutable/);
});
test('bad identity/version, nonempty/absent history and malformed proof cannot unlock a session',async t=>{
 const f=await setup(t);const original=structuredClone(f.proof);
 for(const change of [p=>p.session_id=crypto.randomUUID(),p=>p.chat_id='other',p=>p.dispatch_authorized=true,
 p=>p.checks.agent_id=false,p=>p.checks.pinned_version_valid=false,p=>p.checks.metadata=false,
 p=>p.history_shape={},p=>p.history_shape.message_with_tool_calls.empty=false,
 p=>delete p.history_shape.message_with_tool_calls,p=>p.history_shape.transcript.empty=false]){
  Object.assign(f.proof,structuredClone(original));change(f.proof);await f.save();await assert.rejects(f.reconcile(),/evidence|empty/);
 }
 assert.equal((await f.q('select status from public.retell_api_sessions'))[0].status,'review');
 assert.equal((await f.q('select count(*)::int n from private.retell_empty_session_reconciliations'))[0].n,0);
});
test('stale or failed receipt and missing proof reject; application cannot create proof or invoke recovery',async t=>{
 const f=await setup(t);
 for(const patch of ["created=now()-interval '6 minutes'","status_code=500","timed_out=true"]){
  await f.q('update net._http_response set '+patch);await assert.rejects(f.reconcile(),/evidence/);
  await f.q('update net._http_response set created=now(),status_code=200,timed_out=false');
 }
 await assert.rejects(f.q("update public.retell_api_sessions set chat_id='chat_test',status='ready' where id=$1",[job]),/immutable/);
 for(const role of ['anon','authenticated','service_role']){
  assert.equal((await f.q("select has_function_privilege($1,'private.reconcile_empty_retell_session(uuid,text,bigint,text)','EXECUTE') allowed",[role]))[0].allowed,false);
  assert.equal((await f.q("select has_table_privilege($1,'private.retell_empty_session_reconciliations','INSERT,UPDATE,DELETE') allowed",[role]))[0].allowed,false);
 }
});

test('any saved generated output or carrier outbox evidence forbids empty-chat recovery',async t=>{
 const f=await setup(t);
 await f.q("update public.retell_api_turns set generated_messages='[{\"message_id\":\"saved\",\"content\":\"Evidence\"}]'::jsonb where id=$1",[f.old]);
 await assert.rejects(f.reconcile(),/unresolved/);
 assert.equal((await f.q('select status from public.retell_api_sessions'))[0].status,'review');
 assert.equal((await f.q('select count(*)::int n from private.retell_empty_session_reconciliations'))[0].n,0);
});
