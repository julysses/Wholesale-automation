import postgres from 'npm:postgres@3.4.5';
export async function verifyScoringConcurrency(adminURL:string){
 const admin=postgres(adminURL,{ssl:'require',max:1});
 const one=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'score-claim-one'}});
 const two=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'score-claim-two'}});
 const lead=crypto.randomUUID(),property=crypto.randomUUID(),run=crypto.randomUUID(),signal=crypto.randomUUID(),job=crypto.randomUUID();
 const assert=(v:unknown,m:string)=>{if(!v)throw new Error(m);};
 let locked=false;
 try{
  for(const file of ['20261012231220_list_scoring_receipts.sql','20261012232054_list_scoring_jobs.sql','20261012232711_list_scoring_monitor.sql'])
   await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/'+file,import.meta.url)));
  await admin`insert into public.leads(id,property_address,city) values(${lead},'SYNTHETIC SCORE TEST','Dallas')`;
  await admin`insert into wholesale_ingest.properties(id,state,county,address_std,lead_id) values(${property},'TX','Dallas',${lead},${lead})`;
  await admin`insert into wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
   select ${run},id,current_date,now(),'success','synthetic',repeat('a',64),1 from wholesale_ingest.sources where source_key='tx-dallas-pre_foreclosure'`;
  await admin`insert into wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id)
   select ${signal},${property},source_id,'synthetic','pre_foreclosure',current_date,'https://example.invalid/fixture',${run},${run} from wholesale_ingest.ingest_runs where id=${run}`;
  await admin`select public.prepare_list_score_job(${job},${lead},'claude-fixture')`;
  await one.unsafe('SET ROLE service_role');await two.unsafe('SET ROLE service_role');
  await admin.unsafe('BEGIN');locked=true;
  await admin`select id from wholesale_ingest.scoring_jobs where id=${job} for update`;
  const pending=[one`select public.claim_list_score_job(${job}) AS receipt`.execute(),two`select public.claim_list_score_job(${job}) AS receipt`.execute()];
  let waiters:{pid:number}[]=[];
  for(let i=0;i<100;i++){
   await admin`select pg_stat_clear_snapshot()`;
   waiters=await admin`select pid from pg_stat_activity where application_name in ('score-claim-one','score-claim-two') and wait_event_type='Lock'`;
   if(waiters.length===2)break;
   await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Two scoring claims must overlap on a real row lock');
  console.log('Verified overlapping scoring claim backend PIDs:',waiters.map(r=>r.pid).join(','));
  await admin.unsafe('COMMIT');locked=false;
  const results=(await Promise.all(pending)).map(rows=>rows[0].receipt);
  assert(results.filter(r=>r.dispatch===true).length===1&&results.filter(r=>r.dispatch===false).length===1,'Duplicate scoring dispatch');
  const [retry]=await two`select public.claim_list_score_job(${job}) AS receipt`;
  assert(retry.receipt.dispatch===false,'Uncertain scoring job redispatched');
  const received=results.find(r=>r.dispatch).job;
  const part=(points:number,ids:string[]=[])=>({points,reason:'Synthetic evidence',evidence_ids:ids});
  const result={components:{distress_stack:part(7,[signal]),need_to_sell:part(0),equity:part(0),contactability:part(0),recency:part(0)},needs_to_sell:'unknown'};
  await one`select public.receive_list_score_job(${job},${received.claim_token},'claude-fixture','msg-fixture',${one.json(result)})`;
  const [completed]=await two`select public.complete_list_score_job(${job}) AS receipt`;
  assert(completed.receipt.evaluation.score===7&&completed.receipt.job.state==='completed','Saved scoring receipt did not recover');
  console.log('PASS actual simultaneous scoring claims and model-free receipt recovery; no model invoked');
 }finally{
  if(locked)await admin.unsafe('ROLLBACK');
  await Promise.all([one.end(),two.end(),admin.end()]);
 }
}
