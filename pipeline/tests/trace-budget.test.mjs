import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const hash='a'.repeat(64),resultHash='b'.repeat(64);
async function setup(t){
 const db=await database();t.after(()=>db.close());
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261012224412_list_trace_budget.sql',import.meta.url),'utf8'));
 await db.exec(`ALTER TABLE public.leads ADD owner_phone_1 text;ALTER TABLE public.leads ADD owner_email text;
 INSERT INTO public.leads(id,property_address) VALUES('${id(1)}','SYNTHETIC'),('${id(2)}','SYNTHETIC TWO');
 INSERT INTO wholesale_ingest.properties(state,county,address_std,lead_id) VALUES('TX','Dallas','SYNTHETIC','${id(1)}'),('TX','Collin','SYNTHETIC TWO','${id(2)}');
 INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,100);`);
 return db;
}
const rpc=async(db,name,args)=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) AS receipt`,args)).rows[0].receipt;
const reserve=(db,n=10,lead=1,cost=60)=>rpc(db,'reserve_list_trace',[id(n),id(lead),'synthetic',hash,cost]);
const claim=(db,n=10)=>rpc(db,'claim_list_trace',[id(n),hash]);
const settle=(db,state,cost=null,receipt=null,result=null,n=10)=>rpc(db,'settle_list_trace',[id(n),state,cost,receipt,result]);
const budget=async db=>(await db.query('select reserved_cents,actual_cents from wholesale_ingest.daily_budgets')).rows[0];
test('exact reservation replay and one dispatch claim; ambiguity keeps money reserved',async t=>{
 const db=await setup(t);assert.equal((await reserve(db)).replayed,false);assert.equal((await reserve(db)).replayed,true);
 assert.equal((await reserve(db,10,1,70)).blocked,'reference_conflict');
 assert.equal((await claim(db)).dispatch,true);assert.equal((await claim(db)).dispatch,false);
 assert.equal((await settle(db,'unknown')).request.state,'unknown');
 assert.deepEqual(await budget(db),{reserved_cents:60,actual_cents:0});
 assert.equal((await reserve(db,11)).blocked,'unresolved_request');
 assert.equal((await reserve(db,12,2)).blocked,'daily_cap');
 assert.equal((await rpc(db,'cancel_reserved_list_trace',[id(10)])).blocked,'already_claimed');
});
test('verified settlement bills once and releases only the unused reservation',async t=>{
 const db=await setup(t);await reserve(db);await claim(db);await settle(db,'unknown');
 assert.equal((await settle(db,'completed',40,'provider-fixture-1',resultHash)).replayed,false);
 assert.deepEqual(await budget(db),{reserved_cents:0,actual_cents:40});
 assert.equal((await settle(db,'completed',40,'provider-fixture-1',resultHash)).replayed,true);
 assert.equal((await settle(db,'completed',30,'provider-fixture-1',resultHash)).blocked,'settlement_conflict');
 assert.deepEqual(await budget(db),{reserved_cents:0,actual_cents:40});
 assert.equal((await reserve(db,11)).blocked,'already_enriched');
 assert.equal((await reserve(db,12,2)).request.reserved_cents,60);
});
test('unconfirmed billing never releases a hold; unsubmitted reservation can be canceled',async t=>{
 const db=await setup(t);await reserve(db);
 assert.equal((await settle(db,'completed',40,'receipt',resultHash)).blocked,'invalid_transition');
 assert.equal((await rpc(db,'cancel_reserved_list_trace',[id(10)])).request.actual_cents,0);
 assert.deepEqual(await budget(db),{reserved_cents:0,actual_cents:0});
 await reserve(db,11);await claim(db,11);
 for(const args of [['completed',61,'receipt',resultHash],['completed',-1,'receipt',resultHash],['completed',20,null,resultHash],['completed',20,'receipt','bad']]){
  assert.equal((await settle(db,...args,11)).blocked,'unconfirmed_settlement');
 }
 assert.deepEqual(await budget(db),{reserved_cents:60,actual_cents:0});
});
test('enriched, unknown-property and unconfigured-budget leads are not traced',async t=>{
 const db=await setup(t);
 await db.exec(`UPDATE public.leads SET owner_email='fixture@example.invalid' WHERE id='${id(1)}'`);
 assert.equal((await reserve(db)).blocked,'already_enriched');
 await db.exec(`DELETE FROM wholesale_ingest.properties WHERE lead_id='${id(2)}'`);
 assert.equal((await reserve(db,11,2)).blocked,'unverified_pipeline_property');
 await db.exec(`UPDATE public.leads SET owner_email=NULL;DELETE FROM wholesale_ingest.daily_budgets`);
 assert.equal((await reserve(db)).blocked,'budget_not_configured');
});
test('browser roles cannot reserve spend or settle requests',async t=>{
 const db=await setup(t);
 for(const role of ['anon','authenticated']){
  await db.exec(`SET ROLE ${role}`);await assert.rejects(reserve(db),/permission denied/);await assert.rejects(claim(db),/permission denied/);await assert.rejects(settle(db,'unknown'),/permission denied/);
  await db.exec('RESET ROLE');
 }
});

test('reservation identity cannot change and malformed claim cannot authorize dispatch',async t=>{
 const db=await setup(t);await reserve(db);
 await assert.rejects(db.exec('UPDATE wholesale_ingest.skip_trace_requests SET reserved_cents=1'),/immutable/);
 assert.equal((await rpc(db,'claim_list_trace',[id(10),null])).blocked,'invalid_input_identity');
 assert.equal((await rpc(db,'claim_list_trace',[id(10),'c'.repeat(64)])).blocked,'input_changed');
 await db.exec('SET ROLE wholesale_worker');
 await assert.rejects(db.exec('UPDATE wholesale_ingest.daily_budgets SET cap_cents=10000'),/permission denied/);
});
test('midnight expires unsubmitted work; later settlement charges the original day',async t=>{
 const db=await setup(t);
 await db.exec(`INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents,reserved_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date-1,100,80);
 INSERT INTO wholesale_ingest.skip_trace_requests(id,lead_id,provider,request_key,spend_day,reserved_cents,state,input_hash)
 VALUES('${id(20)}','${id(1)}','synthetic','${id(20)}',(clock_timestamp() AT TIME ZONE 'America/Chicago')::date-1,40,'reserved','${hash}'),
 ('${id(21)}','${id(2)}','synthetic','${id(21)}',(clock_timestamp() AT TIME ZONE 'America/Chicago')::date-1,40,'unknown','${hash}');`);
 assert.equal((await claim(db,20)).blocked,'reservation_expired');
 assert.equal((await rpc(db,'cancel_reserved_list_trace',[id(20)])).request.actual_cents,0);
 assert.equal((await settle(db,'completed',30,'late-provider-receipt',resultHash,21)).request.actual_cents,30);
 const rows=(await db.query('select reserved_cents,actual_cents from wholesale_ingest.daily_budgets order by spend_day')).rows;
 assert.deepEqual(rows,[{reserved_cents:0,actual_cents:30},{reserved_cents:0,actual_cents:0}]);
});
