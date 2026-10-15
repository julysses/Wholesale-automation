import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';

test('audited situs enrichment preserves county facts, rejects stale/conflicting review and deduplicates sources',async()=>{
 const db=new PGlite();
 try{
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
   CREATE TABLE public.profiles(id uuid PRIMARY KEY,role text,status text);
   CREATE TABLE public.leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),property_address text,city text,state text,zip_code text,source text,motivation_tag text,status text,owner_mailing_address text,sms_sequence_active boolean,email_sequence_active boolean);
   CREATE TABLE public.tasks(id uuid PRIMARY KEY,title text,description text,status text,priority text,type text,assigned_to uuid,due_date timestamptz);
   CREATE TABLE public.app_settings(key text,value text);`);
  const dir=new URL('../../frontend/supabase/migrations/',import.meta.url);
  for(const suffix of ['_daily_list_ingestion.sql','_list_operations.sql','_list_review_batch_guard.sql','_list_reviewed_identity.sql']){
   await db.exec(fs.readFileSync(new URL(fs.readdirSync(dir).find(x=>x.endsWith(suffix)),dir),'utf8'));
  }
  const owner='00000000-0000-4000-8000-000000000001';
  await db.query("INSERT INTO public.profiles VALUES($1,'admin','approved')",[owner]);
  const seed=async(type,n)=>{
   const run=`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
   await db.query(`INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
    SELECT $1,id,current_date,now(),'partial','synthetic review',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key=$2`,[run,`tx-dallas-${type}`]);
   await db.query(`INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in) VALUES($1,0,repeat('b',64),repeat('c',64),'{}',1)`,[run]);
   const record={source_record_id:`synthetic-${n}`,property_address:null,city:null,state:'TX',zip:null,filed_date:'2026-10-13',mailing_address:'999 Mailing Only Road',raw:{snapshot_only:true},source_url:'https://www.dallascounty.org/synthetic',amount_owed:null};
   await db.query(`INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record,review_reason) VALUES($1,0,0,$2,$3,'verify_county_property_evidence')`,[run,record.source_record_id,JSON.stringify(record)]);
   const hash=(await db.query('SELECT md5(record::text) h FROM wholesale_ingest.records WHERE run_id=$1',[run])).rows[0].h;
   return {run,record,review:{source_fingerprint:hash,notes:'Synthetic official situs match reviewed.',identity:{property_address:'1 Synthetic Site',city:'Dallas',state:'TX',zip:'75201',parcel_id:'synthetic-parcel',unit:null}}};
  };
  const a=await seed('tax_delinquent',2),b=await seed('pre_foreclosure',3);
  const resolve=(f,review=f.review,lead=null,actor=owner)=>db.query('SELECT public.resolve_reviewed_list_record($1,0,0,$2,$3,$4,$5,false,$6) result',[f.run,actor,'Dallas','https://www.dallascad.org/synthetic',lead,JSON.stringify(review)]);
  await assert.rejects(()=>resolve(a,{...a.review,source_fingerprint:'0'.repeat(32)}),/Current source fingerprint/);
  await assert.rejects(()=>resolve(a,{...a.review,identity:{...a.review.identity,amount_owed:100}}),/Verified Texas situs/);
  await assert.rejects(()=>resolve(a,{...a.review,identity:{...a.review.identity,zip:null}}),/Verified Texas situs/);
  await assert.rejects(()=>resolve(a,a.review,null,'00000000-0000-4000-8000-000000000099'),/Approved administrator/);
  await db.exec("UPDATE wholesale_ingest.raw_payloads SET expires_at=now()-interval '1 second'");
  await assert.rejects(()=>resolve(a),/Complete unexpired/);
  await db.exec("UPDATE wholesale_ingest.raw_payloads SET expires_at=now()+interval '90 days'");
  const first=(await resolve(a)).rows[0].result;
  assert.equal(first.new_lead,true); assert.equal(first.outreach_authorized,false);
  assert.equal((await resolve(a)).rows[0].result.replayed,true);
  await assert.rejects(()=>resolve(a,{...a.review,notes:'Changed evidence after resolution.'}),/different review evidence/);
  const second=(await resolve(b)).rows[0].result;
  assert.equal(second.new_lead,false); assert.equal(second.lead_id,first.lead_id);assert.equal(second.property_id,first.property_id);
  assert.equal((await db.query('SELECT count(*)::int n FROM public.leads')).rows[0].n,1);
  const original=(await db.query('SELECT record FROM wholesale_ingest.records WHERE run_id=$1',[a.run])).rows[0].record;
  assert.deepEqual(original,a.record);
  const audit=(await db.query('SELECT review_details FROM wholesale_ingest.review_events WHERE run_id=$1',[a.run])).rows[0].review_details;
  assert.deepEqual(audit.review,a.review);
  const lead=(await db.query('SELECT * FROM public.leads')).rows[0];
  assert.equal(lead.property_address,'1 Synthetic Site'); assert.equal(lead.owner_mailing_address,'999 Mailing Only Road');
  assert.equal(lead.sms_sequence_active,false);assert.equal(lead.email_sequence_active,false);
  const c=await seed('tax_delinquent',4);
  await assert.rejects(()=>resolve(c,{...c.review,identity:{...c.review.identity,property_address:'2 Other Site'}},first.lead_id),/does not match/);
  await db.exec('SET ROLE authenticated');
  await assert.rejects(()=>resolve(c),/permission denied/);
 }finally{await db.close();}
});
