/** Disposable localhost database only; no provider calls or production access. */
import assert from 'node:assert/strict';
import postgres from '../node_modules/postgres/src/index.js';
import {fixture,job,phone} from '../tests/retell-app-transport-fixture.mjs';
const url=process.env.SMS_TEST_ADMIN_URL;
if(!url || new URL(url).hostname!=='127.0.0.1' || !new URL(url).pathname.endsWith('/wholesale_sms_test'))throw Error('Disposable localhost database required');
const sql=postgres(url,{max:12,types:{json:{to:114,from:[114,3802],serialize:value=>typeof value==='string'?value:JSON.stringify(value),parse:JSON.parse}},connection:{statement_timeout:5000},onnotice:()=>{}});
const db={exec:async text=>{await sql.unsafe(text).simple();},query:async(text,args=[])=>({rows:[...await sql.unsafe(text,args)]})};
try {
 const {q,rpc,ack,inbound}=await fixture(db);
 const winners=await Promise.all(Array.from({length:8},()=>q('select id from public.claim_retell_app_ack($1)',[job])));
 assert.equal(winners.filter(rows=>rows.length).length,1);
 assert.equal((await q('select count(*)::int n from public.sms_events where id=$1',[job]))[0].n,1);
 const others=await Promise.all(Array.from({length:8},()=>rpc('claim_twilio_sms',[crypto.randomUUID(),job,phone,'Concurrent duplicate'])));
 assert.ok(others.every(r=>r.claimed===false));
 await ack();const first=await inbound(),second=await inbound();
 await q("update public.sms_events set created_at=created_at-interval '1 second' where id=$1",[first]);
 const inserts=await Promise.all(Array.from({length:8},()=>rpc('enqueue_retell_api_turn',[job,first])));
 assert.equal(inserts.filter(r=>r.queued).length,1,JSON.stringify(inserts));await rpc('enqueue_retell_api_turn',[job,second]);
 const attempts=await Promise.all(Array.from({length:8},(_,i)=>rpc('claim_retell_api_turn',[i%2?first:second,'agent_test',2])));
 assert.equal(attempts.filter(r=>r.claimed).length,1);
 assert.equal(attempts.find(r=>r.claimed).turn_id,first);
 const bindings=await Promise.all(Array.from({length:8},()=>rpc('bind_retell_api_session',[first,'chat_concurrent'])));
 assert.equal(bindings.filter(r=>r.replayed===false).length,1);
 const messages=[{message_id:'m1',content:'Synthetic saved response'}];
 const saves=await Promise.all(Array.from({length:8},()=>rpc('save_retell_api_generation',[first,JSON.stringify(messages)])));
 assert.equal(saves.filter(r=>r.replayed===false).length,1);
 assert.equal((await rpc('claim_retell_api_turn',[second,'agent_test',2])).claimed,false);
 const holds=await Promise.all(Array.from({length:8},()=>rpc('hold_retell_api_turn',[first,'generated','Synthetic explicit review'])));
 assert.equal(holds.filter(r=>r.held).length,1);
 assert.equal((await rpc('claim_retell_api_turn',[first,'agent_test',2])).claimed,false);
 assert.equal((await rpc('claim_retell_api_turn',[second,'agent_test',2])).claimed,false);
 assert.equal((await q('select count(*)::int n from public.sms_events where direction=\'outbound\''))[0].n,1);
 console.log(JSON.stringify({postgres_concurrency:'passed',workers:8,initial_claims:1,turn_claims:1,session_bindings:1,generation_receipts:1,holds:1,provider_calls:0}));
} finally {await sql.end();}
