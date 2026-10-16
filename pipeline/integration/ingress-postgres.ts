// Real PostgreSQL/TLS integration; refuse all remote hosts and non-test databases.
import postgres from 'npm:postgres@3.4.5';
import {verifyTraceConcurrency} from './trace-concurrency.ts';
import {verifyScoringConcurrency} from './scoring-concurrency.ts';
import {canonicalJSON,sha256} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';
import fixture from '../fixtures/synthetic.json' with {type:'json'};
import coverageFixture from '../fixtures/synthetic-coverage.json' with {type:'json'};
const adminURL=Deno.env.get('INGRESS_TEST_ADMIN_URL')||'';
const url=new URL(adminURL);
if(url.hostname!=='127.0.0.1'||url.pathname!=='/wholesale_ingress_test')throw new Error('Local disposable test database required');
const admin=postgres(adminURL,{ssl:'require',max:1});
const locker=postgres(adminURL,{ssl:'require',max:1});
const assert=(ok:unknown,message:string)=>{if(!ok)throw new Error(message);};
const pause=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
const token='local-synthetic-ingress-token-not-a-real-secret';
let locked=false;
const run=crypto.randomUUID();
try{
 await admin.unsafe(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role BYPASSRLS;
 CREATE TABLE public.profiles(id uuid PRIMARY KEY,role text,status text);
 CREATE TABLE public.leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),property_address text,city text,state text,zip_code text,source text,motivation_tag text,status text,owner_mailing_address text,sms_sequence_active boolean,email_sequence_active boolean);
 CREATE TABLE public.tasks(id uuid PRIMARY KEY,title text,description text,status text,priority text,type text,assigned_to uuid,due_date timestamptz);
 CREATE TABLE public.app_settings(key text,value text);`);
 for(const file of ['20261012174408_daily_list_ingestion.sql','20261012174446_list_operations.sql','20261012201949_list_review_batch_guard.sql','20261012205453_list_monitor_receipts.sql','20261013195311_foreclosure_daily_actions.sql','20261016210114_restricted_collector_login.sql']){
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/'+file,import.meta.url)));
 }
 // Exercise the production role definition, including inherited RLS grants and
 // the notice-history trigger. Credentials below exist only in this disposable DB.
 await admin.unsafe("ALTER ROLE wholesale_ingest_edge LOGIN PASSWORD 'local-only-fixture'");
 await admin`update wholesale_ingest.sources set enabled=true where source_key=${fixture.source_key}`;
 const restrictedURL=new URL(adminURL);restrictedURL.username='wholesale_ingest_edge';restrictedURL.password='local-only-fixture';
 Deno.env.set('INGEST_DATABASE_URL',restrictedURL.toString());
 Deno.env.set('INGEST_TOKEN_CONFIG',JSON.stringify({test:{sha256:await sha256(token),source_keys:[fixture.source_key],expires_at:'2099-01-01T00:00:00Z'}}));
 // Separate module instances model separate Edge workers with independent pools.
 const one=await import('../../frontend/supabase/functions/daily-list-ingest/index.ts?worker=one');
 const two=await import('../../frontend/supabase/functions/daily-list-ingest/index.ts?worker=two');
 const payload={...fixture,run_id:run,pulled_at:new Date().toISOString(),coverage:{...coverageFixture,run_id:run}};
 const request=(body:unknown)=>new Request('https://local-ingress.invalid',{method:'POST',headers:{'Content-Type':'application/json','X-Ingest-Key-Id':'test',Authorization:'Bearer '+token},body:JSON.stringify(body)});
 await locker`select pg_advisory_lock(hashtextextended(${run},0))`;locked=true;
 const first=one.handler(request(payload)),second=two.handler(request(payload));
 let waiters: {pid:number}[]=[];
 for(let i=0;i<100;i++){
  waiters=await admin`select pid from pg_stat_activity where usename='wholesale_ingest_edge' and wait_event_type='Lock' and wait_event='advisory'`;
  if(waiters.length===2)break;
  await pause(50);
 }
 assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Two actual PostgreSQL sessions must overlap on the same advisory lock');
 console.log('Verified two independent waiting backend PIDs:',waiters.map(r=>r.pid).join(','));
 await locker`select pg_advisory_unlock(hashtextextended(${run},0))`;locked=false;
 const responses=await Promise.all([first,second]);
 const statuses=responses.map(r=>r.status).sort();
 const receipts=await Promise.all(responses.map(r=>r.json()));
 assert(JSON.stringify(statuses)==='[200,202]',`Concurrent results: ${JSON.stringify({statuses,receipts})}`);
 assert(receipts.every(r=>r.run_id===run)&&receipts.filter(r=>r.replayed).length===1,'Exact durable replay acknowledgement');
 const counts=await admin`select (select count(*)::int from wholesale_ingest.ingest_runs) runs,(select count(*)::int from wholesale_ingest.raw_payloads) batches,(select count(*)::int from wholesale_ingest.records) records,(select count(*)::int from wholesale_ingest.jobs) jobs`;
 assert(JSON.stringify(counts[0])==='{"runs":1,"batches":1,"records":1,"jobs":1}','Concurrent duplicate produced extra data');
 const [evidence]=await admin`select payload->'coverage'->>'run_id' as ledger_run from wholesale_ingest.raw_payloads where run_id=${run}`;
 assert(evidence.ledger_run===run,'Coverage must be durably stored with the exact payload');
 const replay=await one.handler(request(payload));assert(replay.status===200,'Lost acknowledgement retry must replay');
 const [notice]=await admin`select count(*)::int receipts from wholesale_ingest.foreclosure_first_seen where source_record_id=${payload.records[0].source_record_id}`;
 assert(notice.receipts===1,'Restricted insert and retries must preserve one notice-history receipt');
 const changed=structuredClone(payload);changed.records[0].case_number='CHANGED';changed.records_sha256=await sha256(canonicalJSON(changed.records));changed.coverage.records_sha256=changed.records_sha256;
 assert((await two.handler(request(changed))).status===409,'Changed duplicate payload must conflict');
 await admin`update wholesale_ingest.raw_payloads set expires_at=now()-interval '1 second' where run_id=${run}`;
 assert((await one.handler(request(payload))).status===410,'Expired replay must fail closed');
 const disabled=structuredClone(payload);disabled.run_id=crypto.randomUUID();disabled.coverage.run_id=disabled.run_id;
 await admin`update wholesale_ingest.sources set enabled=false where source_key=${fixture.source_key}`;
 assert((await two.handler(request(disabled))).status===403,'Disabled source must reject successful-shape payload');
 const restricted=postgres(restrictedURL.toString(),{ssl:'require',max:1});
 try{
  const [role]=await restricted`select current_user,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls,rolconnlimit from pg_roles where rolname=current_user`;
  assert(role.current_user==='wholesale_ingest_edge'&&!role.rolsuper&&!role.rolcreaterole&&!role.rolcreatedb&&!role.rolbypassrls&&role.rolconnlimit===4,'Production intake role must retain its restricted privileges');
  for(const query of ['select * from public.leads','select * from wholesale_ingest.contacts',"update wholesale_ingest.sources set enabled=true",'delete from wholesale_ingest.records']){
   let denied=false;try{await restricted.unsafe(query);}catch(e){denied=(e as {code:string}).code==='42501';}
   assert(denied,'Restricted ingress role exceeded its grants');
  }
 }finally{await restricted.end();}
 await verifyTraceConcurrency(adminURL);
 await verifyScoringConcurrency(adminURL);
 console.log('PASS actual ingress success, overlapping duplicate requests, lost-ACK replay, conflict, expiry, disabled source and restricted-role checks');
}finally{
 if(locked)await locker`select pg_advisory_unlock(hashtextextended(${run},0))`;
 await locker.end();await admin.end();
}
Deno.exit(0);
