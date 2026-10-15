import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { database } from './helpers.mjs';
const owner='00000000-0000-4000-8000-000000000001',run='00000000-0000-4000-8000-000000000002',batch='00000000-0000-4000-8000-000000000003';
const sha=value=>createHash('sha256').update(value).digest('hex');
test('bulk receipts bind all extracted pages, reject eligibility claims, replay immutably and flag changed evidence',async t=>{
 const db=await database();t.after(()=>db.close());
 for(const name of ['20261014011940_foreclosure_capture_receipts.sql','20261014021657_foreclosure_extraction_receipts.sql','20261014153604_foreclosure_batch_receipts.sql'])await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+name,import.meta.url),'utf8'));
 await db.exec(`INSERT INTO public.profiles VALUES('${owner}','admin','approved');
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches) SELECT '${run}',id,current_date,now(),'partial','synthetic batch',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key='tx-collin-pre_foreclosure';
 INSERT INTO wholesale_ingest.raw_payloads VALUES('${run}',0,repeat('a',64),'test','{}',1,now(),now()+interval '90 days');
 INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record) VALUES('${run}',0,0,'123','{}');`);
 const capture={document_id:'123',source_url:'https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/123',html_sha256:'a'.repeat(64),captured_at:'2026-01-01T00:00:00Z',expected_pages:1,pages:[{page:1,sha256:'b'.repeat(64)}]};
 const saveCapture=async item=>db.query('SELECT public.save_foreclosure_captures($1,$2,$3)',[owner,'tx-collin-pre_foreclosure',JSON.stringify([item])]);
 await saveCapture(capture);
 const receipt={processor:'foreclosure-batch/1.0',day:'2026-01-02',processed_at:'2026-01-02T12:00:00Z',dataset_url:'https://data.texas.gov/d/ahis-pci3',ownership_snapshot_sha256:'c'.repeat(64),report_sha256:'d'.repeat(64),verification_granted:false,dispatch_authorized:false,outreach_authorized:false,
  notices:[{document_id:'123',html_sha256:'a'.repeat(64),text_sha256s:[sha('synthetic')],parcel_id:'42',appraisal_situs_matched:true,notice_situs_supported:true,trustee_case:'2026-12345-TX',auction_date:'2026-12-01',future_sale:true,holds:[]}]};
 const save=async(r=receipt,id=batch,actor=owner)=>(await db.query('SELECT public.save_foreclosure_batch($1,$2,$3,$4) value',[actor,id,'tx-collin-pre_foreclosure',JSON.stringify(r)])).rows[0].value;
 const status=async()=>(await db.query('SELECT public.foreclosure_capture_status($1) value',[owner])).rows[0].value;
 await assert.rejects(()=>save(),/extracted county evidence/);
 await db.query('SELECT public.save_foreclosure_extractions($1,$2,$3)',[owner,'tx-collin-pre_foreclosure',JSON.stringify([{document_id:'123',source_url:capture.source_url,html_sha256:capture.html_sha256,page:1,image_sha256:'b'.repeat(64),engine:'test/1',text:'synthetic',text_sha256:sha('synthetic'),confidence:90,extracted_at:'2026-01-02T00:00:00Z'}])]);
 assert.equal((await save()).summary.appraisal_situs_matched,1);await save();
 assert.equal((await status()).bulk_batches[0].evidence_current,true);
 for(const r of [{...receipt,verification_granted:true},{...receipt,outreach_authorized:true},{...receipt,notices:[...receipt.notices,...receipt.notices]},{...receipt,notices:[{...receipt.notices[0],html_sha256:'e'.repeat(64)}]}])await assert.rejects(()=>save(r,'00000000-0000-4000-8000-000000000004'));
 await assert.rejects(()=>save({...receipt,report_sha256:'e'.repeat(64)}),/conflict/);
 await assert.rejects(()=>save(receipt,batch,'00000000-0000-4000-8000-000000000009'),/administrator/);
 assert.equal((await db.query('SELECT count(*)::int n FROM wholesale_ingest.foreclosure_batches')).rows[0].n,1);
 assert.equal((await db.query('SELECT count(*)::int n FROM public.leads')).rows[0].n,0);
 await saveCapture({...capture,html_sha256:'f'.repeat(64),captured_at:'2026-01-03T00:00:00Z'});
 assert.equal((await status()).bulk_batches[0].evidence_current,false);
 await db.exec('SET ROLE authenticated');
 await assert.rejects(()=>save(),/permission denied/);await assert.rejects(()=>status(),/permission denied/);
 await assert.rejects(()=>db.query('SELECT * FROM wholesale_ingest.foreclosure_batches'),/permission denied/);
});

test('Dallas appraisal discovery binds the exact saved index and never needs or grants complete-notice verification',async t=>{
 const db=await database();t.after(()=>db.close());
 for(const name of ['20261014011940_foreclosure_capture_receipts.sql','20261014021657_foreclosure_extraction_receipts.sql','20261014153604_foreclosure_batch_receipts.sql','20261014161013_foreclosure_appraisal_index_receipts.sql'])await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/'+name,import.meta.url),'utf8'));
 await db.exec(`INSERT INTO public.profiles VALUES('${owner}','admin','approved');
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches) SELECT '${run}',id,current_date,now(),'partial','synthetic index',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';
 INSERT INTO wholesale_ingest.raw_payloads VALUES('${run}',0,repeat('a',64),repeat('b',64),'{}',2,now(),now()+interval '90 days');
 INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record) VALUES('${run}',0,0,'123','{}'),('${run}',0,1,'124','{}');`);
 const receipt={processor:'dallas-appraisal-batch/1.0',run_id:run,batch_index:0,records_sha256:'b'.repeat(64),archive_sha256:'c'.repeat(64),report_sha256:'d'.repeat(64),source_as_of:'2026-01-02',processed_at:'2026-01-02T12:00:00Z',verification_granted:false,dispatch_authorized:false,outreach_authorized:false,
  items:[{document_id:'123',match_count:1,held:false},{document_id:'124',match_count:0,held:true}]};
 const save=async(r=receipt,id=batch)=>(await db.query('SELECT public.save_foreclosure_appraisal_batch($1,$2,$3) value',[owner,id,JSON.stringify(r)])).rows[0].value;
 const result=await save();assert.equal(result.unique_situs_matches,1);assert.equal(result.verification_granted,false);await save();
 const status=(await db.query('SELECT public.foreclosure_capture_status($1) value',[owner])).rows[0].value;
 assert.equal(status.appraisal_batches[0].summary.documents,2);assert.equal(status.counties.find(c=>c.county==='Dallas').complete_documents,0);
 for(const bad of [{...receipt,records_sha256:'e'.repeat(64)},{...receipt,verification_granted:true},{...receipt,items:[receipt.items[0],receipt.items[0]]},{...receipt,items:[receipt.items[0],{document_id:'999',match_count:1,held:false}]},{...receipt,items:[receipt.items[0],{document_id:'124',match_count:0,held:false}]}])await assert.rejects(()=>save(bad,'00000000-0000-4000-8000-000000000004'));
 await assert.rejects(()=>save({...receipt,report_sha256:'e'.repeat(64)}),/conflict/);
 assert.equal((await db.query('SELECT count(*)::int n FROM wholesale_ingest.foreclosure_appraisal_batches')).rows[0].n,1);
 assert.equal((await db.query('SELECT count(*)::int n FROM public.leads')).rows[0].n,0);
 await db.exec('SET ROLE authenticated');await assert.rejects(()=>save(),/permission denied/);
 await assert.rejects(()=>db.query('SELECT * FROM wholesale_ingest.foreclosure_appraisal_batches'),/permission denied/);
});
