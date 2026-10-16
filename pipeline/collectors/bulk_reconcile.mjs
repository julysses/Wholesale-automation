/** One local batch operation; never orders tracing or authorizes outreach. */
import {readFile,writeFile,mkdir,rename} from 'node:fs/promises';
import {resolve,dirname,join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {performance} from 'node:perf_hooks';
import {hash} from './foreclosure_batch.mjs';
import {matchCompletedResults} from './propstream_result_batch.mjs';
import {matchInventory} from './foreclosure_current_inventory.mjs';
export function reconcileBatch(queue,provider,inventory,day) {
  if(!Array.isArray(queue.properties)||!queue.properties.length||queue.properties.length>500) throw Error('Batch must contain 1–500 properties');
  const results=matchCompletedResults(queue,provider);
  const status=new Map(matchInventory(queue,inventory,day).map(row=>[row.parcel_id,row]));
  const items=results.map(row=>{
    const verification=status.get(row.parcel_id);
    const exclusions=row.contacts.filter(c=>c.dnc_status==='listed').length;
    const exceptions=['full_notice_verification_pending','channel_clearance_pending'];
    if(!row.contacts.length) exceptions.push('no_provider_match');
    if(row.provider_litigator_flag) exceptions.push('provider_warning');
    if(verification.stage!=='current_listing_matched') exceptions.push(verification.stage);
    return {...row,current_listing:verification,exceptions,dnc_exclusions:exclusions,
      follow_up_key:`propstream:${provider.job}:${row.parcel_id}`,
      trace_again:false,outreach_authorized:false};
  });
  return {provider_job_id:provider.job,items,summary:{properties:items.length,
    with_contacts:items.filter(r=>r.contacts.length).length,no_match:items.filter(r=>!r.contacts.length).length,
    contact_records:items.reduce((n,r)=>n+r.contacts.length,0),dnc_exclusions:items.reduce((n,r)=>n+r.dnc_exclusions,0),
    provider_warnings:items.filter(r=>r.provider_litigator_flag).length,
    current_listing_matches:items.filter(r=>r.current_listing.stage==='current_listing_matched').length,
    outreach_ready:0},dispatch_authorized:false,outreach_authorized:false};
}
export async function runReconciliation(configPath) {
  const start=performance.now(),base=dirname(resolve(configPath));
  const config=JSON.parse(await readFile(configPath,'utf8'));
  if(!config||Object.keys(config).some(k=>!['queue','provider','inventory','day','output'].includes(k))
      ||['queue','provider','inventory','day','output'].some(k=>typeof config[k]!=='string'||!config[k])) throw Error('Invalid batch config');
  const paths=['queue','provider','inventory'].map(k=>resolve(base,config[k]));
  const bytes=await Promise.all(paths.map(p=>readFile(p)));
  const inputs=Object.fromEntries(['queue','provider','inventory'].map((k,i)=>[k,hash(bytes[i])]));
  const batch=reconcileBatch(...bytes.map(b=>JSON.parse(b)),config.day);
  const batch_id=hash(JSON.stringify({inputs,day:config.day,processor:'bulk-reconcile/1.0'}));
  const output=join(resolve(base,config.output),batch_id);
  if(paths.some(p=>p===join(output,'reconciliation.json')||p===join(output,'receipt.json'))) throw Error('Output would overwrite input');
  await mkdir(output,{recursive:true,mode:0o700});
  const packet={processor:'bulk-reconcile/1.0',batch_id,day:config.day,input_sha256:inputs,...batch};
  const receipt={processor:packet.processor,batch_id,day:config.day,input_sha256:inputs,summary:batch.summary,
    packet_sha256:hash(JSON.stringify(packet)),dispatch_authorized:false,outreach_authorized:false};
  for(const [name,value] of [['reconciliation',packet],['receipt',receipt]]) {
    await writeFile(join(output,name+'.json.tmp'),JSON.stringify(value,null,2),{mode:0o600});
    await rename(join(output,name+'.json.tmp'),join(output,name+'.json'));
  }
  return {batch_id,output,...batch.summary,local_processing_ms:Math.round(performance.now()-start)};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
 if(process.argv.length!==3) throw Error('Usage: bulk_reconcile.mjs private-batch-config.json');
 console.log(JSON.stringify(await runReconciliation(process.argv[2])));
}
