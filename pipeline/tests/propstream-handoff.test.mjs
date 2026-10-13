import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const rpc=async(db,name,args)=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) AS value`,args)).rows[0].value;
async function setup(t){
 const db=await database(); t.after(()=>db.close());
 const dir=new URL('../../frontend/supabase/migrations/',import.meta.url);
 for(const suffix of ['_list_trace_budget.sql','_list_trace_contacts.sql','_list_trace_operations.sql','_list_trace_total_cap.sql','_propstream_operator_handoff.sql'])await db.exec(fs.readFileSync(new URL(fs.readdirSync(dir).find(x=>x.endsWith(suffix)),dir),'utf8'));
 await db.exec(`ALTER TABLE public.tasks ADD lead_id uuid; ALTER TABLE public.leads ADD owner_first_name text; ALTER TABLE public.leads ADD owner_last_name text;ALTER TABLE public.leads ADD dnc boolean DEFAULT false;
 INSERT INTO public.profiles VALUES('${id(1)}','admin','approved');
 INSERT INTO public.leads(id,property_address,city,state,zip_code,owner_first_name,status) VALUES('${id(2)}','QA TEST PROPERTY','Dallas','TX','75201','Synthetic','new');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,city,zip,lead_id) VALUES('${id(3)}','TX','Dallas','QA TEST PROPERTY','Dallas','75201','${id(2)}');
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches) SELECT '${id(4)}',id,current_date,now(),'partial','test',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';
 INSERT INTO wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,source_url,first_run_id,last_run_id,auction_date,active) SELECT '${id(5)}','${id(3)}',id,'test','pre_foreclosure','https://www.dallascounty.org/test','${id(4)}','${id(4)}',current_date+30,true FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';`);
 const snap=()=>rpc(db,'propstream_handoff_snapshot',[id(1),0]);
 const row=(await snap()).items[0];
 const payload={input_hash:row.input_hash,signal_id:row.signal_id,signal_hash:row.signal_hash,quote_cents:50,prepaid_balance_cents:5000,quote_reference:'synthetic quote',owner_evidence_url:'https://www.dallascad.org/test',status_evidence_url:'https://dallas.tx.publicsearch.us/doc/test',notes:'Synthetic fixture all pages and owner verified',all_pages_reviewed:true};
 const act=(event,action,p,request=10)=>rpc(db,'propstream_handoff_action',[id(event),id(1),id(request),id(2),action,JSON.stringify(p)]);
 return {db,snap,row,payload,act};
}
test('PropStream handoff reserves once, never reauthorizes replay, reconciles contacts and creates one follow-up',async t=>{
 const {db,snap,payload,act}=await setup(t);
 assert.equal((await snap()).items[0].stage,'quote_and_evidence_required');
 const prepared=await act(20,'prepare',payload);assert.equal(prepared.request.state,'reserved');
 assert.equal((await act(20,'prepare',payload)).replayed,true);
 await assert.rejects(()=>act(20,'prepare',{...payload,quote_cents:60}),/reference conflict/);
 assert.equal((await act(21,'start',{input_hash:payload.input_hash})).dispatch,true);
 assert.equal((await act(21,'start',{input_hash:payload.input_hash})).dispatch,false);
 const result={input_hash:payload.input_hash,actual_cents:40,provider_receipt:'test-order-1',contacts:[{phone:'+12145550198',phone_type:'mobile',name:'Synthetic'}],confirmed_match:true};
 assert.equal((await act(22,'reconcile',result)).contacts_saved,1);
 assert.equal((await act(22,'reconcile',result)).replayed,true);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 assert.equal((await snap()).items[0].stage,'result_saved');
 assert.equal((await snap()).total_budget.actual_cents,40);
 await assert.rejects(()=>act(23,'prepare',payload,11),/identity unavailable/);
 assert.equal((await rpc(db,'propstream_recover_event',[id(1),id(999)])).result,null);
 await assert.rejects(()=>act(999,'prepare',payload,12),/abandoned/);
 await db.exec('SET ROLE authenticated');await assert.rejects(()=>snap(),/permission denied/);
});
test('rejects missing review, unverified owner, expired or suppressed foreclosure and insufficient balance',async t=>{
 const {db,payload,act}=await setup(t);
 for(const change of [{all_pages_reviewed:false},{owner_evidence_url:'https://example.org'},{quote_cents:5001},{prepaid_balance_cents:20},{input_hash:'a'.repeat(64)}])await assert.rejects(()=>act(20,'prepare',{...payload,...change}));
 await db.exec(`UPDATE public.leads SET owner_first_name=NULL WHERE id='${id(2)}'`);await assert.rejects(()=>act(20,'prepare',payload),/identity unavailable/);
 await db.exec(`UPDATE public.leads SET owner_first_name='Synthetic',dnc=true WHERE id='${id(2)}'`);await assert.rejects(()=>act(20,'prepare',payload),/suppressed/);
 await db.exec(`UPDATE public.leads SET dnc=false;UPDATE wholesale_ingest.distress_signals SET active=false`);await assert.rejects(()=>act(20,'prepare',payload),/active foreclosure/);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.skip_trace_requests')).rows[0].n,0);
});

test('cap, stale sale and empty results stay conservative; submitted suppression does not hide reconciliation',async t=>{
 const {db,payload,act,snap}=await setup(t);
 await act(20,'prepare',{...payload,quote_cents:5000});
 assert.equal((await snap()).total_budget.remaining_cents,0);
 await db.exec(`UPDATE wholesale_ingest.distress_signals SET auction_date=current_date-1`);
 await assert.rejects(()=>act(21,'start',{input_hash:payload.input_hash}),/Recheck/);
 await db.exec(`UPDATE wholesale_ingest.distress_signals SET auction_date=current_date+30`);
 await act(21,'start',{input_hash:payload.input_hash});
 await db.exec(`UPDATE public.leads SET dnc=true`);
 assert.equal((await snap()).items[0].stage,'reconciliation_required');
 const result=await act(22,'reconcile',{input_hash:payload.input_hash,actual_cents:0,provider_receipt:'no-match-fixture',contacts:[],confirmed_match:true});
 assert.equal(result.contacts_saved,0);
 assert.equal((await db.query('select lead_id from public.tasks')).rows[0].lead_id,id(2));
 assert.equal((await snap()).total_budget.remaining_cents,5000);
 await db.exec(`UPDATE public.leads SET dnc=false`);
 await assert.rejects(()=>act(23,'prepare',payload,11),/already_enriched/);
});
