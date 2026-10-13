// Reference ingress implementation; stage and reconcile with deployed schema before release.
import {Ajv} from 'npm:ajv@8.20.0';
import {fullFormats} from 'npm:ajv-formats@3.0.1/dist/formats.js';
import postgres from 'npm:postgres@3.4.5';
import schema from './ingest.schema.json' with { type: 'json' };
import {canonicalJSON, sha256, equalHash, semanticErrors, resolutionGate} from './core.mjs';

import {coverageSchema} from './coverage.mjs';
import {collectorErrors} from './collector-policy.mjs';

const ajv = new Ajv({allErrors:true, strict:true});
for (const name of ['date','date-time','uuid','uri'] as const) ajv.addFormat(name,fullFormats[name]);
type IngestPayload = {
 schema_version:string; source_key:string; run_id:string; scheduled_for:string; pulled_at:string;
 source:{state:string;county:string;jurisdiction:string;list_type:string;source_url:string};
 status:string;status_reason:string;lookback_days:number;window_start:string;window_end:string;
 coverage_complete:boolean;source_as_of:string|null;records_sha256:string;
 records:Array<Record<string,postgres.JSONValue> & {source_url:string;source_record_id:string|null}>;batch_index?:number;batch_count?:number;
};
const validate = ajv.compile<IngestPayload>(schema);
const validateCoverage = ajv.compile(coverageSchema);
const LIMIT = 2 * 1024 * 1024;
type TokenConfig = {sha256:string; source_keys:string[]; expires_at:string};
const response=(status:number,body:unknown)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
class HttpError extends Error { constructor(public status:number,public reason:string){super(reason);} }
let sql:ReturnType<typeof postgres>|undefined;

async function readBounded(req:Request) {
 if(Number(req.headers.get('content-length')||0)>LIMIT) throw new HttpError(413,'payload_too_large');
 const reader=req.body?.getReader(); if(!reader) throw new HttpError(400,'body_required');
 const parts:Uint8Array[]=[]; let size=0;
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>LIMIT){await reader.cancel();throw new HttpError(413,'payload_too_large');}parts.push(value);}
 const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
 try{return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));}catch{throw new HttpError(400,'invalid_json');}
}
export async function handler(req:Request):Promise<Response> {
 try {
  if(req.method!=='POST') return response(405,{error:'method_not_allowed'});
  if(!req.headers.get('content-type')?.toLowerCase().startsWith('application/json')) return response(415,{error:'application_json_required'});
  // Token plaintext exists only in the caller secret store. Edge stores hashes, scopes and expiry.
  const configJSON=Deno.env.get('INGEST_TOKEN_CONFIG');
  const dbURL=Deno.env.get('INGEST_DATABASE_URL');
  if(!configJSON||!dbURL) return response(503,{error:'ingest_not_configured'});
  const keyId=req.headers.get('x-ingest-key-id')||'';
  const config:Record<string,TokenConfig>=JSON.parse(configJSON);
  const token=req.headers.get('authorization')?.match(/^Bearer ([^\s]{32,512})$/)?.[1];
  const entry=Object.hasOwn(config,keyId)?config[keyId]:undefined;
  if(!token||!entry||!Number.isFinite(Date.parse(entry.expires_at))||Date.parse(entry.expires_at)<=Date.now()||!equalHash(await sha256(token),entry.sha256)) return response(401,{error:'unauthorized'});
  const p=await readBounded(req);
  if(!validate(p)) return response(422,{error:'schema_invalid',fields:validate.errors?.map(e=>({path:e.instancePath,message:e.message,keyword:e.keyword}))});
  const errs=semanticErrors(p); if(errs.length) return response(422,{error:'semantic_invalid',fields:errs});
  if(!entry.source_keys.includes(p.source_key)) return response(403,{error:'source_not_authorized'});
  const collectorErrs=collectorErrors(p,new Date(),validateCoverage);
  if(collectorErrs.length) return response(422,{error:'collector_evidence_invalid',fields:collectorErrs});
  const recordsHash=await sha256(canonicalJSON(p.records));
  if(!equalHash(recordsHash,p.records_sha256)) return response(422,{error:'records_hash_mismatch',fields:[{path:'/records_sha256',message:'recompute canonical records hash'}]});
  const batchIndex=p.batch_index??0,batchCount=p.batch_count??1;
  const payloadHash=await sha256(canonicalJSON(p));
  const records=p.records;
  const manifest={...p} as Partial<IngestPayload>;
  delete manifest.records; delete manifest.records_sha256; delete manifest.batch_index;
  const manifestHash=await sha256(canonicalJSON({...manifest,batch_count:batchCount}));
  // Use a dedicated LOGIN role that inherits wholesale_ingestor, not postgres/service_role.
  sql??=postgres(dbURL,{prepare:false,max:1,connect_timeout:10,idle_timeout:20,ssl:'require'});
  const receipt=await sql.begin(async tx=>{
   await tx`set local statement_timeout='15s'`;
   await tx`select pg_advisory_xact_lock(hashtextextended(${p.run_id},0))`;
   const [src]=await tx`select * from wholesale_ingest.sources where source_key=${p.source_key}`;
   if(!src||!src.enabled) throw new HttpError(403,'source_disabled_or_unknown');
   if(src.county!==p.source.county||src.state!==p.source.state||src.list_type!==p.source.list_type||src.jurisdiction!==p.source.jurisdiction) throw new HttpError(422,'source_metadata_mismatch');
   if(p.lookback_days>Math.max(src.lookback_days,src.backfill_days)) throw new HttpError(422,'lookback_exceeds_source_config');
   for(const u of [p.source.source_url,...records.map(r=>r.source_url)]) if(!src.allowed_hosts.includes(new URL(u).hostname)) throw new HttpError(422,'source_url_not_allowed');
   const [run]=await tx`select id,manifest_hash from wholesale_ingest.ingest_runs where id=${p.run_id}`;
   if(run&&run.manifest_hash!==manifestHash) throw new HttpError(409,'run_id_reused_with_changed_manifest');
   const [expired]=await tx`select 1 from wholesale_ingest.raw_payloads where run_id=${p.run_id} and (expires_at<=now() or purged_at is not null) limit 1`;
   if(expired) throw new HttpError(410,'run_retention_expired');
   const [batch]=await tx`select payload_hash from wholesale_ingest.raw_payloads where run_id=${p.run_id} and batch_index=${batchIndex}`;
   if(batch){if(batch.payload_hash!==payloadHash)throw new HttpError(409,'batch_reused_with_changed_payload');return {run_id:p.run_id,batch_index:batchIndex,replayed:true,state:'accepted'};}
   if(!run)await tx`insert into wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches) values (${p.run_id},${src.id},${p.scheduled_for},${p.pulled_at},${p.status},${p.status_reason},${manifestHash},${batchCount})`;
   await tx`insert into wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in) values(${p.run_id},${batchIndex},${payloadHash},${recordsHash},${tx.json(JSON.parse(JSON.stringify(p)))},${records.length})`;
   if(records.length){
    const rows=records.map((r,i)=>({run_id:p.run_id,batch_index:batchIndex,ordinal:i,source_record_id:r.source_record_id,record:tx.json(r),review_reason:resolutionGate(p,r)}));
    await tx`insert into wholesale_ingest.records ${tx(rows)}`;
    await tx`insert into wholesale_ingest.jobs(run_id,batch_index,kind) values(${p.run_id},${batchIndex},'normalize')`;
   }
   if(p.status!=='success')await tx`insert into wholesale_ingest.jobs(run_id,batch_index,kind) values(${p.run_id},${batchIndex},'source_review')`;
   return {run_id:p.run_id,batch_index:batchIndex,replayed:false,state:'accepted',records_received:records.length};
  });
  return response(receipt.replayed?200:202,receipt);
 }catch(e){
  if(e instanceof HttpError) return response(e.status,{error:e.reason});
  // No raw payload, token, contact information or DB connection string in logs/responses.
  console.error('wholesale_ingest_failed');
  return response(503,{error:'ingest_temporarily_unavailable',retry:'reuse_same_run_id_and_payload'});
 }
}
if (import.meta.main) Deno.serve(handler);
