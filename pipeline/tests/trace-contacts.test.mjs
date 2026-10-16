import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const rpc=async(db,name,args)=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) AS receipt`,args)).rows[0].receipt;
async function setup(t){
 const db=await database();t.after(()=>db.close());
 for(const file of ['20261012224412_list_trace_budget.sql','20261012225103_list_trace_contacts.sql'])await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 await db.exec(`ALTER TABLE public.leads ADD owner_first_name text;ALTER TABLE public.leads ADD owner_phone_1 text;
 INSERT INTO public.leads(id,property_address,city,owner_first_name) VALUES('${id(1)}','SYNTHETIC TRACE','Dallas','Synthetic');
 INSERT INTO wholesale_ingest.properties(state,county,address_std,lead_id) VALUES('TX','Dallas','SYNTHETIC TRACE','${id(1)}');
 INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,100);`);
 const prepared=await rpc(db,'prepare_list_trace',[id(10),id(1),'synthetic',60]);
 assert.equal(prepared.request.state,'reserved');
 return {db,hash:prepared.request.input_hash};
}
const claim=(db,hash)=>rpc(db,'claim_list_trace',[id(10),hash]);
const finish=(db,hash,contacts)=>rpc(db,'complete_list_trace',[id(10),'synthetic',hash,40,'provider-fixture',JSON.stringify(contacts)]);
test('contact receipt commits once with unknown DNC and matching billing',async t=>{
 const {db,hash}=await setup(t);assert.equal((await claim(db,hash)).dispatch,true);
 const contacts=[{phone:'+12145550198',phone_type:'mobile',name:'Synthetic'}];
 assert.equal((await finish(db,hash,contacts)).contacts_saved,1);
 assert.equal((await finish(db,hash,contacts)).replayed,true);
 const rows=(await db.query('select dnc_status,trace_request_id from wholesale_ingest.contacts')).rows;
 assert.deepEqual(rows,[{dnc_status:'unknown',trace_request_id:id(10)}]);
 const b=(await db.query('select actual_cents,reserved_cents from wholesale_ingest.daily_budgets')).rows[0];
 assert.deepEqual(b,{actual_cents:40,reserved_cents:0});
 const replay=await rpc(db,'prepare_list_trace',[id(10),id(1),'synthetic',60]);assert.equal(replay.request.state,'completed');assert.equal(replay.contacts_saved,1);
 assert.equal((await finish(db,hash,[{email:'changed@example.invalid'}])).blocked,'settlement_conflict');
});
test('changed owner/property or newly enriched lead blocks dispatch',async t=>{
 const {db,hash}=await setup(t);
 await db.exec(`UPDATE public.leads SET property_address='CHANGED' WHERE id='${id(1)}'`);
 assert.equal((await claim(db,hash)).blocked,'input_changed');
 await db.exec(`UPDATE public.leads SET owner_phone_1='+12145550198' WHERE id='${id(1)}'`);
 assert.equal((await claim(db,hash)).blocked,'already_enriched');
 assert.equal((await db.query('select state from wholesale_ingest.skip_trace_requests')).rows[0].state,'reserved');
});
test('invalid contacts cannot settle spend; stale post-provider input requires reconciliation',async t=>{
 const {db,hash}=await setup(t);await claim(db,hash);
 for(const c of [[{phone:'123'}],[{email:'bad'}],[{email:'a@b.test',dnc_status:'clean'}],[{}]])assert.equal((await finish(db,hash,c)).blocked,'invalid_contacts');
 await db.exec(`UPDATE public.leads SET owner_first_name='Different' WHERE id='${id(1)}'`);
 assert.equal((await finish(db,hash,[{email:'a@b.test'}])).blocked,'input_changed');
 assert.equal((await db.query('select reserved_cents from wholesale_ingest.daily_budgets')).rows[0].reserved_cents,60);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.contacts')).rows[0].n,0);
});
test('snapshot is immutable and contacts failure rolls back billing settlement',async t=>{
 const {db,hash}=await setup(t);await claim(db,hash);
 await assert.rejects(db.exec("UPDATE wholesale_ingest.skip_trace_requests SET input_snapshot='{}'"),/immutable/);
 await db.exec(`CREATE FUNCTION public.reject_fixture_contact() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RAISE EXCEPTION 'fixture storage failure';END$$;
 CREATE TRIGGER reject_fixture_contact BEFORE INSERT ON wholesale_ingest.contacts FOR EACH ROW EXECUTE FUNCTION public.reject_fixture_contact();`);
 await assert.rejects(finish(db,hash,[{email:'a@b.test'}]),/fixture storage failure/);
 assert.equal((await db.query('select state from wholesale_ingest.skip_trace_requests')).rows[0].state,'submitted');
 assert.equal((await db.query('select reserved_cents from wholesale_ingest.daily_budgets')).rows[0].reserved_cents,60);
});
