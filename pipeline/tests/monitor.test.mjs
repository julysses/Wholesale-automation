import test from 'node:test';
import assert from 'node:assert/strict';
import {database} from './helpers.mjs';

const day='2026-10-12', time='2026-10-12T11:00:00Z'; // 06:00 Central
async function scan(db,now=time){return (await db.query('select wholesale_ingest.scan_at($1) as result',[now])).rows[0].result;}
async function owner(db){
 const id=crypto.randomUUID();
 await db.query("insert into public.profiles values($1,'admin','approved')",[id]);
 await db.query("insert into public.app_settings values('lead_owner_user_id',$1)",[id]);
 return id;
}
async function enable(db,key='tx-dallas-pre_foreclosure',date=day){
 await db.query("update wholesale_ingest.sources set enabled=true,procedure_approved_at=($2::date+interval '1 hour') AT TIME ZONE 'America/Chicago' where source_key=$1",[key,date]);
 return (await db.query('select id from wholesale_ingest.sources where source_key=$1',[key])).rows[0].id;
}
async function run(db,source,status='success',batches=1,scheduled=day,received='2026-10-12T10:00:00Z'){
 const id=crypto.randomUUID();
 await db.query(`insert into wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,received_at,status,status_reason,manifest_hash,expected_batches) values($1,$2,$3,$4,$4,$5,$6,repeat('a',64),$7)`,[id,source,scheduled,received,status,status==='success'?'':'synthetic status reason',batches]);
 return id;
}
async function batch(db,id,index=0){await db.query("insert into wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in,expires_at) values($1,$2,repeat('b',64),repeat('c',64),'{\"private\":\"synthetic\"}',0,'2027-01-01')",[id,index]);}
async function count(db,table){return (await db.query(`select count(*)::int as n from ${table}`)).rows[0].n;}

test('deadline is inclusive; repeated missing scans create one task; complete delivery resolves incident',async()=>{
 const db=await database();try{
 await owner(db);const src=await enable(db);
 let summary=await scan(db,'2026-10-12T10:59:59Z');assert.equal(summary.open_incidents.length,0);
 summary=await scan(db);assert.equal(summary.open_incidents[0].kind,'missing');
 await scan(db);assert.equal(await count(db,'public.tasks'),1);
 const id=await run(db,src);await batch(db,id);
 summary=await scan(db);assert.equal(summary.open_incidents.length,0);
 assert.equal((await db.query('select processing_status from wholesale_ingest.ingest_runs')).rows[0].processing_status,'completed');
 assert.equal(await count(db,'public.tasks'),1); // retained for operator acknowledgement
 assert.equal((await db.query('select status,delivered_at from wholesale_ingest.daily_digests')).rows[0].status,'generated');
 assert.equal((await db.query('select delivered_at from wholesale_ingest.daily_digests')).rows[0].delivered_at,null);
 }finally{await db.close();}
});

test('blocked, partial and failed runs create assigned review incidents before deadline without duplicate tasks',async()=>{
 const db=await database();try{
 await owner(db);const src=await enable(db);
 for(const [n,status] of ['blocked','partial','failed'].entries()){
  const id=await run(db,src,status,1,day,`2026-10-12T10:0${n}:00Z`);await batch(db,id);
  const summary=await scan(db,'2026-10-12T10:30:00Z');
  assert.equal(summary.open_incidents[0].kind,status);
  assert.equal(summary.sources.find(s=>s.source_key==='tx-dallas-pre_foreclosure').status,status);
 }
 assert.equal(await count(db,'public.tasks'),1);
 }finally{await db.close();}
});

test('incomplete batches and unavailable owner remain visible; owner recovery assigns exactly one task',async()=>{
 const db=await database();try{
 const src=await enable(db);const id=await run(db,src,'success',2);await batch(db,id);
 let summary=await scan(db);assert.equal(summary.owner_configured,false);assert.equal(summary.open_incidents[0].kind,'incomplete');
 assert.equal(await count(db,'public.tasks'),0);
 await owner(db);await scan(db);await scan(db);assert.equal(await count(db,'public.tasks'),1);
 await batch(db,id,1);summary=await scan(db);assert.equal(summary.open_incidents.length,0);
 }finally{await db.close();}
});

test('retention purges raw content while keeping receipts, counts and unresolved review state',async()=>{
 const db=await database();try{
 await owner(db);const src=await enable(db);const id=await run(db,src);await batch(db,id);
 await db.query("insert into wholesale_ingest.records(run_id,batch_index,ordinal,record,review_reason) values($1,0,0,'{}','verify')",[id]);
 await db.query("update wholesale_ingest.raw_payloads set expires_at='2026-10-12T10:59:00Z',records_in=1 where run_id=$1",[id]);
 let summary=await scan(db);assert.equal(summary.open_incidents[0].kind,'property_review');
 assert.equal(await count(db,'wholesale_ingest.records'),0);
 const receipt=(await db.query('select * from wholesale_ingest.raw_payloads')).rows[0];
 assert.equal(receipt.payload,null);assert.ok(receipt.purged_at);assert.equal(receipt.payload_hash,'b'.repeat(64));
 summary=await scan(db);assert.equal(summary.open_incidents[0].kind,'property_review');
 assert.equal(summary.sources.find(s=>s.run_id===id).records_in,1);
 assert.equal(await count(db,'public.leads'),0);
 }finally{await db.close();}
});

test('expected deadlines follow Central DST and catch a missed prior-day scan',async()=>{
 const db=await database();try{
 const src=await enable(db,'tx-dallas-pre_foreclosure','2026-10-31');
 await scan(db,'2026-11-01T13:00:00Z');
 const rows=(await db.query('select day,due_at from wholesale_ingest.expected_runs where source_id=$1 order by day',[src])).rows;
 assert.equal(rows.length,2);
 assert.equal(new Date(rows[0].due_at).toISOString(),'2026-10-31T11:00:00.000Z');
 assert.equal(new Date(rows[1].due_at).toISOString(),'2026-11-01T12:00:00.000Z');
 await db.exec('set role authenticated');await assert.rejects(()=>scan(db),/permission denied/);
 }finally{await db.close();}
});

test('digest selects latest receipt and latest per-lead score; newer failure reopens the original incident',async()=>{
 const db=await database();try{
 await owner(db);const src=await enable(db);await scan(db);
 const id=await run(db,src);await batch(db,id);await scan(db);
 const failed=await run(db,src,'failed',1,day,'2026-10-12T10:45:00Z');await batch(db,failed);
 const lead=crypto.randomUUID();await db.query('insert into public.leads(id) values($1)',[lead]);
 for(const [n,score] of [99,40].entries()){
  await db.query("insert into wholesale_ingest.lead_evaluations(lead_id,input_hash,model_version,prompt_version,score,reasons,flags,route,stack_count,created_at) values($1,$2,'test','v1',$3,'[]','[]','review',0,$4)",[lead,String(n),score,`2026-10-12T10:0${n}:00Z`]);
 }
 const summary=await scan(db);
 assert.equal(summary.top_ten.length,1);assert.equal(summary.top_ten[0].score,40);
 assert.equal(summary.open_incidents[0].kind,'failed');assert.equal(await count(db,'public.tasks'),1);
 assert.equal(summary.sources.find(s=>s.source_key==='tx-dallas-pre_foreclosure').run_id,failed);
 }finally{await db.close();}
});
