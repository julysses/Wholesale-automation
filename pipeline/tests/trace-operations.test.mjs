import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const rpc=async(db,name,args)=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) AS v`,args)).rows[0].v;
test('operator cancellation is audited, replayable and cannot release a submitted hold',async t=>{
 const db=await database();t.after(()=>db.close());
 for(const file of ['20261012224412_list_trace_budget.sql','20261012225103_list_trace_contacts.sql','20261012225802_list_trace_operations.sql'])await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+file,import.meta.url),'utf8'));
 await db.exec(`ALTER TABLE public.leads ADD owner_first_name text; INSERT INTO public.profiles VALUES('${id(1)}','admin','approved'),('${id(2)}','user','approved');
 INSERT INTO public.leads(id,property_address,city,owner_first_name) VALUES('${id(3)}','SYNTHETIC','Dallas','Synthetic');
 INSERT INTO wholesale_ingest.properties(state,county,address_std,lead_id) VALUES('TX','Dallas','SYNTHETIC','${id(3)}');
 INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,100);`);
 await rpc(db,'prepare_list_trace',[id(4),id(3),'synthetic',60]);
 const before=await rpc(db,'list_trace_operations',[id(1),0]);assert.equal(before.open_count,1);assert.equal(before.total_held_cents,60);
 const cancel=()=>rpc(db,'cancel_list_trace_as_operator',[id(5),id(4),id(1)]);
 assert.equal((await cancel()).replayed,false);assert.equal((await cancel()).replayed,true);
 assert.equal((await rpc(db,'cancel_list_trace_as_operator',[id(5),id(9),id(1)])).blocked,'reference_conflict');
 const after=await rpc(db,'list_trace_operations',[id(1),0]);assert.equal(after.open_count,0);assert.equal(after.total_held_cents,0);assert.equal(after.recent_actions[0].operator_id,id(1));
 const prepared=await rpc(db,'prepare_list_trace',[id(6),id(3),'synthetic',60]);assert.equal((await rpc(db,'claim_list_trace',[id(6),prepared.request.input_hash])).dispatch,true);
 assert.equal((await rpc(db,'cancel_list_trace_as_operator',[id(7),id(6),id(1)])).blocked,'already_claimed');
 await assert.rejects(rpc(db,'list_trace_operations',[id(2),0]),/administrator/);
 for(const role of ['anon','authenticated']){await db.exec('SET ROLE '+role);await assert.rejects(cancel(),/permission denied/);await db.exec('RESET ROLE');}
 await db.exec('SET ROLE service_role');await assert.rejects(db.exec('DELETE FROM wholesale_ingest.trace_operator_events'),/permission denied/);
});
