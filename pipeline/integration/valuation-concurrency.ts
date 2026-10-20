import postgres from 'npm:postgres@3.4.5';
export async function verifyValuationConcurrency(adminURL:string){
 const admin=postgres(adminURL,{ssl:'require',max:1});
 const one=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'valuation-one'}});
 const two=postgres(adminURL,{ssl:'require',max:1,connection:{application_name:'valuation-two'}});
 const land=crypto.randomUUID(),actor=crypto.randomUUID();let locked=false;
 const assert=(v:unknown,m:string)=>{if(!v)throw new Error(m);};
 try{
  const original=await Deno.readTextFile(new URL('../../frontend/supabase/migrations/007_land_wholesaling.sql',import.meta.url));
  const table=original.slice(original.indexOf('CREATE TABLE IF NOT EXISTS land_comps ('),original.indexOf('ALTER TABLE land_comps ENABLE'));
  await admin.unsafe(table.replace('IF NOT EXISTS land_comps','public.land_comps').replaceAll('uuid_generate_v4()','gen_random_uuid()'));
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261020163219_integration_land_valuation_receipts.sql',import.meta.url)));
  await admin.unsafe(await Deno.readTextFile(new URL('../../frontend/supabase/migrations/20261020163221_integration_preserve_valuation_radius.sql',import.meta.url)));
  await admin`insert into public.profiles(id,role,status) values(${actor},'user','approved')`;
  await admin`insert into public.land_leads(id,property_address,city,state,county,status,offer_price,mao) values(${land},'SYNTHETIC VALUATION','Dallas','TX','Dallas','new',12345,23456)`;
  await one.unsafe('SET ROLE service_role');await two.unsafe('SET ROLE service_role');
  const [initial]=await one`select public.read_land_valuation(${land},${actor}) value`;
  const hash=initial.value.snapshot_hash;
  const payload={direct_comp_details:[{address:'Synthetic comp',price:100,sqft:null,date:null,distance_mi:0,source_url:null}],avg_house_arv:null,house_comp_count:null,tav:0,tav_source:'manual',tav_assessment_date:null,comp_notes:'Synthetic evidence'};
  const ids=[crypto.randomUUID(),crypto.randomUUID()];
  await admin.unsafe('BEGIN');locked=true;await admin`select id from public.land_leads where id=${land} for update`;
  const saves=[one`select public.save_land_valuation(${ids[0]},${actor},${land},${hash},${one.json(payload)}) value`.execute(),two`select public.save_land_valuation(${ids[1]},${actor},${land},${hash},${two.json(payload)}) value`.execute()];
  let waiters:{pid:number}[]=[];
  for(let i=0;i<100;i++){
   await admin`select pg_stat_clear_snapshot()`;
   waiters=await admin`select pid from pg_stat_activity where application_name in ('valuation-one','valuation-two') and wait_event_type='Lock'`;
   if(waiters.length===2)break;await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(waiters.length===2&&waiters[0].pid!==waiters[1].pid,'Valuation saves must overlap on separate sessions');
  console.log('Verified overlapping valuation save PIDs:',waiters.map(r=>r.pid).join(','));
  await admin.unsafe('COMMIT');locked=false;
  const results=(await Promise.all(saves)).map(rows=>rows[0].value);
  assert(results.filter(x=>x.event).length===1&&results.filter(x=>x.blocked==='valuation_changed').length===1,'Expected one valuation save and one stale conflict');
  const winner=results.find(x=>x.event).event;
  const [counts]=await admin`select (select count(*)::int from public.land_comps where land_lead_id=${land}) comps,(select count(*)::int from wholesale_ingest.land_valuation_events where land_lead_id=${land}) receipts`;
  assert(counts.comps===1&&counts.receipts===1,'Concurrent saves created duplicate records');
  const [replay]=await one`select public.save_land_valuation(${winner.id},${actor},${land},${hash},${one.json(payload)}) value`;
  assert(replay.value.replayed===true,'Lost receipt must replay');
  const [snapshot]=await one`select public.read_land_valuation(${land},${actor}) value`;
  await one`select public.save_land_valuation(${crypto.randomUUID()},${actor},${land},${snapshot.value.snapshot_hash},${one.json({...payload,tav:200})})`;
  await one`select public.save_land_valuation(${winner.id},${actor},${land},${hash},${one.json(payload)})`;
  const [latest]=await one`select public.read_land_valuation(${land},${actor}) value`;
  assert(latest.value.comp.revision===2&&latest.value.comp.tav===200,'Historical retry overwrote later valuation');
  const [price]=await admin`select offer_price::int,mao::int,status from public.land_leads where id=${land}`;
  assert(price.offer_price===12345&&price.mao===23456&&price.status==='new','Valuation changed human offer pricing or lead stage');
  await admin.unsafe(await Deno.readTextFile(new URL('../../tests/sql/land_valuation_receipts.sql',import.meta.url)));
  console.log('PASS actual concurrent valuation saves create one record, preserve subsequent edits and never write offer prices');
 }finally{if(locked)await admin.unsafe('ROLLBACK');await Promise.all([one.end(),two.end(),admin.end()]);}
}
