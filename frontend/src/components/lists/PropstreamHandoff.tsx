import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { apiFetch } from '@/lib/api';
import { useProfile } from '@/hooks/useProfile';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
const intentSchema=z.object({event_id:z.string().uuid(),request_id:z.string().uuid(),lead_id:z.string().uuid(),action:z.enum(['prepare','start','reconcile','review_status']),payload:z.record(z.string(),z.unknown())});
type Intent=z.infer<typeof intentSchema>;
type Contact={name:string;phone:string;email:string;phone_type:'mobile'|'landline'|'voip'|'unknown'};
type Candidate={lead_id:string;county:string;address_std:string;city:string;zip:string;stage:string;signal_id:string;signal_hash:string;auction_date:string|null;input_hash:string|null;input:Record<string,string>|null;
 request:{id:string;state:string;input_hash:string;reserved_cents:number;actual_cents:number|null;provider_job_id:string|null}|null;
 contacts:Contact[];handoff:{follow_up_task_id:string|null}|null};
type Snapshot={items:Candidate[];total:number;total_budget:{remaining_cents:number;committed_cents:number}};
const dollars=(n:number)=>(n/100).toFixed(2);
function cents(text:string){if(!/^\d+(\.\d{1,2})?$/.test(text))throw new Error('Enter a dollar amount with at most two decimal places.');return Math.round(Number(text)*100);}
export function PropstreamHandoff(){const {profile,isAdmin}=useProfile();return isAdmin&&profile?<Controls key={profile.id} actor={profile.id}/>:null;}
function Controls({actor}:{actor:string}){
 const key=`wholesaleos.propstream.v1.${actor}`;
 const [initial]=useState(()=>{try{const raw=sessionStorage.getItem(key);return {intent:raw?intentSchema.parse(JSON.parse(raw)):null,error:''};}catch{return {intent:null,error:'Saved handoff is unreadable. Ask an administrator to reconcile it before another order.'};}});
 const [pending,setPending]=useState<Intent|null>(initial.intent);const [busy,setBusy]=useState(false);const lock=useRef(false);
 const [message,setMessage]=useState(initial.error);const [offset,setOffset]=useState(0);const client=useQueryClient();
 const query=useQuery<Snapshot>({queryKey:['propstream-handoff',actor,offset],queryFn:async()=> (await apiFetch(`/api/operations/lists/propstream?offset=${offset}`)).json()});
 const refresh=async()=>{await Promise.all([query.refetch(),client.invalidateQueries({queryKey:['list-tracing',actor]})]);};
 async function execute(intent:Intent){
  if(lock.current||initial.error)return;lock.current=true;setBusy(true);setMessage('');
  try{
   sessionStorage.setItem(key,JSON.stringify(intent));setPending(intent);
   const r=await(await apiFetch('/api/operations/lists/propstream/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(intent)})).json();
   if(r.event_id!==intent.event_id||r.request_id!==intent.request_id||r.lead_id!==intent.lead_id||r.operator_id!==actor||r.action!==intent.action||r.outreach_authorized!==false)throw new Error('Handoff receipt did not match. Check the saved action before another order.');
   sessionStorage.removeItem(key);setPending(null);
   setMessage(r.replayed?'Saved action recovered. Do not repeat any PropStream purchase.':intent.action==='start'&&r.dispatch===true?'Handoff started. Submit this exact lead once in PropStream. If interrupted, check the provider order before retrying.':intent.action==='review_status'?'Current sale review saved. Recheck the updated queue before tracing.':intent.action==='prepare'?'Quote reserved. Start the handoff before submitting in PropStream.':'Result saved. Review the matched contacts and the assigned follow-up task. No outreach was sent.');
   await refresh();
  }catch(e){setMessage(e instanceof Error?e.message:'Outcome unconfirmed. Recover the saved action.');}finally{lock.current=false;setBusy(false);}
 }
 async function recover(){
  if(!pending||lock.current)return;lock.current=true;setBusy(true);
  const original=JSON.stringify(pending);
  try{
   const r=await(await apiFetch(`/api/operations/lists/propstream/events/${pending.event_id}/recover`,{method:'POST'})).json();
   if(r.event_id!==pending.event_id||r.settled!==true||(r.result!==null&&(r.result.operator_id!==actor||r.result.request_id!==pending.request_id||r.result.lead_id!==pending.lead_id||r.result.action!==pending.action)))throw new Error('Saved action could not be verified.');
   if(sessionStorage.getItem(key)!==original)throw new Error('Saved handoff changed in another action. Reload to reconcile.');
   sessionStorage.removeItem(key);setPending(null);setMessage(r.result?'Saved action confirmed. Review its current state; do not repeat the provider purchase.':'No committed action was found. Its old reference is now blocked from running late. Review the current lead and quote before trying again.');await refresh();
  }catch(e){setMessage(e instanceof Error?e.message:'Recovery unavailable');}finally{lock.current=false;setBusy(false);}
 }
 return <section aria-label="PropStream handoff" className="rounded-xl border bg-white p-5 space-y-3">
  <h2 className="text-xl font-semibold">PropStream — verified foreclosure leads</h2>
  <p>Verify the owner, property and current sale before tracing. Reuse existing contacts. Reserve the exact quote against the $50 total prepaid limit, then submit once in PropStream and save its result here.</p>
  <a className="underline" href="https://app.propstream.com" target="_blank" rel="noreferrer">Open PropStream</a>
  {message&&<p role="status">{message}</p>}
  {pending&&<div role="alert">Unconfirmed saved {pending.action} action: {pending.event_id}.<Button disabled={busy} onClick={recover}>Recover saved handoff</Button><Button disabled={busy} onClick={()=>execute(pending)}>Retry exact saved action</Button></div>}
  {query.isLoading&&<p>Loading verified leads…</p>}{query.error&&<p role="alert">PropStream handoff unavailable. <Button onClick={()=>query.refetch()}>Refresh handoff</Button></p>}
  {query.data&&<><p>${dollars(query.data.total_budget.remaining_cents)} remaining · ${dollars(query.data.total_budget.committed_cents)} committed across all days. No card fallback or replenishment.</p>
   {!query.data.total&&<p>No verified foreclosure properties yet. Complete notice review in the priority inbox above.</p>}
   {query.data.items.map(row=><CandidateControl key={`${row.lead_id}:${row.signal_hash}:${row.input_hash}:${row.request?.state}`} row={row} disabled={busy||!!pending||!!initial.error||!!query.error} run={execute}/>)}
   <div className="flex gap-2"><Button disabled={offset===0||busy} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous verified leads</Button><Button disabled={offset+50>=query.data.total||busy} onClick={()=>setOffset(offset+50)}>Next verified leads</Button></div>
  </>}
 </section>;
}
function CandidateControl({row,disabled,run}:{row:Candidate;disabled:boolean;run:(intent:Intent)=>Promise<void>}){
 const [quote,setQuote]=useState('');const [balance,setBalance]=useState('');const [reference,setReference]=useState('');const [ownerUrl,setOwnerUrl]=useState('');const [statusUrl,setStatusUrl]=useState('');const [notes,setNotes]=useState('');const [reviewed,setReviewed]=useState(false);
 const [statusConfirmed,setStatusConfirmed]=useState(false);const [saleDate,setSaleDate]=useState(row.auction_date||'');const [saleActive,setSaleActive]=useState(false);
 const [actual,setActual]=useState('');const [receipt,setReceipt]=useState('');const [matched,setMatched]=useState(false);const [noMatch,setNoMatch]=useState(false);const [error,setError]=useState('');
 const empty=():Contact=>({name:'',phone:'',email:'',phone_type:'unknown'});const [contacts,setContacts]=useState<Contact[]>([empty()]);
 async function act(action:Intent['action']){
  setError('');try{
   const payload=action==='review_status'?{signal_id:row.signal_id,signal_hash:row.signal_hash,active:saleActive,auction_date:saleDate,status_evidence_url:statusUrl,notes,confirmed_current_status:statusConfirmed}:action==='prepare'?{input_hash:row.input_hash,signal_id:row.signal_id,signal_hash:row.signal_hash,quote_cents:cents(quote),prepaid_balance_cents:cents(balance),quote_reference:reference,owner_evidence_url:ownerUrl,status_evidence_url:statusUrl,notes,all_pages_reviewed:reviewed}:action==='start'?{input_hash:row.request!.input_hash}:{input_hash:row.request!.input_hash,actual_cents:cents(actual),provider_receipt:receipt,contacts:noMatch?[]:contacts.map(c=>({...c,phone:c.phone||null,email:c.email||null,name:c.name||null})),confirmed_match:matched};
   await run({event_id:crypto.randomUUID(),request_id:action==='prepare'||action==='review_status'?crypto.randomUUID():row.request!.id,lead_id:row.lead_id,action,payload});
  }catch(e){setError(e instanceof Error?e.message:'Check entered values.');}
 }
 const update=(index:number,k:keyof Contact,value:string)=>setContacts(old=>old.map((c,i)=>i===index?{...c,[k]:value}:c));
 return <details className="rounded border p-3"><summary className="cursor-pointer font-semibold">{row.address_std} · {row.county} · {row.stage.replaceAll('_',' ')}</summary>
  {row.stage==='suppressed'&&<p>Lead suppressed. No new tracing or outreach is permitted.</p>}
  <p>CRM lead: {row.lead_id} · Sale date: {row.auction_date||'unverified'}</p>
  {row.input&&<p>Owner: {row.input.owner_name} · Property: {row.input.property_address}, {row.input.city}, {row.input.state} {row.input.zip_code}</p>}
  {error&&<p role="alert">{error}</p>}
  {row.stage==='quote_and_evidence_required'&&<div className="space-y-2">
   <Input label="PropStream quote ($)" value={quote} onChange={e=>setQuote(e.target.value)}/><Input label="Confirmed PropStream prepaid balance ($)" value={balance} onChange={e=>setBalance(e.target.value)}/><Input label="Quote reference or dated quote description" value={reference} onChange={e=>setReference(e.target.value)}/>
   <Input label="Official owner evidence URL" value={ownerUrl} onChange={e=>setOwnerUrl(e.target.value)}/><Input label="Official current-sale evidence URL" value={statusUrl} onChange={e=>setStatusUrl(e.target.value)}/><Input label="Owner and current-sale review notes" value={notes} onChange={e=>setNotes(e.target.value)}/>
   <label className="block"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> I reviewed every notice page and independently confirmed this owner, property and current sale.</label>
   <Button disabled={disabled||!reviewed||notes.trim().length<20||!quote||!balance||!reference||!ownerUrl||!statusUrl} onClick={()=>act('prepare')}>Reserve verified quote</Button>
  </div>}
  {row.stage==='reserved'&&<><p>${dollars(row.request!.reserved_cents)} reserved. Start once before placing the matching order in PropStream. Use tracing recovery below to cancel an unsubmitted reservation.</p><Button disabled={disabled} onClick={()=>act('start')}>Start one PropStream handoff</Button></>}
  {row.stage==='reconciliation_required'&&<div className="space-y-2">
   <p>Check the existing PropStream order. Do not place another purchase. Request: {row.request!.id}</p>
   <Input label="PropStream order receipt" value={receipt} onChange={e=>setReceipt(e.target.value)}/><Input label="Confirmed charge ($)" value={actual} onChange={e=>setActual(e.target.value)}/>
   <label className="block"><input type="checkbox" checked={noMatch} onChange={e=>setNoMatch(e.target.checked)}/> Provider returned no contacts</label>
   {!noMatch&&contacts.map((c,i)=><fieldset className="border p-2" key={i}><legend>Returned contact {i+1}</legend><Input label={`Contact ${i+1} name`} value={c.name} onChange={e=>update(i,'name',e.target.value)}/><Input label={`Contact ${i+1} phone (+1 and 10 digits)`} value={c.phone} onChange={e=>update(i,'phone',e.target.value)}/><Input label={`Contact ${i+1} email`} value={c.email} onChange={e=>update(i,'email',e.target.value)}/><label>Phone type <select value={c.phone_type} onChange={e=>update(i,'phone_type',e.target.value)}><option value="unknown">Unknown</option><option value="mobile">Mobile</option><option value="landline">Landline</option><option value="voip">VoIP</option></select></label></fieldset>)}
   {!noMatch&&<Button disabled={contacts.length>=20} onClick={()=>setContacts(old=>[...old,empty()])}>Add returned contact</Button>}
   <label className="block"><input type="checkbox" checked={matched} onChange={e=>setMatched(e.target.checked)}/> I matched this order and every returned contact to the saved lead and property.</label>
   <Button disabled={disabled||!matched||!receipt||!actual} onClick={()=>act('reconcile')}>Save matched result and follow-up</Button>
  </div>}
  {row.stage==='identity_incomplete'&&<p>Verify and save the owner name on the CRM lead before requesting a quote.</p>}
  {row.stage==='current_status_review'&&<p>Current active foreclosure evidence is required. This property is not eligible for a trace purchase.</p>}
  <details className="border p-2"><summary>Review current sale status</summary>
   <p>Record current official evidence and cancellation/postponement checks. Saving a review does not order a trace or authorize outreach.</p>
   <Input label="Reviewed sale date (YYYY-MM-DD)" value={saleDate} onChange={e=>setSaleDate(e.target.value)}/>
   <Input label="Current sale status evidence URL" value={statusUrl} onChange={e=>setStatusUrl(e.target.value)}/>
   <Input label="Current status review notes" value={notes} onChange={e=>setNotes(e.target.value)}/>
   <label className="block"><input type="checkbox" checked={saleActive} onChange={e=>setSaleActive(e.target.checked)}/> Sale confirmed active on the reviewed date</label>
   <label className="block"><input type="checkbox" checked={statusConfirmed} onChange={e=>setStatusConfirmed(e.target.checked)}/> I checked current cancellation/postponement status and recorded the evidence above.</label>
   <Button disabled={disabled||!statusConfirmed||notes.trim().length<20||!statusUrl||!/^\d{4}-\d{2}-\d{2}$/.test(saleDate)} onClick={()=>act('review_status')}>Save current sale review</Button>
  </details>
  {row.contacts.length>0&&<div><h3 className="font-semibold">Contact found — outreach eligibility review required</h3>{row.contacts.map((c,i)=><p key={i}>{c.name} · {c.phone} · {c.email}</p>)}<p>A skip trace does not record consent or clear suppression. No outreach has been queued by this handoff.</p></div>}
  {row.stage==='result_saved'&&row.contacts.length===0&&<p>Saved result has no contacts available. Review the original receipt; do not purchase another trace automatically.</p>}
  {row.handoff?.follow_up_task_id&&<a href="/tasks" className="underline">View assigned follow-up task</a>}
 </details>;
}
