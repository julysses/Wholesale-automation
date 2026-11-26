import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
const run=async db=>(await db.query('select wholesale_ingest.supervise_bulk_pipeline() v')).rows[0].v;
async function setup(t){
 const db=await database();t.after(()=>db.close());
 await db.exec(`INSERT INTO public.profiles VALUES('00000000-0000-4000-8000-000000000001','admin','approved');
 INSERT INTO public.app_settings VALUES('lead_owner_user_id','00000000-0000-4000-8000-000000000001');`);
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261014200149_scheduled_bulk_supervision.sql',import.meta.url),'utf8'));
 return db;
}
test('consecutive scans keep one durable status and no routine tasks',async t=>{
 const db=await setup(t);
 assert.equal((await run(db)).supervision,'healthy');assert.equal((await run(db)).supervision,'healthy');
 assert.equal((await db.query('select attempts from wholesale_ingest.bulk_supervision')).rows[0].attempts,2);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,0);
 await db.exec('SET ROLE authenticated');await assert.rejects(run(db),/permission denied/);
});
test('failure rolls back partial writes and reuses one exception task',async t=>{
 const db=await setup(t);
 await db.exec(`CREATE OR REPLACE FUNCTION public.scan_list_pipeline() RETURNS jsonb LANGUAGE plpgsql AS $$ BEGIN
 INSERT INTO public.app_settings VALUES('must_rollback','true');RAISE EXCEPTION 'private error'; END $$;`);
 assert.equal((await run(db)).reason,'scan_error_P0001');await run(db);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
 assert.equal((await db.query("select count(*)::int n from public.app_settings where key='must_rollback'")).rows[0].n,0);
 assert.equal((await db.query('select description from public.tasks')).rows[0].description,'scan_error_P0001');
});
test('expired evidence blocks legacy purge and does not execute scanner',async t=>{
 const db=await setup(t);
 await db.exec(`INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
 SELECT '00000000-0000-4000-8000-000000000002',id,current_date,now(),'partial','test',repeat('a',64),1 FROM wholesale_ingest.sources LIMIT 1;
 INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in,expires_at)
 VALUES('00000000-0000-4000-8000-000000000002',0,repeat('a',64),'test','{}',0,now()-interval '1 second');`);
 assert.equal((await run(db)).reason,'retention_review_required');await run(db);
 assert.deepEqual((await db.query('select payload from wholesale_ingest.raw_payloads')).rows[0].payload,{});
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.daily_digests')).rows[0].n,0);
 assert.equal((await db.query('select count(*)::int n from public.tasks')).rows[0].n,1);
});
