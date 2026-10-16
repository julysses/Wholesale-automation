import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';

test('source review pages retain global counts, exclude resolved rows and preserve source evidence',async()=>{
 const db=new PGlite();
 try{
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
   CREATE TABLE public.profiles(id uuid PRIMARY KEY,role text,status text);
   CREATE TABLE public.leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),property_address text,city text,state text,zip_code text,source text,motivation_tag text,status text,owner_mailing_address text,sms_sequence_active boolean,email_sequence_active boolean);
   CREATE TABLE public.tasks(id uuid PRIMARY KEY,title text,description text,status text,priority text,type text,assigned_to uuid,due_date timestamptz);
   CREATE TABLE public.app_settings(key text,value text);`);
  const dir=new URL('../../frontend/supabase/migrations/',import.meta.url);
  for(const suffix of ['_daily_list_ingestion.sql','_list_operations.sql','_list_reviewed_identity.sql','_list_review_source_filters.sql']){
   await db.exec(fs.readFileSync(new URL(fs.readdirSync(dir).find(x=>x.endsWith(suffix)),dir),'utf8'));
  }
  for(const [index,source,n] of [[1,'tx-dallas-tax_delinquent',105],[2,'tx-dallas-pre_foreclosure',3],[3,'tx-collin-tax_delinquent',2]]){
   const run=`00000000-0000-4000-8000-${String(index).padStart(12,'0')}`;
   await db.query(`INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,received_at,status,status_reason,manifest_hash,expected_batches)
    SELECT $1,id,current_date,now(),'2026-10-13T10:00:00Z','partial','synthetic',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key=$2`,[run,source]);
   await db.query(`INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in) VALUES($1,0,repeat('b',64),repeat('c',64),'{}',$2)`,[run,n]);
   await db.query(`INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record,review_reason)
    SELECT $1,0,n,'synthetic-'||n,jsonb_build_object('property_address','Synthetic '||n,'city','Dallas','state','TX','zip','75201','parcel_id','test-'||n,'source_url','https://www.dallascounty.org/test'),'verify_county_property_evidence'
    FROM generate_series(0,$2::int-1) n`,[run,n]);
  }
  await db.exec(`UPDATE wholesale_ingest.records SET resolved_at=now() WHERE run_id='00000000-0000-4000-8000-000000000001' AND ordinal=0;
   UPDATE wholesale_ingest.records SET review_reason=NULL WHERE run_id='00000000-0000-4000-8000-000000000001' AND ordinal=1;`);
  const page=async(source,offset=0)=>(await db.query('SELECT public.list_pipeline_snapshot_filtered(current_date,$1,$2) result',[offset,source])).rows[0].result;
  const first=await page('tx-dallas-tax_delinquent'),last=await page('tx-dallas-tax_delinquent',100);
  assert.equal(first.review_count,103);assert.equal(first.total_review_count,108);assert.equal(first.reviews.length,100);
  assert.deepEqual(last.reviews.map(r=>r.ordinal),[102,103,104]);
  assert(first.reviews.every(r=>r.source_key==='tx-dallas-tax_delinquent'&&/^[a-f0-9]{32}$/.test(r.source_fingerprint)&&r.city==='Dallas'&&r.parcel_id));
  assert.equal(new Set([...first.reviews,...last.reviews].map(r=>r.source_record_id)).size,103);
  const foreclosure=await page('tx-dallas-pre_foreclosure');
  assert.equal(foreclosure.review_count,3);assert.equal(foreclosure.total_review_count,108);
  assert.equal((await page('tx-collin-pre_foreclosure')).review_count,0);
  assert.deepEqual((await page(null,100)).reviews.map(r=>[r.source_key,r.ordinal]),[
   ...[102,103,104].map(n=>['tx-dallas-tax_delinquent',n]),
   ...[0,1,2].map(n=>['tx-dallas-pre_foreclosure',n]),...[0,1].map(n=>['tx-collin-tax_delinquent',n])]);
  assert.equal((await db.query('SELECT public.list_pipeline_snapshot(current_date,0) result')).rows[0].result.review_count,108);
  for(const role of ['anon','authenticated','wholesale_ingestor']){
   await db.exec(`SET ROLE ${role}`);
   await assert.rejects(()=>page(null),/permission denied/);
   await db.exec('RESET ROLE');
  }
  assert.equal((await db.query('SELECT count(*)::int n FROM public.leads')).rows[0].n,0);
 }finally{await db.close();}
});
