import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {PGlite} from '@electric-sql/pglite';

const root=new URL('../../',import.meta.url);
const read=file=>fs.readFileSync(new URL('frontend/supabase/migrations/'+file,root),'utf8');

test('scoped Retell claims retain guards and never consume another job',async t=>{
 const db=new PGlite();t.after(()=>db.close());
 await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
 CREATE TABLE public.leads(id uuid PRIMARY KEY);
 CREATE TABLE public.lead_form_submissions(id uuid PRIMARY KEY);
 CREATE TABLE public.sms_events(id uuid PRIMARY KEY,lead_id uuid,provider text,direction text,phone_number text,body text,status text,raw_payload jsonb,opt_out boolean,created_at timestamptz DEFAULT now());
 CREATE TABLE public.retell_call_requests(id uuid,phone_number text,status text,created_at timestamptz);
 CREATE TABLE public.test_suppression(phone text PRIMARY KEY);
 CREATE FUNCTION public.intake_phone_status(text,uuid,text) RETURNS jsonb LANGUAGE sql AS $$ SELECT jsonb_build_object('suppressed',exists(select 1 from public.test_suppression where phone=$1)) $$;
 CREATE FUNCTION public.sms_stop_has_reviewed_opt_in(uuid) RETURNS boolean LANGUAGE sql AS $$ SELECT false $$;`);
 await db.exec(read('20261015192903_retell_form_sms_production.sql').split('-- Cloud trigger only')[0]);
 await db.exec(read('20261017000257_scope_retell_sms_claims.sql'));
 const q=async(sql,args=[])=>(await db.query(sql,args)).rows;
 const target='00000000-0000-4000-8000-000000000001';
 const other='00000000-0000-4000-8000-000000000002';
 const missing='00000000-0000-4000-8000-000000000003';
 for(const id of [target,other]) {
  await db.query('insert into public.leads values($1)',[id]);
  await db.query('insert into public.lead_form_submissions values($1)',[id]);
  await db.query(`insert into public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at) values($1,$1,$1,$2,now()-interval '1 minute',now()+interval '10 minutes')`,[id,id===target?'+12145550196':'+12145550197']);
 }
 const claim=(id)=>q('select id from public.claim_retell_form_sms_matching(10,$1)',[id]);
 assert.deepEqual(await claim(missing),[]);
 assert.deepEqual(await claim(target),[{id:target}]);
 assert.deepEqual(await claim(target),[],'No duplicate claim');
 assert.deepEqual(await q('select id,status from public.retell_form_sms_jobs where id=$1',[other]),[{id:other,status:'scheduled'}]);
 assert.deepEqual(await q('select id from public.sms_events'),[{id:target}]);
 // Actual production contact-limit function and the shared no-replay checks.
 for(const blocker of ['future','expired','suppressed','unknown','recent','limit','review','accepted','processing','stop']) {
  await db.exec('delete from public.sms_events; delete from public.test_suppression; delete from public.retell_call_requests;');
  await db.query(`update public.retell_form_sms_jobs set status='scheduled',due_at=now()-interval '1 minute',expires_at=now()+interval '10 minutes',phone_number=case when id=$1 then '+12145550196' else '+12145550197' end`,[target]);
  if(blocker==='future') await db.query("update public.retell_form_sms_jobs set due_at=now()+interval '1 minute' where id=$1",[target]);
  if(blocker==='expired') await db.query("update public.retell_form_sms_jobs set expires_at=now()-interval '1 minute' where id=$1",[target]);
  if(blocker==='suppressed') await db.exec("insert into public.test_suppression values('+12145550196')");
  if(['review','accepted','processing'].includes(blocker)) await db.query("update public.retell_form_sms_jobs set status=$2,phone_number='+12145550196' where id=$1",[other,blocker]);
  if(['unknown','recent','limit','stop'].includes(blocker)) {
   const status=blocker==='unknown'?'unknown':'accepted';
   const age=blocker==='recent'?'1 hour':'2 days';
   await db.query(`insert into public.sms_events(id,provider,direction,phone_number,status,created_at,opt_out) values(gen_random_uuid(),'twilio',$1,'+12145550196',$2,now()-$3::interval,$4)`,[blocker==='stop'?'inbound':'outbound',status,age,blocker==='stop']);
   if(blocker==='limit') await db.exec("insert into public.sms_events(id,provider,direction,phone_number,status,created_at) values(gen_random_uuid(),'twilio','outbound','+12145550196','accepted',now()-interval '3 days')");
  }
  const before=await q('select * from public.retell_form_sms_jobs where id=$1',[other]);
  assert.deepEqual(await claim(target),[],blocker+' must block');
  assert.deepEqual(await q('select * from public.retell_form_sms_jobs where id=$1',[other]),before,blocker+' must not touch unrelated job');
 }
 await db.exec('delete from public.sms_events;');
 await db.query("update public.retell_form_sms_jobs set status='scheduled',phone_number=case when id=$1 then '+12145550196' else '+12145550197' end",[target]);
 assert.equal((await q('select id from public.claim_retell_form_sms(1)')).length,1,'Original batch interface still works');
 for(const role of ['anon','authenticated']) assert.equal((await q(`select has_function_privilege($1,'public.claim_retell_form_sms_matching(integer,uuid)','EXECUTE') allowed`,[role]))[0].allowed,false);
 assert.equal((await q("select prosecdef from pg_proc where oid='public.claim_retell_form_sms_matching(integer,uuid)'::regprocedure"))[0].prosecdef,false);
});
