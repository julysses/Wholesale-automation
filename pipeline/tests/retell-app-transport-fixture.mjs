import fs from 'node:fs';
const read=name=>fs.readFileSync(new URL('../../frontend/supabase/migrations/'+name,import.meta.url),'utf8');
export const job='00000000-0000-4000-8000-000000000001', native='00000000-0000-4000-8000-000000000002';
export const phone='+12145550196',sender='+14695550100', sid='SM'+'a'.repeat(32);
export async function fixture(db){
 await db.exec(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role BYPASSRLS;
 CREATE TABLE public.leads(id uuid PRIMARY KEY,dnc boolean DEFAULT false,status text DEFAULT 'new',ai_calling_paused boolean DEFAULT false);
 CREATE TABLE public.lead_form_submissions(id uuid PRIMARY KEY);
 CREATE TABLE public.sms_events(id uuid PRIMARY KEY,lead_id uuid,provider text,direction text,phone_number text,body text,status text,raw_payload jsonb,opt_out boolean,created_at timestamptz DEFAULT now());
 CREATE TABLE public.retell_call_requests(id uuid,phone_number text,status text,created_at timestamptz);
 CREATE TABLE public.test_suppression(phone text PRIMARY KEY);
 CREATE FUNCTION public.intake_phone_status(text,uuid,text) RETURNS jsonb LANGUAGE sql AS $$ SELECT jsonb_build_object('suppressed',exists(select 1 from public.test_suppression where phone=$1)) $$;
 CREATE FUNCTION public.sms_stop_has_reviewed_opt_in(uuid) RETURNS boolean LANGUAGE sql AS $$ SELECT false $$;`);
 await db.exec(read('20261008202609_retell_call_batches.sql').split('CREATE TABLE public.retell_call_batches')[0]);
 await db.exec(read('20261015192903_retell_form_sms_production.sql').split('-- Cloud trigger only')[0]);
 await db.exec(read('20261017000257_scope_retell_sms_claims.sql'));
 await db.exec(`INSERT INTO public.leads(id) VALUES('00000000-0000-4000-8000-000000000999');
 INSERT INTO public.lead_form_submissions VALUES('00000000-0000-4000-8000-000000000999');
 INSERT INTO public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at,status,chat_id,reason)
 VALUES('00000000-0000-4000-8000-000000000999','00000000-0000-4000-8000-000000000999','00000000-0000-4000-8000-000000000999',
 '+12145550198',now()-interval '2 days',now()-interval '1 day','accepted','chat_legacy','Original native provider receipt');`);
 await db.exec(read('20261017012707_retell_app_transport_ownership.sql'));
 for(const [id,transport,number] of [[job,'app_twilio',phone],[native,'retell_native','+12145550197']]){
  await db.query('insert into public.leads(id) values($1)',[id]);await db.query('insert into public.lead_form_submissions values($1)',[id]);
  await db.query(`insert into public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at,created_at,delivery_transport,delivery_body,delivery_sender)
   values($1,$1,$1,$2,now()-interval '1 minute',now()+interval '10 minutes',now()-interval '2 minutes',$3,$4,$5)`,
   [id,number,transport,transport==='app_twilio'?'Thanks for your property inquiry. Reply STOP to opt out.':null,transport==='app_twilio'?sender:null]);
 }
 const q=async(sql,args=[])=>(await db.query(sql,args)).rows;
 const rpc=async(name,args)=>{const placeholders=args.map((_,i)=>'$'+(i+1));return (await q(`select public.${name}(${placeholders.join(',')}) result`,args))[0].result;};
 const ack=async()=>{
  await q('select id from public.claim_retell_app_ack($1)',[job]);
  await q("update public.sms_events set created_at=now()-interval '10 seconds',status='accepted',raw_payload=raw_payload||jsonb_build_object('provider_sid',$2::text) where id=$1",[job,sid]);
  await q("update public.retell_form_sms_jobs set status='accepted' where id=$1",[job]);
 };
 const inbound=async(id=crypto.randomUUID(),patch={})=>{
  const payload={MessageSid:'SM'+id.replaceAll('-',''),From:phone,To:sender,Body:'  Can Julio call tomorrow?\nThanks. ',crm_opt_out:false,...patch};
  await q(`insert into public.sms_events(id,lead_id,provider,direction,phone_number,body,status,raw_payload,opt_out,created_at)
   values($1,$2,'twilio','inbound',$3,$4,'replied',$5,false,now()-interval '1 second')`,[id,job,phone,payload.Body,JSON.stringify(payload)]);return id;
 };
 return {db,q,rpc,ack,inbound};
}
