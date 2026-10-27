import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type Status = 'unassigned' | 'assigned' | 'on_hold' | 'review_complete';
type Decision = { id: string; expected_sequence: number; request_hash: string; status: Status; assigned_user_id: string | null; review_note: string };
type Review = { id: string; workspace_id: string; task_id: string; sequence: number; request_hash: string; status: Status; assigned_user_id: string | null; review_note: string; actor_id: string; created_at: string };
type State = { workspace_id: string; task_id: string; sequence: number; request_hash: string; latest_review: Review | null; request_current: boolean; review_current: boolean; status: Status | 'pending_review' | 'requires_review' | 'superseded' | 'withdrawn'; assigned_user_id: string | null; execution_authorized: false; contact_permission_granted: false; checked_at: string };
type Member = {workspace_id: string; user_id: string; role: string; status: string};
const statuses: Record<Status,string> = {unassigned:'Release assignment',assigned:'Assign or reopen review',on_hold:'Place review on hold',review_complete:'Complete review'};
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const options = {retry:false,gcTime:0,staleTime:0,refetchOnWindowFocus:false} as const;
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded border p-2';
const allowedRole = (v: string) => ['owner','admin','operator'].includes(v);
function validDecision(v: Decision) {
 return v && uuid(v.id) && Number.isInteger(v.expected_sequence) && v.expected_sequence>=0 && v.expected_sequence<1e9 && hash(v.request_hash)
  && Object.hasOwn(statuses,v.status) && (v.status==='unassigned'?v.assigned_user_id===null:uuid(v.assigned_user_id))
  && typeof v.review_note==='string' && v.review_note.trim().length>=20 && v.review_note.length<=2000;
}
function validReview(v: Review,w: string,t: string) {
 return v && v.workspace_id===w && v.task_id===t && Number.isInteger(v.sequence) && v.sequence>0
  && validDecision({...v,expected_sequence:v.sequence-1}) && uuid(v.actor_id) && Number.isFinite(Date.parse(v.created_at));
}
async function read(path: string,signal?:AbortSignal){return (await apiFetch(path,{signal})).json();}
async function readState(path: string,w: string,t: string,signal?:AbortSignal):Promise<State>{
 const v=await read(path,signal) as State;
 if(!v || v.workspace_id!==w || v.task_id!==t || !hash(v.request_hash) || !Number.isInteger(v.sequence) || v.sequence<0
  || typeof v.request_current!=='boolean' || typeof v.review_current!=='boolean' || v.execution_authorized!==false || v.contact_permission_granted!==false
  || !Number.isFinite(Date.parse(v.checked_at)) || (v.assigned_user_id!==null && !uuid(v.assigned_user_id))
  || (v.sequence===0 ? v.latest_review!==null : !validReview(v.latest_review!,w,t) || v.latest_review!.sequence!==v.sequence || v.latest_review!.request_hash!==v.request_hash)
  || (v.review_current ? !v.request_current || !v.latest_review || v.status!==v.latest_review.status || v.assigned_user_id!==v.latest_review.assigned_user_id
    : v.assigned_user_id!==null || (!v.request_current ? !['superseded','withdrawn'].includes(v.status) : v.status!==(v.latest_review?'requires_review':'pending_review')))) throw new Error('Invalid review state');
 return v;
}
const ignoreSaved = () => {};
export function InboundRequestReview({userId,workspace,task,onPending,onClose,onSaved=ignoreSaved}:{userId:string;workspace:string;task:string;onPending:(value:boolean)=>void;onClose:()=>void;onSaved?:()=>void}){
 const path=`/api/acquisition/workspaces/${workspace}/inbound/requests/${task}`;
 const key=`inbound-request-review:v1:${userId}:${workspace}:${task}`;
 const [initial]=useState(()=>{try{const raw=sessionStorage.getItem(key);if(raw===null)return {request:null,invalid:false};const v=JSON.parse(raw) as Decision;if(!validDecision(v))throw new Error('Invalid pending request');return {request:v,invalid:false};}catch{return {request:null,invalid:true};}});
 const [pending,setPending]=useState<Decision|null>(initial.request);
 const [status,setStatus]=useState<Status>(initial.request?.status??'assigned');
 const [assignee,setAssignee]=useState(initial.request?.assigned_user_id??userId);
 const [note,setNote]=useState(initial.request?.review_note??'');const [ack,setAck]=useState(false);
 const [busy,setBusy]=useState(false);const inFlight=useRef(false);const [feedback,setFeedback]=useState('');
 const [before,setBefore]=useState<number|null>(null);
 useEffect(()=>{onPending(busy || !!pending || initial.invalid);},[busy,pending,initial.invalid,onPending]);
 const state=useQuery({...options,queryKey:['inbound-review-state',userId,workspace,task],queryFn:({signal})=>readState(path+'/state',workspace,task,signal)});
 const members=useQuery({...options,queryKey:['inbound-review-members',userId,workspace],queryFn:async({signal}):Promise<Member[]>=>{
  const rows=await read(`/api/acquisition/workspaces/${workspace}/memberships`,signal);
  if(!Array.isArray(rows) || !rows.every(r=>r && r.workspace_id===workspace && uuid(r.user_id) && typeof r.role==='string' && typeof r.status==='string'))throw new Error('Invalid membership evidence');return rows;
 }});
 const history=useQuery({...options,queryKey:['inbound-review-history',userId,workspace,task,before],queryFn:async({signal}):Promise<Review[]>=>{
  const rows=await read(path+`/reviews?limit=20${before?`&before=${before}`:''}`,signal);
  if(!Array.isArray(rows) || rows.length>20 || !rows.every((r,i)=>validReview(r,workspace,task) && (!before || r.sequence<before) && (i===0 || rows[i-1].sequence>r.sequence)))throw new Error('Invalid review history');return rows;
 }});
 const actor=members.data?.find(m=>m.user_id===userId && m.status==='active' && allowedRole(m.role));
 const operator=actor?.role==='operator';
 const available=!!actor && !members.isError && !members.isFetching && !!state.data && !state.isError && !state.isFetching && state.data.request_current && !!history.data && !history.isError && !history.isFetching;
 const assignmentValid=status==='unassigned' ? !operator || state.data?.assigned_user_id===userId
  : members.data?.some(m=>m.user_id===assignee && m.status==='active' && allowedRole(m.role)) && (!operator || assignee===userId);
 const outcomeValid=!['on_hold','review_complete'].includes(status) || state.data?.review_current && ['assigned','on_hold'].includes(state.data.status) && state.data.assigned_user_id===assignee;
 const valid=available && assignmentValid && outcomeValid && (!operator || !state.data?.assigned_user_id || state.data.assigned_user_id===userId) && ack && note.trim().length>=20 && !initial.invalid;
 async function save(){
  if(inFlight.current || initial.invalid || (!pending && !valid))return;
  inFlight.current=true;setBusy(true);setFeedback('');let request=pending;const retrying=!!pending;let sent=false;
  try{
   if(!request){const fresh=await readState(path+'/state',workspace,task);
    if(!fresh.request_current || fresh.sequence!==state.data!.sequence || fresh.request_hash!==state.data!.request_hash || fresh.status!==state.data!.status || fresh.assigned_user_id!==state.data!.assigned_user_id)throw new Error('State changed');
    request={id:crypto.randomUUID(),expected_sequence:fresh.sequence,request_hash:fresh.request_hash,status,assigned_user_id:status==='unassigned'?null:assignee,review_note:note.trim()};}
   sessionStorage.setItem(key,JSON.stringify(request));setPending(request);sent=true;
   const result=await (await apiFetch(path+'/reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)})).json();
   if(result?.review_id!==request.id || result.sequence!==request.expected_sequence+1 || typeof result.duplicate!=='boolean' || result.execution_authorized!==false)throw new Error('Unconfirmed receipt');
   sessionStorage.removeItem(key);setPending(null);setNote('');setAck(false);setBefore(null);setFeedback('Review decision recorded. No callback, transfer or seller contact was authorized.');void state.refetch();void history.refetch();onSaved();
  }catch(error){
   const rejected=!retrying && sent && error instanceof ApiError && [400,401,403,404,409,422].includes(error.status);
   if(rejected){try{sessionStorage.removeItem(key);setPending(null);}catch{/* Preserve reconciliation lock if storage cannot be cleared. */}}
   setFeedback((retrying || sent && !rejected)?'Result unconfirmed. Retry the exact request to reconcile it; do not create another decision.':'Review was not recorded. Refresh evidence and verify MFA, assignment and workspace access.');setAck(false);
  }finally{inFlight.current=false;setBusy(false);}
 }
 return <section aria-label="Inbound request review" className="border rounded-lg p-4 space-y-3">
  <h3 className="font-semibold">Assign and review request</h3><p className="text-xs break-all">Request record: {task}</p><p className="text-sm">Completing review records your decision, not a completed call or transfer. Seller contact still requires fresh eligibility approval. MFA is required to save.</p>
  {initial.invalid && <p role="alert">Pending review could not be recovered. Reconcile saved review history before changing this browser session.</p>}
  {state.isFetching?<p role="status">Checking current review…</p>:state.isError?<p role="alert">Current review unavailable. Refresh and verify access.</p>:state.data && <><p>Current status: {state.data.status.replaceAll('_',' ')}</p><p>Review sequence: {state.data.sequence}</p><p className="break-all">Current assignee: {state.data.assigned_user_id??'None'}</p>{!state.data.request_current && <p>{state.data.status==='withdrawn'?'The caller withdrew this callback or requested no contact. It cannot be reopened here.':'This request has been superseded. Review the newer request in the queue.'}</p>}</>}
  {members.isError && <p role="alert">Reviewer membership unavailable.</p>}
  {available && !outcomeValid && <p role="status">Assign this request first. Hold or completion must use the same current assignee.</p>}
  {available && operator && state.data?.assigned_user_id && state.data.assigned_user_id!==userId && <p role="status">This request is assigned to another reviewer. An administrator can reassign it.</p>}
  <fieldset disabled={busy || !!pending || !available || initial.invalid} className="space-y-2">
   <label className="block text-sm">Review action<select className={input} value={status} onChange={e=>{setStatus(e.target.value as Status);setAck(false);}}>{Object.entries(statuses).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   {status!=='unassigned' && <label className="block text-sm">Assigned reviewer<select className={input} value={assignee} onChange={e=>{setAssignee(e.target.value);setAck(false);}}><option value="">Select reviewer</option>{members.data?.filter(m=>m.status==='active' && allowedRole(m.role) && (!operator || m.user_id===userId)).map(m=><option key={m.user_id} value={m.user_id}>{m.user_id===userId?'Me':m.user_id} ({m.role})</option>)}</select></label>}
   <label className="block text-sm">Review note<textarea className={input} maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/></label>
   <label className="flex gap-2 text-sm"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I reviewed this request and understand this does not authorize contact.</label>
  </fieldset>
  <div className="flex flex-wrap gap-2"><button className={button} disabled={busy || initial.invalid || (!pending && !valid)} onClick={()=>{void save();}}>{busy?'Saving review…':pending?'Retry exact request review':'Save request review'}</button>
   <button className={button} disabled={busy || !!pending || initial.invalid} onClick={()=>{setAck(false);void state.refetch();void members.refetch();void history.refetch();}}>Refresh review evidence</button>
   <button className={button} disabled={busy || !!pending || initial.invalid} onClick={onClose}>Close request review</button></div>
  {feedback && <p role="status">{feedback}</p>}
  <h4 className="font-medium">Saved review history</h4>
  {history.isFetching?<p>Checking saved history…</p>:history.isError?<p role="alert">Review history unavailable.</p>:<>{!history.data?.length && <p>No saved reviews on this page.</p>}{history.data?.map(r=><div key={r.id} className="border rounded p-2 text-sm break-words"><p>{r.sequence} · {r.status.replaceAll('_',' ')} · {r.created_at}</p><p>{r.review_note}</p><p className="break-all">Recorded by {r.actor_id} · Assignee {r.assigned_user_id??'None'}</p></div>)}</>}
  <div className="flex gap-2"><button className={button} disabled={busy || !!pending || history.isFetching || before===null} onClick={()=>setBefore(null)}>Latest request reviews</button><button className={button} disabled={busy || !!pending || history.isFetching || history.isError || history.data?.length!==20} onClick={()=>setBefore(history.data!.at(-1)!.sequence)}>Older request reviews</button></div>
 </section>;
}
