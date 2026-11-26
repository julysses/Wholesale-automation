/** Real isolated PostgreSQL checks; no provider requests. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import postgres from '../node_modules/postgres/src/index.js';
import {fixture,job,phone,native} from '../tests/retell-app-transport-fixture.mjs';
const url=process.env.SMS_TEST_ADMIN_URL;
if(!url || new URL(url).hostname!=='127.0.0.1' || !new URL(url).pathname.endsWith('/wholesale_sms_test'))throw Error('Disposable localhost required');
const sql=postgres(url,{max:10,onnotice:()=>{}});
const db={exec:async text=>{await sql.unsafe(text).simple();},query:async(text,args=[])=>({rows:[...await sql.unsafe(text,args)]})};
let cases=0;
try {
 const {q}=await fixture(db);
 await db.exec('create schema private');
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261023213112_retell_owner_retest_authorization.sql',import.meta.url),'utf8'));
 // Prior terminal delivery records remain intact, and exceed the normal cap.
 await q(`insert into public.sms_events(id,provider,direction,phone_number,status,created_at)
  select gen_random_uuid(),'twilio','outbound',$1,'delivered',now()-interval '3 days' from generate_series(1,2)`,[phone]);
 const authorize=()=>q(`insert into private.retell_owner_retest_authorizations
  (job_id,lead_id,phone_number,operator_id,reason,expires_at,before_state)
  values($1,$1,$2,gen_random_uuid(),'Owner explicitly authorized one automated test',now()+interval '15 minutes','{}')`,[job,phone]);
 const claim=()=>q('select id from public.claim_retell_app_ack($1)',[job]);
 // Use one reserved connection so each rollback isolates the fixture.
 async function isolated(name,check){
  const c=await sql.reserve();
  const tq=async(s,args=[])=>[...await c.unsafe(s,args)];
  await tq('begin');
  try {await check(tq);cases++;console.log(name+': passed');}finally{await tq('rollback');c.release();}
 }
 const authSQL=`insert into private.retell_owner_retest_authorizations(job_id,lead_id,phone_number,operator_id,reason,expires_at,before_state)
 values($1,$1,$2,gen_random_uuid(),'Owner explicitly authorized one automated test',now()+interval '15 minutes','{}')`;
 const casesToCheck=[
  ['no authorization',null,null],
  ['expired authorization',"update private.retell_owner_retest_authorizations set created_at=now()-interval '20 minutes',expires_at=now()-interval '1 minute'",null],
  ['wrong phone',"update private.retell_owner_retest_authorizations set phone_number='+12145550195'",null],
  ['cooldown',"update public.sms_events set created_at=now()-interval '1 hour'",null],
  ['unresolved send',"update public.sms_events set status='unknown'",null],
  ['suppression',`insert into public.test_suppression values('${phone}')`,null],
  ['STOP',`insert into public.sms_events(id,phone_number,direction,opt_out) values(gen_random_uuid(),'${phone}','inbound',true)`,null],
  ['expired inquiry',`update public.retell_form_sms_jobs set expires_at=now()-interval '1 second' where id='${job}'`,null],
  ['bulk scope',null,'select id from public.claim_retell_form_sms_transport(10,NULL,\'app_twilio\')'],
  ['native scope',null,`select id from public.claim_retell_form_sms_transport(1,'${job}','retell_native')`],
 ];
 for(const [name,change,query] of casesToCheck) await isolated(name,async tq=>{
  if(name!=='no authorization')await tq(authSQL,[job,phone]);
  if(change)await tq(change);
  assert.equal((await tq(query||'select id from public.claim_retell_app_ack($1)',query?[]:[job])).length,0);
  assert.equal((await tq('select count(*)::int n from public.sms_events where id=$1',[job]))[0].n,0);
 });
 await isolated('browser and service authorization writes denied',async tq=>{
  for(const role of ['anon','authenticated','service_role']){
   const rows=await tq("select has_table_privilege($1,'private.retell_owner_retest_authorizations','INSERT') can_insert,has_column_privilege($1,'private.retell_owner_retest_authorizations','expires_at','UPDATE') can_extend",[role]);
   assert.equal(rows[0].can_insert,false);assert.equal(rows[0].can_extend,false);
  }
 });
 await authorize();
 const results=await Promise.all(Array.from({length:8},claim));
 assert.equal(results.filter(r=>r.length===1).length,1);
 assert.equal((await q('select count(*)::int n from public.sms_events where id=$1',[job]))[0].n,1);
 assert.ok((await q('select consumed_at from private.retell_owner_retest_authorizations where job_id=$1',[job]))[0].consumed_at);
 assert.equal((await claim()).length,0);
 assert.equal((await q('select count(*)::int n from public.sms_events where status=\'delivered\''))[0].n,2);
 console.log(JSON.stringify({cases:cases+1,concurrent_claimants:8,winners:1,history_preserved:true,provider_calls:0}));
} finally {await sql.end();}
