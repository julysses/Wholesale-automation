import postgres from 'npm:postgres@3.4.5';
export async function verifyLotConcurrency(adminURL:string){
 const admin=postgres(adminURL,{ssl:'require',max:1});
 const one=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'lot-handoff-one'}});
 const two=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'lot-handoff-two'}});
 const lead=crypto.randomUUID(),property=crypto.randomUUID(),run=crypto.randomUUID(),signal=crypto.randomUUID(),actor=crypto.randomUUID(),owner=crypto.randomUUID(),evaluation=crypto.randomUUID();
 const assert=(v:unknown,m:string)=>{if(!v)throw new Error(m);};let locked=false;
 async function overlapping(){
  let waiters:{pid:number}[]=[];
  for(let i=0;i<100;i++){
   await admin`select pg_stat_clear_snapshot()`;
   waiters=await admin`select pid from pg_stat_activity where application_name in ('lot-handoff-one','lot-handoff-two') and wait_event_type='Lock'`;
   if(waiters.length===2)break;await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Two lot operations must contend simultaneously');
  console.log('Verified overlapping lot operation backend PIDs:',waiters.map(r=>r.pid).join(','));
 }
 try{
  await admin.unsafe(`CREATE TABLE public.land_leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),lead_id uuid,source text,owner_name text NOT NULL,property_address text,city text,state text,zip_code text,county text,apn text,status text,assigned_to uuid,sms_sequence_active boolean,offer_price numeric,mao numeric)`);
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261012235926_list_lot_handoff.sql',import.meta.url)));
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261013004341_list_lot_receiving_evidence.sql',import.meta.url)));
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261013013234_list_lot_worker.sql',import.meta.url)));
  await admin`insert into public.profiles(id,role,status) values(${actor},'admin','approved'),(${owner},'user','approved')`;
  await admin`insert into public.leads(id,property_address,city) values(${lead},'SYNTHETIC LOT','Dallas')`;
  await admin`insert into wholesale_ingest.properties(id,state,county,address_std,city,lead_id) values(${property},'TX','Dallas','SYNTHETIC LOT','Dallas',${lead})`;
  await admin`insert into wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches) select ${run},id,current_date,now(),'success','synthetic',repeat('a',64),1 from wholesale_ingest.sources where source_key='tx-dallas-pre_foreclosure'`;
  await admin`insert into wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id) select ${signal},${property},source_id,'synthetic','pre_foreclosure',current_date,'https://example.invalid/fixture',${run},${run} from wholesale_ingest.ingest_runs where id=${run}`;
  await admin`update wholesale_ingest.settings set score_threshold=7`;
  await one.unsafe('SET ROLE service_role');await two.unsafe('SET ROLE service_role');
  let [snapshot]=await one`select public.list_scoring_input(${lead}) value`;
  await one`select public.review_list_lot(${crypto.randomUUID()},${actor},${lead},${snapshot.value.input_hash},true,'https://example.invalid/lot','Verified synthetic lot')`;
  [snapshot]=await one`select public.list_scoring_input(${lead}) value`;
  const part=(points:number,ids:string[]=[])=>({points,reason:'Synthetic evidence',evidence_ids:ids});
  const result={components:{distress_stack:part(7,[signal]),need_to_sell:part(0),equity:part(0),contactability:part(0),recency:part(0)},needs_to_sell:'unknown'};
  await one`select public.save_list_score(${evaluation},${lead},${snapshot.value.input_hash},'claude-fixture','daily-list-score-v1','msg-lot',${one.json(result)})`;
  await admin.unsafe('BEGIN');locked=true;await admin`select id from wholesale_ingest.properties where id=${property} for update`;
  const requests=[one`select public.handoff_list_lot(${crypto.randomUUID()},${actor},${evaluation},${owner}) value`.execute(),two`select public.handoff_list_lot(${crypto.randomUUID()},${actor},${evaluation},${owner}) value`.execute()];
  await overlapping();await admin.unsafe('COMMIT');locked=false;
  const outputs=(await Promise.all(requests)).map(rows=>rows[0].value);
  assert(outputs.filter(x=>!x.blocked).length===1&&outputs.filter(x=>x.blocked==='existing_handoff').length===1,'Duplicate lot handoff');
  const saved=outputs.find(x=>!x.blocked).handoff;
  const [inbox]=await one`select public.list_lot_handoffs(${owner},0) value`;
  assert(inbox.value.handoffs.length===1&&inbox.value.handoffs[0].evidence_url==='https://example.invalid/lot'&&inbox.value.handoffs[0].score===7&&inbox.value.handoffs[0].scoring_input.lead_id===lead,'Assigned receiver evidence is missing or mismatched');
  const [count]=await admin`select count(*)::int n from public.land_leads where lead_id=${lead}`;assert(count.n===1,'Duplicate land record');
  await admin.unsafe('BEGIN');locked=true;await admin`select id from wholesale_ingest.lot_handoffs where id=${saved.id} for update`;
  const acks=[one`select public.acknowledge_list_lot(${saved.id},${actor}) value`.execute(),two`select public.acknowledge_list_lot(${saved.id},${owner}) value`.execute()];
  await overlapping();await admin.unsafe('COMMIT');locked=false;
  const received=(await Promise.all(acks)).map(rows=>rows[0].value);
  assert(received[0].handoff.acknowledged_by===received[1].handoff.acknowledged_by&&received.filter(x=>x.replayed).length===1,'Conflicting receiver acknowledgement');
  // New eligible lead: hold its property while a worker owns the global batch lock.
  const workerLead=crypto.randomUUID(),workerProperty=crypto.randomUUID(),workerEval=crypto.randomUUID(),workerSignal=crypto.randomUUID();
  await admin`insert into public.leads(id,property_address,city) values(${workerLead},'SYNTHETIC WORKER LOT','Dallas')`;
  await admin`insert into wholesale_ingest.properties(id,state,county,address_std,city,lead_id) values(${workerProperty},'TX','Dallas','SYNTHETIC WORKER LOT','Dallas',${workerLead})`;
  await admin`insert into wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id) select ${workerSignal},${workerProperty},source_id,'synthetic-worker','pre_foreclosure',current_date,'https://example.invalid/worker',${run},${run} from wholesale_ingest.ingest_runs where id=${run}`;
  await admin`delete from public.app_settings where key='lead_owner_user_id'`;
  await admin`insert into public.app_settings(key,value) values('lead_owner_user_id',${owner})`;
  [snapshot]=await one`select public.list_scoring_input(${workerLead}) value`;
  assert(snapshot.value.input_hash,'Worker fixture requires a scoreable source observation');
  await one`select public.review_list_lot(${crypto.randomUUID()},${actor},${workerLead},${snapshot.value.input_hash},true,'https://example.invalid/worker-lot','Verified synthetic worker lot')`;
  [snapshot]=await one`select public.list_scoring_input(${workerLead}) value`;
  const zero={components:{distress_stack:part(7,[workerSignal]),need_to_sell:part(0),equity:part(0),contactability:part(0),recency:part(0)},needs_to_sell:'unknown'};
  await one`select public.save_list_score(${workerEval},${workerLead},${snapshot.value.input_hash},'claude-fixture','daily-list-score-v1','msg-worker-lot',${one.json(zero)})`;
  await admin.unsafe('BEGIN');locked=true;await admin`select id from wholesale_ingest.properties where id=${workerProperty} for update`;
  const batch=one`select public.route_list_lots(10) value`.execute();
  let waiting=false;
  for(let i=0;i<100;i++){
   await admin`select pg_stat_clear_snapshot()`;
   const rows=await admin`select pid from pg_stat_activity where application_name='lot-handoff-one' and wait_event_type='Lock'`;
   if(rows.length){waiting=true;break;}await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiting,'Worker must be observed waiting with its batch lock');
  const [busy]=await two`select public.route_list_lots(10) value`;
  assert(busy.value.busy===true,'Overlapping worker must not select a second batch');
  await admin.unsafe('COMMIT');locked=false;
  const [routed]=await batch;
  assert(routed.value.outcomes.some((r:{lead_id:string;blocked:string|null})=>r.lead_id===workerLead&&r.blocked===null),'Worker did not route reviewed lot');
  const [receipt]=await one`select public.list_lot_handoffs(${owner},0) value`;
  const automatic=receipt.value.handoffs.find((h:{lead_id:string})=>h.lead_id===workerLead);
  assert(automatic?.operator_id===null&&automatic?.initiation==='worker','Automatic receipt must not impersonate an administrator');
  const [repeat]=await one`select public.route_list_lots(10) value`;
  assert(!repeat.value.outcomes.some((r:{lead_id:string})=>r.lead_id===workerLead),'Rerun must exclude saved handoff');
  const [monitor]=await one`select public.monitor_list_lots() value`;
  assert(Array.isArray(monitor.value.open_incidents)&&Array.isArray(monitor.value.overdue_receipts),'Restricted role must persist monitor results');
  await admin.unsafe(await Deno.readTextFile(new URL('../../tests/sql/list_lot_worker.sql',import.meta.url)));
  console.log('PASS overlapping lot workers return busy and persist one automatic receipt without a human initiator');
  console.log('PASS concurrent lot handoff creates one destination and retains first receiver acknowledgement; no model or outreach');
 }finally{
  if(locked)await admin.unsafe('ROLLBACK');await Promise.all([one.end(),two.end(),admin.end()]);
 }
}
