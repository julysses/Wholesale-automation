import {PropstreamResultMatch} from './PropstreamResultMatch';
import {useRef,useState} from 'react';
import Papa from 'papaparse';
import {useQueryClient} from '@tanstack/react-query';
import {apiFetch} from '@/lib/api';
import {Button} from '@/components/ui/button';
import {useProfile} from '@/hooks/useProfile';
import {batchSchema,parseBulkCsv,propstreamContactRows,type Batch,type Action} from '@/lib/propstreamBulkCsv';
type Row={lead_id:string;signal_id:string;signal_hash:string;auction_date:string;stage:string;input_hash:string;address_std:string;county:string;input:Record<string,string>|null;request:{id:string;input_hash:string}|null};
const allowed:Record<Action,string[]>= {review_status:['current_status_review','quote_and_evidence_required'],prepare:['quote_and_evidence_required'],start:['reserved'],reconcile:['reconciliation_required']};
const saveCsv=(name:string,rows:Record<string,unknown>[])=>{const url=URL.createObjectURL(new Blob([Papa.unparse(rows,{escapeFormulae:true})],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);};
export function PropstreamBulk(){const {profile,isAdmin}=useProfile();return profile&&isAdmin?<Bulk key={profile.id} actor={profile.id}/>:null;}
function Bulk({actor}:{actor:string}){
 const key=`wholesaleos.propstream.bulk.v1.${actor}`;const client=useQueryClient();const lock=useRef(false);
 const [initial]=useState(()=>{try{const raw=sessionStorage.getItem(key);return {batch:raw?batchSchema.parse(JSON.parse(raw)):null,error:''};}catch{return {batch:null,error:'Saved batch is unreadable. Reconcile it before another submission.'};}});
 const [manifest,setManifest]=useState<Record<string,unknown>[]>([]);const [pending,setPending]=useState<Batch|null>(initial.batch);const [draft,setDraft]=useState<Batch|null>(null);const [action,setAction]=useState<Action>('review_status');const [busy,setBusy]=useState(false);const [message,setMessage]=useState(initial.error);
 async function refresh(){await client.invalidateQueries({queryKey:['propstream-handoff',actor]});await client.invalidateQueries({queryKey:['list-tracing',actor]});}
 async function sheet(){if(lock.current)return;lock.current=true;setBusy(true);setMessage('');try{
  const rows:Row[]=[];let offset=0,total=0;
  do{const page=await(await apiFetch(`/api/operations/lists/propstream?offset=${offset}`)).json();rows.push(...page.items.filter((r:Row)=>allowed[action].includes(r.stage)));total=page.total;offset+=50;}while(offset<total&&rows.length<500);
  const selected=rows.slice(0,500);if(!selected.length)throw new Error('No eligible rows for this step. Review holds and existing contacts are excluded from trace orders.');
  saveCsv(`wholesaleos-${action}.csv`,selected.map(r=>{
   const common={action,lead_id:r.lead_id,request_id:['start','reconcile'].includes(action)?r.request?.id:'',signal_id:r.signal_id,signal_hash:r.signal_hash,input_hash:r.request?.input_hash||r.input_hash,property_address:r.address_std,county:r.county,owner_name:r.input?.owner_name||'',city:r.input?.city||'',state:r.input?.state||'TX',zip_code:r.input?.zip_code||''};
   if(action==='review_status')return {...common,auction_date:r.auction_date,active:'false',status_evidence_url:'',notes:'',confirmed_current_status:'false'};
   if(action==='prepare')return {...common,quote_cents:'',prepaid_balance_cents:'',quote_reference:'',owner_evidence_url:'',status_evidence_url:'',notes:'',all_pages_reviewed:'false'};
   if(action==='start')return common;
   const contacts=Object.fromEntries(Array.from({length:5},(_,i)=>i+1).flatMap(n=>[['name_'+n,''],['phone_'+n,''],['email_'+n,''],['phone_type_'+n,'unknown']]));
   return {...common,actual_cents:'',provider_receipt:'',no_match:'false',confirmed_match:'false',...contacts};
  }));setMessage(`Exported ${selected.length} eligible rows for ${action.replaceAll('_',' ')}. Remove unwanted rows and complete the evidence/quote or matched result columns. Other rows remain held.`);
 }catch(e){setMessage(e instanceof Error?e.message:'Export unavailable');}finally{lock.current=false;setBusy(false);}}
 async function submit(batch:Batch){if(lock.current||initial.error)return;lock.current=true;setBusy(true);try{
  sessionStorage.setItem(key,JSON.stringify(batch));setPending(batch);
  const result=await(await apiFetch('/api/operations/lists/propstream/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(batch)})).json();
  if(result.batch_id!==batch.batch_id||result.operator_id!==actor||result.count!==batch.items.length||result.outreach_authorized!==false)throw new Error('Batch acknowledgement unconfirmed. Recover the saved batch.');
  sessionStorage.removeItem(key);setPending(null);setDraft(null);
  setMessage(result.replayed?'Original batch recovered. Do not repeat a provider submission.':result.dispatch?'Batch marked submitted. Submit the matching properties once in PropStream; preserve these request IDs for result matching.':'Batch saved. Refresh the next step’s sheet. No provider order or outreach was sent.');
  if(result.action==='start')setManifest(result.results.map((r:{request_id:string;lead_id:string;input:Record<string,string>})=>({request_id:r.request_id,lead_id:r.lead_id,...r.input})));
  await refresh();
 }catch(e){setMessage(e instanceof Error?e.message:'Batch outcome unknown. Recover before another action.');}finally{lock.current=false;setBusy(false);}}
 async function recover(){if(!pending||lock.current)return;lock.current=true;setBusy(true);try{
  const r=await(await apiFetch(`/api/operations/lists/propstream/batches/${pending.batch_id}/recover`,{method:'POST'})).json();
  if(r.batch_id!==pending.batch_id||r.settled!==true||(r.result&&r.result.operator_id!==actor))throw new Error('Batch recovery unconfirmed.');
  if(r.result?.action==='start')setManifest(r.result.results.map((x:{request_id:string;lead_id:string;input:Record<string,string>})=>({request_id:x.request_id,lead_id:x.lead_id,...x.input})));
  sessionStorage.removeItem(key);setPending(null);setDraft(null);setMessage(r.result?'Original batch confirmed. Do not repeat its provider order.':'No committed batch found; its old ID is now blocked from running late. Generate a fresh sheet.');await refresh();
 }catch(e){setMessage(e instanceof Error?e.message:'Recovery unavailable');}finally{lock.current=false;setBusy(false);}}
 const disabled=busy||!!pending||!!initial.error;
 return <section aria-label="Bulk PropStream workflow" className="rounded-xl border bg-white p-5 space-y-3"><h2 className="text-xl font-semibold">Bulk foreclosure → PropStream → follow-up</h2>
 <p>Process up to 500 verified leads together. Export the current step’s sheet, complete it in bulk, and import it for review. Duplicate or ineligible leads cannot reserve spending. The $50 cap includes every prior order.</p>
 <PropstreamResultMatch /><label>Batch step <select disabled={disabled} value={action} onChange={e=>{setAction(e.target.value as Action);setDraft(null);}}><option value="review_status">1. Review current sales</option><option value="prepare">2. Reserve verified quotes</option><option value="start">3. Start reserved batch</option><option value="reconcile">4. Import matched results</option></select></label>
 <Button disabled={disabled} onClick={sheet}>Download eligible batch sheet</Button>
 <label className="block">Import completed batch CSV <input type="file" accept=".csv,text/csv" disabled={disabled} onChange={async e=>{const file=e.target.files?.[0];setDraft(null);if(!file)return;try{if(file.size>2_000_000)throw new Error('CSV limit is 2 MB.');setDraft(parseBulkCsv(await file.text(),action));setMessage('Review the batch count and cost before saving.');}catch(error){setMessage(error instanceof Error?error.message:'Invalid CSV');}e.target.value='';}}/></label>
 {draft&&<div><p>{draft.items.length} leads · {action.replaceAll('_',' ')} · ${(draft.items.reduce((n,x)=>n+Number(x.payload.quote_cents||x.payload.actual_cents||0),0)/100).toFixed(2)} quoted/actual total</p><Button disabled={disabled} onClick={()=>submit(draft)}>Save {draft.items.length}-lead batch</Button></div>}
 {pending&&<div role="alert">Unconfirmed batch {pending.batch_id}. <Button disabled={busy} onClick={recover}>Recover saved batch</Button><Button disabled={busy} onClick={()=>submit(pending)}>Retry exact batch</Button></div>}
 {manifest.length>0&&<div><Button onClick={()=>saveCsv('propstream-submission-manifest.csv',manifest)}>Download saved submission manifest</Button><Button onClick={()=>saveCsv('propstream-contacts.csv',propstreamContactRows(manifest))}>Download PropStream contacts CSV</Button><p>Keep the separate manifest for matching results. PropStream’s template has no request-ID column. The verified full owner name is preserved in First Name; confirm provider matching before tracing.</p></div>}{message&&<p role="status">{message}</p>}<p>PropStream submission remains in its signed-in UI. Keep the exported request IDs and map returned rows to them; never match by row order. Result import saves contacts and creates assigned follow-up tasks. Channel eligibility is still required before outreach.</p>
 </section>;
}
