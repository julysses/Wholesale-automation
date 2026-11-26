// Scoped HTTPS transport. Caller retains unchanged manifests and journal after any
// uncertain response. Never logs token values or owner/property data.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {preflight} from './preflight.mjs';
import {canonicalJSON,sha256} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';

export async function validateBatches(payloads,now=new Date(),coverage){
 if(!payloads.length)throw new Error('No batches');
 const sorted=[...payloads].sort((a,b)=>(a.batch_index??0)-(b.batch_index??0));
 const first=sorted[0], count=first.batch_count??1;
 if(count!==sorted.length)throw new Error('Incomplete batch set');
 const identity=p=>{const copy={...p};delete copy.records;delete copy.records_sha256;delete copy.batch_index;return canonicalJSON(copy);};
 const ids=new Set();
 for(let i=0;i<count;i++){
  const p=sorted[i];
  if((p.batch_index??0)!==i||identity(p)!==identity(first))throw new Error('Batch identity mismatch');
  if(!(await preflight(p,now,coverage)).valid)throw new Error('Batch preflight failed');
  for(const r of p.records){if(r.source_record_id&&ids.has(r.source_record_id))throw new Error('Duplicate record across batches');if(r.source_record_id)ids.add(r.source_record_id);}
 }
 return sorted;
}
export async function sendBatch(payload,{endpoint,keyId,token,fetcher=fetch}){
 if(!/^https:\/\/[a-z0-9]{20}\.supabase\.co\/functions\/v1\/daily-list-ingest$/.test(endpoint))throw new Error('Expected exact Supabase ingestion endpoint');
 if(!/^[A-Za-z0-9_-]{1,100}$/.test(keyId)||!/^\S{32,512}$/.test(token))throw new Error('Missing scoped collector credentials');
 let response;
 try{response=await fetcher(endpoint,{method:'POST',redirect:'error',headers:{'Content-Type':'application/json','X-Ingest-Key-Id':keyId,Authorization:'Bearer '+token},body:JSON.stringify(payload),signal:AbortSignal.timeout(30000)});}
 catch{throw new Error('Delivery uncertain; retry the identical saved run and payload');}
 if(![200,202].includes(response.status))throw new Error(`Ingestion HTTP ${response.status}; preserve the same run and payload for reconciliation`);
 // Bound even a misbehaving endpoint; never print the returned body.
 const reader=response.body?.getReader();if(!reader)throw new Error('Acknowledgement missing');
 const parts=[];let size=0;
 while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>16384){await reader.cancel();throw new Error('Acknowledgement too large');}parts.push(value);}
 let r;try{r=JSON.parse(Buffer.concat(parts).toString('utf8'));}catch{throw new Error('Acknowledgement unreadable');}
 if(r.run_id!==payload.run_id||r.batch_index!==(payload.batch_index??0)||r.state!=='accepted'||r.replayed!==(response.status===200)||(!r.replayed&&r.records_received!==payload.records.length))throw new Error('Acknowledgement identity mismatch; reconcile before changing payload');
 return {run_id:r.run_id,batch_index:r.batch_index,replayed:r.replayed,state:r.state,records:payload.records.length,payload_sha256:await sha256(canonicalJSON(payload))};
}
export async function deliver(payloads,{journalPath,coverage,...options}){
 const batches=await validateBatches(payloads,new Date(),coverage);
 const wireBatches=batches.map(p=>coverage===undefined?p:{...p,coverage});
 const identity=await sha256(canonicalJSON(wireBatches));
 let journal={run_id:batches[0].run_id,payload_set_sha256:identity,endpoint:options.endpoint,key_id:options.keyId,accepted:[]};
 if(fs.existsSync(journalPath)){
  journal=JSON.parse(fs.readFileSync(journalPath,'utf8'));
  if(journal.run_id!==batches[0].run_id||journal.payload_set_sha256!==identity||!Array.isArray(journal.accepted))throw new Error('Saved journal belongs to different payloads');
  if(journal.endpoint!==options.endpoint||journal.key_id!==options.keyId)throw new Error('Saved journal destination is missing or different; reconcile it before delivery');
 }
 const save=()=>{const tmp=journalPath+'.tmp';fs.writeFileSync(tmp,JSON.stringify(journal,null,2),{mode:0o600});fs.renameSync(tmp,journalPath);};
 save();
 // Replays every batch, including previously acknowledged batches, so local
 // journal corruption cannot substitute for an actual durable server receipt.
 for(const p of wireBatches){
  journal.pending_batch=p.batch_index??0;save();
  const ack=await sendBatch(p,options);
  journal.accepted=journal.accepted.filter(x=>x.batch_index!==ack.batch_index);journal.accepted.push(ack);delete journal.pending_batch;save();
 }
 return {run_id:journal.run_id,accepted_batches:journal.accepted.length,records:batches.reduce((n,p)=>n+p.records.length,0),ingress_accepted:true,crm_leads_verified:false};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  const [dir,project,coveragePath]=process.argv.slice(2);
  if(!dir||!project||process.argv.length>5)throw new Error('Usage: node pipeline/collectors/deliver.mjs manifest-directory project-ref [coverage.json]');
  const files=fs.readdirSync(dir).filter(x=>/^batch-\d{4}\.json$/.test(x)).sort();
  const payloads=files.map(file=>{const name=path.join(dir,file);if(fs.statSync(name).size>2*1024*1024)throw new Error('Batch too large');return JSON.parse(fs.readFileSync(name,'utf8'));});
  const coverage=coveragePath?JSON.parse(fs.readFileSync(coveragePath,'utf8')):undefined;
  if(!/^[a-z0-9]{20}$/.test(project))throw new Error('Invalid project reference');
  const result=await deliver(payloads,{coverage,journalPath:path.join(dir,`delivery-receipts.${project}.json`),endpoint:`https://${project}.supabase.co/functions/v1/daily-list-ingest`,keyId:process.env.INGEST_KEY_ID??'',token:process.env.INGEST_TOKEN??''});
  console.log(JSON.stringify(result,null,2));
 }catch(e){console.error(e instanceof Error?e.message:'Delivery failed');process.exitCode=1;}
}
