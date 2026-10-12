import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';

test('review waits for complete unexpired batches, then deduplicates and preserves provenance', async () => {
 const db = new PGlite();
 try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
   CREATE TABLE public.profiles(id uuid PRIMARY KEY,role text,status text);
   CREATE TABLE public.leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),property_address text,city text,state text,zip_code text,source text,motivation_tag text,status text,owner_mailing_address text,sms_sequence_active boolean,email_sequence_active boolean);
   CREATE TABLE public.tasks(id uuid PRIMARY KEY,title text,description text,status text,priority text,type text,assigned_to uuid,due_date timestamptz);
   CREATE TABLE public.app_settings(key text,value text);`);
  const dir = new URL('../../frontend/supabase/migrations/', import.meta.url);
  for (const suffix of ['_daily_list_ingestion.sql','_list_operations.sql','_list_review_batch_guard.sql']) {
   const file = fs.readdirSync(dir).find(x => x.endsWith(suffix));
   await db.exec(fs.readFileSync(new URL(file,dir),'utf8'));
  }
  const owner='00000000-0000-4000-8000-000000000001', run='00000000-0000-4000-8000-000000000002';
  await db.query("INSERT INTO public.profiles VALUES($1,'admin','approved')",[owner]);
  await db.query(`INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
   SELECT $1,id,current_date,now(),'success','',repeat('a',64),2 FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure'`,[run]);
  const addBatch = (index) => db.query(`INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in) VALUES($1,$2,repeat('b',64),repeat('c',64),'{}',1)`,[run,index]);
  await addBatch(0);
  const record={source_record_id:'synthetic-notice',property_address:'1 Synthetic Lane',city:'Dallas',state:'TX',zip:'75201',filed_date:'2026-10-12',source_url:'https://www.dallascounty.org/synthetic',amount_owed:null};
  await db.query(`INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record,review_reason) VALUES($1,0,0,$2,$3,'verify_county_property_evidence')`,[run,record.source_record_id,JSON.stringify(record)]);
  const resolve=()=>db.query('SELECT public.resolve_list_record($1,0,0,$2,$3,$4) AS result',[run,owner,'Dallas','https://www.dallascad.org/synthetic']);
  await assert.rejects(resolve,/Complete unexpired batch set/);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.leads')).rows[0].n,0);
  await addBatch(1);
  await db.exec('UPDATE wholesale_ingest.raw_payloads SET expires_at=now()-interval \'1 second\' WHERE batch_index=1');
  await assert.rejects(resolve,/Complete unexpired batch set/);
  await db.exec('UPDATE wholesale_ingest.raw_payloads SET expires_at=now()+interval \'90 days\'');
  const first=(await resolve()).rows[0].result;
  assert.equal(first.new_lead,true);
  assert.equal((await resolve()).rows[0].result.replayed,true);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM public.leads')).rows[0].n,1);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM wholesale_ingest.review_events')).rows[0].n,1);
  assert.equal((await db.query('SELECT run_id FROM wholesale_ingest.signal_observations')).rows[0].run_id,run);
  const lead=(await db.query('SELECT * FROM public.leads')).rows[0];
  assert.equal(lead.sms_sequence_active,false); assert.equal(lead.email_sequence_active,false);
  await db.exec('SET ROLE authenticated');
  await assert.rejects(resolve,/permission denied/);
 } finally {await db.close();}
});
