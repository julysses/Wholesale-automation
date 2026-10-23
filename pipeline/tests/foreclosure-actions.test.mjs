import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
test('foreclosure daily inbox deduplicates and preserves first receipt across retention, filters county and rejects public access',async()=>{
 const db=new PGlite();
 try {
 await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE TABLE public.leads(id uuid PRIMARY KEY); CREATE TABLE public.tasks(id uuid PRIMARY KEY);');
 const dir=new URL('../../frontend/supabase/migrations/',import.meta.url);
 for(const suffix of ['_daily_list_ingestion.sql','_foreclosure_daily_actions.sql']) await db.exec(fs.readFileSync(new URL(fs.readdirSync(dir).find(x=>x.endsWith(suffix)),dir),'utf8'));
 await db.exec(`INSERT INTO wholesale_ingest.sources(source_key,state,county,jurisdiction,list_type,method,source_url,allowed_hosts,lookback_days,backfill_days,schedule_cron)
 VALUES('tx-dallas-pre_foreclosure','TX','Dallas','county','pre_foreclosure','browser','https://example.org',ARRAY['example.org'],30,30,'0 5 * * *'),('tx-collin-pre_foreclosure','TX','Collin','county','pre_foreclosure','browser','https://example.org',ARRAY['example.org'],30,30,'0 5 * * *');`);
 let n=0;
 async function seed(county,notice,when){
 const id=`00000000-0000-4000-8000-${String(++n).padStart(12,'0')}`;
 await db.query(`INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,received_at,pulled_at,status,status_reason,manifest_hash,expected_batches) SELECT $1,id,'2026-10-13',$2,$2,'partial','review',repeat('a',64),1 FROM wholesale_ingest.sources WHERE county=$3`,[id,when,county]);
 await db.query(`INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in) VALUES($1,0,repeat('a',64),repeat('b',64),'{}',1)`,[id]);
 await db.exec('SET ROLE wholesale_ingestor');
 await db.query(`INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record,review_reason) VALUES($1,0,0,$2,'{"source_url":"https://example.org"}','verify_property')`,[id,notice]);
 await db.exec('RESET ROLE');return id;
 }
 const get=async(day='2026-10-13',county=null)=> (await db.query('SELECT public.foreclosure_daily_actions($1,$2,0) AS value',[day,county])).rows[0].value;
 const old=await seed('Dallas','same','2026-10-13T04:59:00Z'); // previous Central day
 await seed('Dallas','same','2026-10-13T06:00:00Z');
 await seed('Collin','same','2026-10-13T06:01:00Z');
 let value=await get();assert.equal(value.total,2);assert.equal(value.new_today,1);assert.equal(value.backlog,1);
 assert.equal((await get('2026-10-13','Dallas')).new_today,0);
 await db.query('DELETE FROM wholesale_ingest.records WHERE run_id=$1',[old]);
 await seed('Dallas','same','2026-10-14T12:00:00Z');
 value=await get('2026-10-14','Dallas');assert.equal(value.new_today,0);assert.equal(value.total,1);
 await db.exec(`UPDATE wholesale_ingest.records SET resolved_at=now() WHERE source_record_id='same' AND run_id IN (SELECT id FROM wholesale_ingest.ingest_runs WHERE source_id=(SELECT id FROM wholesale_ingest.sources WHERE county='Dallas'))`);
 assert.equal((await get('2026-10-14','Dallas')).total,0);
 await db.exec('SET ROLE authenticated');await assert.rejects(()=>get(),/permission denied/);
 } finally {await db.close();}
});
