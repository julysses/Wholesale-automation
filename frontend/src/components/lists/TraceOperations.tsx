import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { apiFetch, ApiError } from '@/lib/api';
import { useProfile } from '@/hooks/useProfile';
const count=z.number().int().nonnegative();
const requestSchema=z.object({id:z.string().uuid(),lead_id:z.string().uuid(),provider:z.string(),spend_day:z.string(),reserved_cents:count,state:z.enum(['reserved','submitted','unknown']),created_at:z.string()});
const snapshotSchema=z.object({total_budget:z.object({cap_cents:count,reserved_cents:count,actual_cents:count,committed_cents:count,remaining_cents:count}).optional(),day:z.string(),budget:z.object({cap_cents:count,reserved_cents:count,actual_cents:count}).nullable(),total_held_cents:count,open_count:count,requests:z.array(requestSchema).max(50),recent_actions:z.array(z.object({id:z.string().uuid(),operator_id:z.string().uuid(),request_id:z.string().uuid(),action:z.literal('cancel_reserved'),created_at:z.string()})).max(20)});
const pendingSchema=z.object({event_id:z.string().uuid(),trace_id:z.string().uuid()});
const receiptSchema=z.object({event:z.object({id:z.string().uuid(),operator_id:z.string().uuid(),request_id:z.string().uuid(),action:z.literal('cancel_reserved'),result:z.object({request:z.object({id:z.string().uuid(),state:z.literal('failed'),actual_cents:z.literal(0),provider_job_id:z.literal('not_submitted')})})})});
const money=(cents:number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
export function TraceOperations(){
 const {profile,isAdmin}=useProfile();
 return isAdmin&&profile?<Controls key={profile.id} actor={profile.id}/>:null;
}
function Controls({actor}:{actor:string}){
 const storageKey=`hilltop.trace-cancel.v1.${actor}`;
 const [initial]=useState(()=>{try{const raw=sessionStorage.getItem(storageKey);return {pending:raw?pendingSchema.parse(JSON.parse(raw)):null,error:''};}catch{return {pending:null,error:'Saved cancellation recovery data is unreadable. Review the record before another action.'};}});
 const [pending,setPending]=useState(initial.pending);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState(initial.error);
 const [notice,setNotice]=useState('');
 const [offset,setOffset]=useState(0);
 const query=useQuery({queryKey:['list-tracing',actor,offset],queryFn:async()=>snapshotSchema.parse(await(await apiFetch(`/api/operations/lists/tracing?offset=${offset}`)).json())});
 async function cancel(traceId:string){
  if(busy||initial.error)return;
  setBusy(true);setError('');setNotice('');
  const decision=pending??{event_id:crypto.randomUUID(),trace_id:traceId};
  try{
   sessionStorage.setItem(storageKey,JSON.stringify(decision));setPending(decision);
   const receipt=receiptSchema.parse(await(await apiFetch(`/api/operations/lists/tracing/${decision.trace_id}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id:decision.event_id})})).json());
   const event=receipt.event;
   if(event.id!==decision.event_id||event.operator_id!==actor||event.request_id!==decision.trace_id||event.result.request.id!==decision.trace_id)throw new Error('Cancellation acknowledgement did not match the request.');
   sessionStorage.removeItem(storageKey);setPending(null);
   setNotice(`Unsubmitted reservation canceled. Audit reference: ${event.id}. No provider request was sent by this action.`);
   await query.refetch();
  }catch(e){
   if(e instanceof ApiError&&e.status===409){sessionStorage.removeItem(storageKey);setPending(null);await query.refetch();}
   setError(e instanceof Error?e.message:'Cancellation is unconfirmed. Retry the saved reference.');
  }finally{setBusy(false);}
 }
 const data=query.data;
 return <section aria-label="Tracing operations" className="rounded-xl border bg-white p-4 space-y-3">
  <h2 className="text-xl font-semibold">Tracing budgets and recovery</h2>
  <p>A budget does not enable paid tracing. Provider setup and launch acceptance are separate. Submitted or uncertain requests must be reconciled with the provider before funds can be released.</p>
  <button className="rounded border px-3 py-2" type="button" disabled={busy||query.isFetching} onClick={()=>void query.refetch()}>Refresh tracing status</button>
  {query.isLoading&&<p>Loading tracing status…</p>}
  {query.error&&<p role="alert">Tracing status is unavailable: {query.error.message}</p>}
  {error&&<p role="alert">{error}</p>}
  {notice&&<p role="status">{notice}</p>}
  {pending&&<div role="alert"><p>Unconfirmed cancellation: {pending.trace_id}. Event: {pending.event_id}.</p><button className="rounded border px-3 py-2" type="button" disabled={busy} onClick={()=>void cancel(pending.trace_id)}>Retry saved cancellation</button></div>}
  {data&&<>
   {data.total_budget?<p>Total authorization: {money(data.total_budget.cap_cents)} · Committed across all days: {money(data.total_budget.committed_cents)} · Remaining: {money(data.total_budget.remaining_cents)}. This cap does not reset daily; verify the provider balance separately.</p>:<p role="alert">Total authorization status unavailable. Do not submit paid tracing until the cumulative budget is verified.</p>}
   <p>{data.day} · Central time</p>
   {data.budget?<p>Daily cap: {money(data.budget.cap_cents)} · Reserved today: {money(data.budget.reserved_cents)} · Confirmed spend: {money(data.budget.actual_cents)}</p>:<p>No daily budget configured. New tracing reservations are blocked.</p>}
   <p>Reserved across all days: {money(data.total_held_cents)} · {data.open_count} unresolved requests</p>
   {!data.open_count&&<p>No unresolved tracing requests.</p>}
   {data.requests.map(row=><article className="rounded border p-3 space-y-1" key={row.id}>
    <p>{row.provider} · {row.state} · {money(row.reserved_cents)} reserved on {row.spend_day}</p>
    <p className="break-all">Request: {row.id} · Lead: {row.lead_id}</p>
    {row.state==='reserved'?<button className="rounded border px-3 py-2" type="button" disabled={busy||!!pending||!!initial.error||!!query.error} onClick={()=>void cancel(row.id)}>Cancel unsubmitted reservation</button>:<p>Provider reconciliation required. Do not resend or release this hold from an assumed failure.</p>}
   </article>)}
   <div className="flex gap-2"><button type="button" disabled={offset===0||busy} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous 50 tracing requests</button><button type="button" disabled={offset+50>=data.open_count||busy} onClick={()=>setOffset(offset+50)}>Next 50 tracing requests</button></div>
   <h3 className="font-semibold">Recent cancellation audit</h3>
   {data.recent_actions.map(event=><p className="break-all" key={event.id}>{event.request_id} canceled by {event.operator_id} at {event.created_at} · Audit {event.id}</p>)}
  </>}
 </section>;
}
