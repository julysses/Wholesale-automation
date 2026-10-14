import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const rpc=async(db,name,args)=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) AS value`,args)).rows[0].value;
async function setup(t){
 const db=await database(); t.after(()=>db.close());
 const dir=new URL('../../frontend/supabase/migrations/',import.meta.url);
 for(const suffix of ['_list_reviewed_identity.sql','_list_trace_budget.sql','_list_trace_contacts.sql','_list_trace_operations.sql','_list_trace_total_cap.sql','_propstream_operator_handoff.sql','_collin_appraisal_evidence_host.sql','_foreclosure_status_review.sql','_propstream_bulk_actions.sql','_foreclosure_trustee_status_evidence.sql'])await db.exec(fs.readFileSync(new URL(fs.readdirSync(dir).find(x=>x.endsWith(suffix)),dir),'utf8'));
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

test('trustee status evidence binds to the exact verified property and never becomes owner evidence',async t=>{
 const {db,payload,act}=await setup(t);
 const valid='https://www.xome.com/auctions/qa-test-property-dallas-tx-75201-123456789';
 for(const url of [valid.replace('75201','75001'),valid.replace('qa-test-property','another-property'),valid.replace('dallas','plano'),valid+'?override=true',valid.replace('www.xome.com','xome.com.example.org'),'https://www.xome.com/auctions']){
  await assert.rejects(()=>act(20,'prepare',{...payload,status_evidence_url:url}),/Property-bound/);
 }
 await assert.rejects(()=>act(20,'prepare',{...payload,owner_evidence_url:valid,status_evidence_url:valid}),/Official owner/);
 assert.equal((await act(20,'prepare',{...payload,status_evidence_url:valid})).request.state,'reserved');
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.skip_trace_requests')).rows[0].n,1);
 await db.exec('SET ROLE authenticated');
 await assert.rejects(()=>db.query('select wholesale_ingest.foreclosure_status_evidence_allowed($1,$2,$3)',[id(2),'Dallas',valid]),/permission denied/);
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

 test('audited status reviews activate verified signals, reject stale edits, and invalidate reserved quotes',async t=>{
 const {db,snap,payload,act}=await setup(t);
 await db.exec('UPDATE wholesale_ingest.distress_signals SET active=false');
 const held=(await snap()).items[0];
 const review={signal_id:held.signal_id,signal_hash:held.signal_hash,active:true,auction_date:held.auction_date,status_evidence_url:'https://www.dallascounty.org/test',notes:'Synthetic current trustee status independently confirmed',confirmed_current_status:true};
 await assert.rejects(()=>act(30,'review_status',{...review,status_evidence_url:'https://example.org'}),/current-sale evidence required/);
 await assert.rejects(()=>act(30,'review_status',{...review,confirmed_current_status:false}),/review/);
 assert.equal((await act(30,'review_status',review)).status_reviewed,true);
 assert.equal((await act(30,'review_status',review)).replayed,true);
 await assert.rejects(()=>act(31,'review_status',review),/evidence changed/);
 const ready=(await snap()).items[0];assert.equal(ready.stage,'quote_and_evidence_required');
 await act(32,'prepare',{...payload,signal_hash:ready.signal_hash});
 await act(33,'review_status',{...review,signal_hash:ready.signal_hash,active:false});
 await assert.rejects(()=>act(34,'start',{input_hash:payload.input_hash}),/Recheck/);
 assert.equal((await db.query("select count(*)::int n from wholesale_ingest.propstream_events where status_review is not null")).rows[0].n,2);
 assert.equal((await rpc(db,'propstream_recover_event',[id(1),id(30)])).result.status_reviewed,true);
 });

test('bulk is atomic, enforces aggregate balance, replays safely and tombstones lost requests',async t=>{
 const {db,payload,snap}=await setup(t);
 await db.exec(`INSERT INTO public.leads(id,property_address,city,state,zip_code,owner_first_name,status) VALUES('${id(102)}','SECOND QA PROPERTY','Dallas','TX','75201','Synthetic','new');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,city,zip,lead_id) VALUES('${id(103)}','TX','Dallas','SECOND QA PROPERTY','Dallas','75201','${id(102)}');
 INSERT INTO wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,source_url,first_run_id,last_run_id,auction_date,active) SELECT '${id(105)}','${id(103)}',source_id,'second','pre_foreclosure',source_url,first_run_id,last_run_id,auction_date,true FROM wholesale_ingest.distress_signals WHERE id='${id(5)}'`);
 const rows=(await snap()).items;
 const items=rows.map((r,i)=>({event_id:id(200+i),request_id:id(300+i),lead_id:r.lead_id,action:'prepare',payload:{...payload,signal_id:r.signal_id,signal_hash:r.signal_hash,input_hash:r.input_hash,quote_cents:30,prepaid_balance_cents:50}}));
 const bulk=(n,list)=>rpc(db,'propstream_bulk_action',[id(n),id(1),JSON.stringify(list)]);
 await assert.rejects(()=>bulk(400,items),/Batch quote exceeds/);
 items.forEach(x=>x.payload.prepaid_balance_cents=5000);
 const bad=structuredClone(items);bad[1].payload.signal_hash='f'.repeat(32);
 await assert.rejects(()=>bulk(400,bad),/evidence changed/);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.skip_trace_requests')).rows[0].n,0);
 assert.equal((await bulk(400,items)).count,2);
 assert.equal((await bulk(400,items)).dispatch,false);
 assert.equal((await snap()).total_budget.committed_cents,60);
 const starts=items.map((x,i)=>({...x,event_id:id(210+i),action:'start',payload:{input_hash:x.payload.input_hash}}));
 assert.equal((await bulk(401,starts)).dispatch,true);assert.equal((await bulk(401,starts)).dispatch,false);
 assert.equal((await rpc(db,'propstream_bulk_recover',[id(401),id(1)])).result.count,2);
 await rpc(db,'propstream_bulk_recover',[id(402),id(1)]);
 await assert.rejects(()=>bulk(402,items),/abandoned/);
 const completed=items.map((x,i)=>({...x,event_id:id(220+i),action:'reconcile',payload:{input_hash:x.payload.input_hash,actual_cents:20,provider_receipt:'bulk-receipt-'+i,contacts:[],confirmed_match:true}}));
 const settled=await bulk(403,completed);assert.equal(settled.count,2);
 assert.equal((await snap()).total_budget.actual_cents,40);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,2);
 await bulk(403,completed);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,2);
});
