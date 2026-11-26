import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const hash='a'.repeat(64);
const rpc=async(db,name,args=[])=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) as result`,args)).rows[0].result;
async function setup(t){
 const db=await database();t.after(()=>db.close());
 for(const file of ['20261012224412_list_trace_budget.sql','20261012225103_list_trace_contacts.sql','20261012225802_list_trace_operations.sql','20261013164454_list_trace_total_cap.sql'])await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 await db.exec(`ALTER TABLE public.leads ADD owner_first_name text;
 INSERT INTO public.leads(id,property_address,city,owner_first_name) VALUES('${id(1)}','SYNTHETIC ONE','Dallas','Synthetic'),('${id(2)}','SYNTHETIC TWO','Dallas','Synthetic');
 INSERT INTO public.leads(id,property_address) VALUES('${id(20)}','HISTORICAL SYNTHETIC'),('${id(21)}','HISTORICAL SYNTHETIC TWO');
 INSERT INTO wholesale_ingest.properties(state,county,address_std,lead_id) VALUES('TX','Dallas','SYNTHETIC ONE','${id(1)}'),('TX','Dallas','SYNTHETIC TWO','${id(2)}');
 INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,10000);`);
 return db;
}
const reserve=(db,n,lead,cost,provider='synthetic')=>rpc(db,'reserve_list_trace',[id(n),id(lead),provider,hash,cost]);
test('historical spend and uncertain charges consume the total across days and providers',async t=>{
 const db=await setup(t);
 await db.exec(`INSERT INTO wholesale_ingest.skip_trace_requests(id,lead_id,provider,request_key,spend_day,reserved_cents,actual_cents,state,input_hash) VALUES
 ('${id(20)}','${id(20)}','old_provider','old-paid',CURRENT_DATE-2,4000,3500,'completed','${hash}'),
 ('${id(21)}','${id(21)}','old_provider','old-unknown',CURRENT_DATE-1,1000,NULL,'unknown','${hash}');`);
 assert.deepEqual(await rpc(db,'list_trace_total_budget'),{cap_cents:5000,reserved_cents:1000,actual_cents:3500,committed_cents:4500,remaining_cents:500});
 assert.equal((await reserve(db,10,1,501,'different_provider')).blocked,'total_cap');
 assert.equal((await reserve(db,10,1,500)).replayed,false);
 assert.equal((await reserve(db,10,1,500)).replayed,true);
 assert.equal((await reserve(db,11,2,1)).blocked,'total_cap');
 assert.equal((await rpc(db,'cancel_reserved_list_trace',[id(10)])).request.actual_cents,0);
 assert.equal((await rpc(db,'list_trace_total_budget')).remaining_cents,500);
});
test('settlement releases only unused quote and does not authorize retracing',async t=>{
 const db=await setup(t);
 const p=await rpc(db,'prepare_list_trace',[id(10),id(1),'synthetic',5000]);
 assert.equal((await rpc(db,'claim_list_trace',[id(10),p.request.input_hash])).dispatch,true);
 await rpc(db,'settle_list_trace',[id(10),'unknown',null,null,null]);
 assert.equal((await rpc(db,'list_trace_total_budget')).remaining_cents,0);
 await rpc(db,'settle_list_trace',[id(10),'completed',4900,'synthetic-receipt','b'.repeat(64)]);
 assert.equal((await rpc(db,'list_trace_total_budget')).remaining_cents,100);
 assert.equal((await reserve(db,11,1,1)).blocked,'already_enriched');
 assert.equal((await reserve(db,12,2,101)).blocked,'total_cap');
});
test('legacy over-cap reservations cannot dispatch and browser roles cannot read the ledger',async t=>{
 const db=await setup(t);
 const p=await rpc(db,'prepare_list_trace',[id(10),id(1),'synthetic',100]);
 await db.exec(`INSERT INTO wholesale_ingest.skip_trace_requests(id,lead_id,provider,request_key,spend_day,reserved_cents,state,input_hash) VALUES('${id(20)}','${id(20)}','legacy','legacy-over-cap',CURRENT_DATE-1,5000,'unknown','${hash}')`);
 assert.equal((await rpc(db,'claim_list_trace',[id(10),p.request.input_hash])).blocked,'total_cap');
 for(const role of ['anon','authenticated']){
  await db.exec(`SET ROLE ${role}`);await assert.rejects(rpc(db,'list_trace_total_budget'),/permission denied/);await db.exec('RESET ROLE');
 }
});
