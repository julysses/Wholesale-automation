import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import postgres from '../node_modules/postgres/src/index.js';
import {fixture,job,phone} from '../tests/retell-app-transport-fixture.mjs';
const url=process.env.SMS_TEST_ADMIN_URL;
if(!url || new URL(url).hostname!=='127.0.0.1' || !new URL(url).pathname.endsWith('/wholesale_sms_test'))throw Error('Disposable localhost required');
const sql=postgres(url,{max:10,types:{json:{to:114,from:[114,3802],serialize:value=>typeof value==='string'?value:JSON.stringify(value),parse:JSON.parse}},onnotice:()=>{}});
const db={exec:async t=>{await sql.unsafe(t).simple();},query:async(t,a=[])=>({rows:[...await sql.unsafe(t,a)]})};
const read=n=>fs.readFileSync(new URL('../../frontend/supabase/migrations/'+n,import.meta.url),'utf8');
const hash=s=>createHash('sha256').update(s).digest('hex');
let cases=0;
try {
 const {q,rpc,ack,inbound}=await fixture(db);
 await db.exec(`create schema private; create schema net;
 create table net._http_response(id bigint,status_code int,timed_out boolean,created timestamptz,content text);
 create table public.webhook_jobs(id uuid primary key,source text,status text,payload jsonb);`);
 await db.exec(read('20261019213545_retell_empty_session_reconciliation.sql'));
 await db.exec(read('20261023214643_retell_verified_generation_recovery.sql'));
 await db.exec(read('20261017013643_retell_app_twilio_outbox.sql'));
 await ack(); await q("update public.sms_events set status='delivered' where id=$1",[job]);
 const turn=await inbound();const enqueued=await rpc('enqueue_retell_api_turn',[job,turn]);assert.equal(enqueued.queued,true,JSON.stringify(enqueued));
 await rpc('claim_retell_api_turn',[turn,'agent_test',2]);await rpc('bind_retell_api_session',[turn,'chat_test']);
 await rpc('hold_retell_api_turn',[turn,'generating','Provider outcome held']);
 const text=(await q('select recipient_text from public.retell_api_turns where id=$1',[turn]))[0].recipient_text;
 const content='What time works?';const event=crypto.randomUUID();
 const proof={status:'inspected',session_id:job,chat_id:'chat_test',dispatch_authorized:false,
 checks:{chat_id:true,chat_type:true,agent_id:true,metadata:true,ongoing:true,pinned_version_valid:true},
 first_turn_proof:{user_message_id:'u1',recipient_sha256:hash(text),message_id:'a1',content_sha256:hash(content)}};
 const payload={event:'transcript_updated',chat:{chat_id:'chat_test',chat_type:'api_chat',agent_id:'agent_test',agent_version:2,
 metadata:{operation_id:job,lead_id:job,transport:'wholesaleos_twilio'}},
 transcript_with_tool_calls:[{role:'user',message_id:'u1',content:text},{role:'agent',message_id:'a1',content}]};
 await q('insert into net._http_response values(1,200,false,now(),$1)',[JSON.stringify(proof)]);
 await q("insert into public.webhook_jobs values($1,'retell_api_chat','done',$2)",[event,JSON.stringify(payload)]);
 const recover='select private.reconcile_retell_generation($1,1,$2,\'Owner-authorized exact first response recovery\') result';
 const alterations=[
 ['stale proof',"update net._http_response set created=now()-interval '6 minutes'"],
 ['wrong live fingerprint',"update net._http_response set content=jsonb_set(content::jsonb,'{first_turn_proof,content_sha256}','\"wrong\"')::text"],
 ['wrong event identity',"update public.webhook_jobs set payload=jsonb_set(payload,'{chat,chat_id}','\"chat_other\"')"],
 ['wrong input',"update public.webhook_jobs set payload=jsonb_set(payload,'{transcript_with_tool_calls,0,content}','\"Other input\"')"],
 ['tool action',"update public.webhook_jobs set payload=jsonb_set(payload,'{transcript_with_tool_calls,1,role}','\"tool_call_invocation\"')"],
 ['suppression',`insert into public.test_suppression values('${phone}')`],
 ['DNC',`update public.leads set dnc=true where id='${job}'`],
 ['outbound exists',`insert into public.sms_events(id,raw_payload) values(gen_random_uuid(),jsonb_build_object('api_turn_id','${turn}'))`],
 ];
 for(const [name,change] of alterations){
  const c=await sql.reserve();try{
   await c`begin`; await c.unsafe(change);await assert.rejects(c.unsafe(recover,[turn,event]));cases++;
   console.log(name+': blocked');
  }finally{await c`rollback`;c.release();}
 }
 for(const role of ['anon','authenticated','service_role']){
  const [r]=await q("select has_function_privilege($1,'private.reconcile_retell_generation(uuid,bigint,uuid,text)','EXECUTE') f,has_table_privilege($1,'private.retell_generation_reconciliations','INSERT') t",[role]);
  assert.equal(r.f,false);assert.equal(r.t,false);
 }cases++;
 const recovered=(await q(recover,[turn,event]))[0].result;assert.equal(recovered.reconciled,true);
 assert.equal(recovered.dispatch_authorized,false);
 assert.equal((await q('select count(*)::int n from public.sms_events'))[0].n,2);
 const [saved]=await q('select generated_messages,recipient_text,expires_at from public.retell_api_turns where id=$1',[turn]);
 assert.equal(saved.generated_messages[0].content,content);assert.equal(saved.recipient_text,text);
 await assert.rejects(q(recover,[turn,event]));cases++;
 const claims=await Promise.all(Array.from({length:8},()=>rpc('claim_retell_app_reply',[turn])));
 assert.equal(claims.filter(x=>x.claimed===true).length,1);cases++;
 await q("update public.retell_api_turns set status='review' where id=$1",[turn]);
 await q("update public.retell_api_sessions set status='review' where id=$1",[job]);
 await assert.rejects(q("update public.retell_api_sessions set status='ready' where id=$1",[job]));cases++;
 console.log(JSON.stringify({cases,provider_calls:0,concurrent_claimants:8,winners:1}));
}finally{await sql.end();}
