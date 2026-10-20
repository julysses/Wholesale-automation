import postgres from 'npm:postgres@3.4.5';
export async function verifyOfferConcurrency(adminURL:string){
 const admin=postgres(adminURL,{ssl:'require',max:1});
 const one=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'offer-contention-one'}});
 const two=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'offer-contention-two'}});
 const lead=crypto.randomUUID(),actor=crypto.randomUUID(),revision=crypto.randomUUID();
 const firstID=crypto.randomUUID(),secondID=crypto.randomUUID();
 const key='offer-lead:'+lead;
 const assert=(ok:unknown,message:string)=>{if(!ok)throw new Error(message);};
 let locked=false;
 try{
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261020163157_integration_human_offer_review.sql',import.meta.url)));
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261020163211_integration_offer_content_binding.sql',import.meta.url)));
  await admin`insert into public.profiles(id,role,status) values(${actor},'admin','approved')`;
  await admin`insert into public.leads(id,property_address,city) values(${lead},'SYNTHETIC CONCURRENT OFFER TEST','Dallas')`;
  await admin.unsafe('GRANT SELECT ON public.profiles,public.leads TO service_role; GRANT UPDATE ON public.leads TO service_role');
  await one.unsafe('SET ROLE service_role');await two.unsafe('SET ROLE service_role');
  const terms={price:'125000',closing_date:'2099-12-31',expires_at:'2099-10-01T00:00:00Z',recipient:'fixture@example.invalid',channel:'email',conditions:'Synthetic only; never send'};
  await one`select public.record_offer_review_v2(${revision},${lead},${actor},0,'draft',${revision},${one.json(terms)},NULL)`;
  await admin`select pg_advisory_lock(hashtextextended(${key},0))`;locked=true;
  const approve=(db:ReturnType<typeof postgres>,id:string)=>db`select public.record_offer_review_v2(${id},${lead},${actor},1,'approve',${revision},NULL,${revision}) AS receipt`.execute();
  const first=approve(one,firstID),second=approve(two,secondID);
  let waiters:{pid:number}[]=[];
  for(let i=0;i<100;i++){
   waiters=await admin`select pid from pg_stat_activity where application_name in ('offer-contention-one','offer-contention-two') and wait_event_type='Lock' and wait_event='advisory'`;
   if(waiters.length===2)break;
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Offer decisions must overlap on independent PostgreSQL sessions');
  console.log('Verified overlapping offer decision backend PIDs:',waiters.map(r=>r.pid).join(','));
  await admin`select pg_advisory_unlock(hashtextextended(${key},0))`;locked=false;
  const receipts=(await Promise.all([first,second])).map(rows=>rows[0].receipt);
  assert(receipts.filter(r=>r.conflict).length===1&&receipts.filter(r=>r.event).length===1,'Exactly one concurrent offer decision must win');
  const [count]=await admin`select count(*)::int n from offer_review.events where lead_id=${lead}`;
  assert(count.n===2,'Losing decision must not append an event');
  const winner=receipts.find(r=>r.event).event.id;
  await one`select public.record_offer_review_v2(${crypto.randomUUID()},${lead},${actor},2,'revoke',${revision},NULL,NULL)`;
  const [replayed]=await one`select public.record_offer_review_v2(${winner},${lead},${actor},1,'approve',${revision},NULL,${revision}) AS receipt`;
  assert(replayed.receipt.replayed===true&&replayed.receipt.current.approved===false,'Old approval replay must not restore revoked approval');
  await admin.unsafe('BEGIN');
  await admin`update public.leads set city='CHANGED WHILE APPROVING' where id=${lead}`;
  const changed=one`select public.record_offer_review_v2(${crypto.randomUUID()},${lead},${actor},3,'approve',${revision},NULL,${revision}) AS receipt`.execute();
  let propertyWait=false;
  for(let i=0;i<100;i++){
   const waiting=await admin`select pid from pg_stat_activity where application_name='offer-contention-one' and wait_event_type='Lock'`;
   if(waiting.length){propertyWait=true;break;}
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  await admin.unsafe('COMMIT');
  const [changedResult]=await changed;
  assert(propertyWait&&changedResult.receipt.conflict===true,'Approval must wait for concurrent property edit and reject the changed identity');
  console.log('PASS property update contention: approval waits, rechecks committed identity, and rejects stale content');
  console.log('PASS actual overlapping offer decisions: one winner, one conflict, no duplicate event, revoked approval stays revoked on replay');
 }finally{
  if(locked)await admin`select pg_advisory_unlock(hashtextextended(${key},0))`;
  await Promise.all([one.end(),two.end(),admin.end()]);
 }
}
