import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';
test('migration executes in isolated PostgreSQL; uniqueness, geography, RLS and scoped writes hold',async()=>{
 const db=new PGlite();
 try {
  await db.exec('CREATE ROLE anon;CREATE ROLE authenticated;CREATE TABLE public.leads(id uuid PRIMARY KEY);CREATE TABLE public.tasks(id uuid PRIMARY KEY);');
  const dir=new URL('../../frontend/supabase/migrations/',import.meta.url);const file=fs.readdirSync(dir).find(x=>x.endsWith('_daily_list_ingestion.sql'));
  await db.exec(fs.readFileSync(new URL(file,dir),'utf8'));
  const {rows}=await db.query("select relname,relrowsecurity from pg_class join pg_namespace on pg_namespace.oid=relnamespace where nspname='wholesale_ingest' and relkind='r'");
  assert.ok(rows.length>=10);assert.ok(rows.every(x=>x.relrowsecurity));
  await db.exec("INSERT INTO wholesale_ingest.sources(source_key,state,county,jurisdiction,list_type,method,source_url,allowed_hosts,lookback_days,backfill_days,schedule_cron) VALUES('tx-dallas-pre_foreclosure','TX','Dallas','Dallas County','pre_foreclosure','browser','https://www.dallascounty.org',ARRAY['www.dallascounty.org'],30,30,'0 5 * * *')");
  await assert.rejects(()=>db.exec("UPDATE wholesale_ingest.sources SET county='Denton'"));
  await assert.rejects(()=>db.exec("UPDATE wholesale_ingest.sources SET backfill_days=31"));
  await db.exec("INSERT INTO wholesale_ingest.properties(state,county,parcel_id) VALUES('TX','Dallas','001')");
  await assert.rejects(()=>db.exec("INSERT INTO wholesale_ingest.properties(state,county,parcel_id) VALUES('TX','Dallas','001')"));
  await db.exec("INSERT INTO wholesale_ingest.properties(state,county,parcel_id) VALUES('TX','Collin','001')");
  await db.exec('SET ROLE wholesale_ingestor');
  assert.equal((await db.query('select * from wholesale_ingest.sources')).rows.length,1);
  await assert.rejects(()=>db.exec("UPDATE wholesale_ingest.sources SET enabled=true"));
  await assert.rejects(()=>db.exec("INSERT INTO public.leads VALUES(gen_random_uuid())"));
  await assert.rejects(()=>db.query('select * from wholesale_ingest.contacts'));
  await db.exec('RESET ROLE;SET ROLE anon');await assert.rejects(()=>db.query('select * from wholesale_ingest.sources'));
  await db.exec('RESET ROLE;SET ROLE authenticated');await assert.rejects(()=>db.query('select * from wholesale_ingest.raw_payloads'));
 } finally {await db.close();}
});
