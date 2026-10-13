import postgres from 'npm:postgres@3.4.5';
export async function verifyTraceConcurrency(adminURL:string){
 const admin=postgres(adminURL,{ssl:'require',max:1});
 const one=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'trace-budget-one'}});
 const two=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'trace-budget-two'}});
 const leads=[crypto.randomUUID(),crypto.randomUUID()],ids=[crypto.randomUUID(),crypto.randomUUID()];
 const assert=(v:unknown,m:string)=>{if(!v)throw new Error(m);};
 let locked=false;
 try{
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261012224412_list_trace_budget.sql',import.meta.url)));
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261012225103_list_trace_contacts.sql',import.meta.url)));
  await admin.unsafe('ALTER TABLE public.leads ADD COLUMN owner_first_name text');
  for(const lead of leads){
   await admin`insert into public.leads(id,property_address,city,owner_first_name) values(${lead},'SYNTHETIC TRACE TEST','Dallas','Synthetic')`;
   await admin`insert into wholesale_ingest.properties(state,county,address_std,lead_id) values('TX','Dallas',${lead},${lead})`;
  }
  await admin`insert into wholesale_ingest.daily_budgets(spend_day,cap_cents) values((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,100)`;
  await admin.unsafe('GRANT SELECT,UPDATE ON public.leads TO service_role');
  await one.unsafe('SET ROLE service_role');await two.unsafe('SET ROLE service_role');
  await admin.unsafe('BEGIN');locked=true;
  await admin`select * from wholesale_ingest.daily_budgets for update`;
  const reserve=(db:ReturnType<typeof postgres>,i:number)=>db`select public.prepare_list_trace(${ids[i]},${leads[i]},'synthetic',80) AS receipt`.execute();
  const pending=[reserve(one,0),reserve(two,1)];
  let waiters:{pid:number}[]=[];
  for(let i=0;i<100;i++){
   await admin`select pg_stat_clear_snapshot()`;
   waiters=await admin`select pid from pg_stat_activity where application_name in ('trace-budget-one','trace-budget-two') and wait_event_type='Lock'`;
   if(waiters.length===2)break;
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Two trace reservations must overlap on real budget lock');
  console.log('Verified overlapping trace budget backend PIDs:',waiters.map(r=>r.pid).join(','));
  await admin.unsafe('COMMIT');locked=false;
  const results=(await Promise.all(pending)).map(rows=>rows[0].receipt);
  assert(results.filter(r=>r.request).length===1&&results.filter(r=>r.blocked==='daily_cap').length===1,'Concurrent reservations exceeded daily cap');
  const [budget]=await admin`select reserved_cents,actual_cents from wholesale_ingest.daily_budgets`;
  assert(budget.reserved_cents===80&&budget.actual_cents===0,'Unexpected budget accounting');
  const winning=results.find(r=>r.request).request;
  const winner=winning.id,hash=winning.input_hash;
  await one`select public.claim_list_trace(${winner},${hash})`;
  await one`select public.settle_list_trace(${winner},'unknown',NULL,NULL,NULL)`;
  const [held]=await admin`select reserved_cents from wholesale_ingest.daily_budgets`;
  assert(held.reserved_cents===80,'Unknown outcome released reserved money');
  const [retry]=await two`select public.claim_list_trace(${winner},${hash}) AS receipt`;
  assert(retry.receipt.dispatch===false,'Unknown provider outcome permitted resend');
  const contacts=[{phone:'+12145550198',phone_type:'mobile'}];
  const [complete]=await one`select public.complete_list_trace(${winner},'synthetic',${hash},50,'synthetic-confirmed-receipt',${one.json(contacts)}) AS receipt`;
  assert(complete.receipt.contacts_saved===1&&complete.receipt.request.actual_cents===50,'Contact/billing receipt failed');
  for(const file of ['20261012225802_list_trace_operations.sql','20261013164454_list_trace_total_cap.sql'])
   await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/'+file,import.meta.url)));
  await admin`update wholesale_ingest.daily_budgets set cap_cents=10000`;
  const fresh=[crypto.randomUUID(),crypto.randomUUID()];
  for(const lead of fresh){
   await admin`insert into public.leads(id,property_address,city,owner_first_name) values(${lead},'SYNTHETIC TOTAL CAP','Dallas','Synthetic')`;
   await admin`insert into wholesale_ingest.properties(state,county,address_std,lead_id) values('TX','Dallas',${lead},${lead})`;
  }
  await admin.unsafe('BEGIN');locked=true;
  await admin`select pg_advisory_xact_lock(hashtextextended('trace-total-cap-v1',0))`;
  const totalPending=[one,two].map((db,i)=>db`select public.prepare_list_trace(${crypto.randomUUID()},${fresh[i]},'synthetic',3000) AS receipt`.execute());
  for(let i=0;i<100;i++){
   await admin`select pg_stat_clear_snapshot()`;
   waiters=await admin`select pid from pg_stat_activity where application_name in ('trace-budget-one','trace-budget-two') and wait_event_type='Lock'`;
   if(waiters.length===2)break;
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Total cap reservations must overlap on independent sessions');
  await admin.unsafe('COMMIT');locked=false;
  const totalResults=(await Promise.all(totalPending)).map(rows=>rows[0].receipt);
  assert(totalResults.filter(r=>r.request).length===1&&totalResults.filter(r=>r.blocked==='total_cap').length===1,'Concurrent reservations exceeded total authorization');
  const [total]=await admin`select public.list_trace_total_budget() AS receipt`;
  assert(total.receipt.committed_cents===3050&&total.receipt.remaining_cents===1950,'Total cap did not include settled spending');
  console.log('PASS real concurrent daily and cumulative trace caps and uncertain-outcome hold; no provider invoked');
 }finally{
  if(locked)await admin.unsafe('ROLLBACK');
  await Promise.all([one.end(),two.end(),admin.end()]);
 }
}
