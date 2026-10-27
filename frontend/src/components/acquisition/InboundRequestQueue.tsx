import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { InboundRequestReview } from './InboundRequestReview';
import { InboundRequests } from './InboundRequests';

type Item = { id: string; integration_id: string; call_id: string; request_kind: 'request_callback' | 'request_human'; revision: number; created_at: string; review_status: string; review_sequence: number; review_current: boolean; assigned_user_id: string | null };
type Page = { workspace_id: string; items: Item[]; next_after: string | null; checked_at: string; revision_scope: string; review_status_available: true; filters: {status: string; assignment: string}; execution_authorized: false };
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v);
const statusLabels: Record<string,string> = {all:'All reviews',open:'Open reviews',pending_review:'Pending review',assigned:'Assigned',on_hold:'On hold',review_complete:'Review complete',requires_review:'Needs fresh review',unassigned:'Released assignment'};
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const ignorePending = () => {};
export function InboundRequestQueue({ userId, workspace, onPending = ignorePending }: { userId: string; workspace: string; onPending?: (pending: boolean) => void }) {
  const selectionKey = `inbound-review-selection:v1:${userId}:${workspace}`;
  const [initial] = useState(() => { try { const value=sessionStorage.getItem(selectionKey); return {task:uuid(value)?value:null,invalid:value!==null && !uuid(value)}; } catch { return {task:null,invalid:true}; } });
  const [reviewTask,setReviewTask] = useState<string|null>(initial.task);
  const [reviewPending,setReviewPending] = useState(false);
  const [selectionError,setSelectionError] = useState(initial.invalid);
  const [open, setOpen] = useState(!!initial.task);
  useEffect(()=>{onPending(reviewPending || selectionError);},[reviewPending,selectionError,onPending]);
  function selectReview(task: string) { try { sessionStorage.setItem(selectionKey,task);setReviewTask(task);setSelectionError(false); } catch { setSelectionError(true); } }
  function closeReview() { try { sessionStorage.removeItem(selectionKey);setReviewTask(null);setReviewPending(false);setSelectionError(false); } catch { setSelectionError(true); } }
  const [statusFilter,setStatusFilter] = useState('open');
  const [assignmentFilter,setAssignmentFilter] = useState('all');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selected, setSelected] = useState<Item | null>(null);
  const after = cursors.at(-1) ?? null;
  const page = useQuery({queryKey:['inbound-request-queue',userId,workspace,statusFilter,assignmentFilter,after],enabled:open,retry:false,gcTime:0,staleTime:0,refetchOnWindowFocus:false,
    queryFn:async({signal}):Promise<Page>=>{
      const value = await (await apiFetch(`/api/acquisition/workspaces/${workspace}/inbound/requests?limit=20&status=${statusFilter}&assignment=${assignmentFilter}${after ? `&after=${after}` : ''}`,{signal})).json() as Page;
      if (!value || value.workspace_id !== workspace || value.execution_authorized !== false || value.review_status_available !== true || value.filters?.status !== statusFilter || value.filters?.assignment !== assignmentFilter
        || value.revision_scope !== 'latest_per_call_and_kind_at_read' || !Number.isFinite(Date.parse(value.checked_at))
        || !Array.isArray(value.items) || value.items.length > 20
        || !value.items.every(r=>r && uuid(r.id) && uuid(r.integration_id) && /^[A-Za-z0-9_-]{1,200}$/.test(r.call_id)
          && Number.isInteger(r.review_sequence) && r.review_sequence>=0 && typeof r.review_current==='boolean'
          && (r.review_current ? r.review_sequence>0 && ['assigned','on_hold','review_complete','unassigned'].includes(r.review_status) && (r.review_status==='unassigned'?r.assigned_user_id===null:uuid(r.assigned_user_id)) : r.assigned_user_id===null && r.review_status===(r.review_sequence===0?'pending_review':'requires_review'))
          && (statusFilter==='all' || statusFilter==='open' && r.review_status!=='review_complete' || r.review_status===statusFilter)
          && (assignmentFilter==='all' || assignmentFilter==='mine' && r.assigned_user_id===userId || assignmentFilter==='unassigned' && r.assigned_user_id===null)
          && ['request_callback','request_human'].includes(r.request_kind) && Number.isInteger(r.revision) && r.revision>0 && r.revision<=1e9 && Number.isFinite(Date.parse(r.created_at)))
        || value.items.some((r,i)=>(after !== null && r.id<=after) || (i>0 && r.id<=value.items[i-1].id))
        || !(value.next_after === null || uuid(value.next_after) && value.items.length===20 && value.next_after===value.items.at(-1)?.id)) throw new Error('Invalid inbound queue');
      return value;
    }});
  return <section className="rounded-xl border bg-white p-4 space-y-3" aria-label="Inbound request queue">
    <h2 className="font-semibold text-lg"><button disabled={reviewPending || selectionError} aria-expanded={open} onClick={()=>{setOpen(v=>!v);setSelected(null);}}>Inbound callback and assistance requests</button></h2>
    {open && <><p className="text-sm">Includes calls without a completed intake. Each row is the latest request of its kind for that call when this page was read. Refresh to check for new revisions. Status and assignment reflect this read, including stale-review checks. Refresh after changes elsewhere. These rows are not transaction or contact totals; no callback or transfer is scheduled.</p>
      <fieldset disabled={reviewPending || selectionError || page.isFetching} className="flex flex-wrap gap-3">
        <label className="text-sm">Review status<select className="block border rounded p-2" value={statusFilter} onChange={e=>{setStatusFilter(e.target.value);setCursors([null]);setSelected(null);}}>{Object.entries(statusLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label className="text-sm">Assignment filter<select className="block border rounded p-2" value={assignmentFilter} onChange={e=>{setAssignmentFilter(e.target.value);setCursors([null]);setSelected(null);}}><option value="all">All assignments</option><option value="mine">Assigned to me</option><option value="unassigned">No current assignee</option></select></label>
      </fieldset>
      <button className={button} disabled={page.isFetching || reviewPending || selectionError} onClick={()=>{setSelected(null);if(after)setCursors([null]);else void page.refetch();}}>Refresh request queue</button>
      {page.isFetching ? <p role="status">Checking inbound request queue…</p> : page.isError ? <p role="alert">Inbound queue unavailable. Verify workspace access and refresh.</p> : page.data && <>
        <p className="text-xs">Checked: {page.data.checked_at}</p>
        {!page.data.items.length && <p>No requests on this page.</p>}
        <ol className="space-y-3">{page.data.items.map(row=><li key={row.id} className="border rounded p-3 text-sm break-all">
          <h3 className="font-semibold">{row.request_kind==='request_callback'?'Callback requested':'Human assistance requested'} · revision {row.revision}</h3>
          <p>Status: {statusLabels[row.review_status]} · review {row.review_sequence}</p><p>Assignee: {row.assigned_user_id===userId?'Me':row.assigned_user_id??'None'}</p><p>Call: {row.call_id}</p><p>Integration: {row.integration_id}</p><p>Saved: {row.created_at}</p>
          <button className={button} disabled={reviewPending || selectionError} onClick={()=>setSelected(row)}>View call request history</button>
          <button className={button} disabled={reviewPending || selectionError} onClick={()=>selectReview(row.id)}>Review request</button>
        </li>)}</ol>
        {selected && page.data.items.some(r=>r.id===selected.id) && <InboundRequests initiallyOpen key={`${workspace}:${selected.integration_id}:${selected.call_id}`} userId={userId} workspace={workspace} contextId={selected.id} integration={selected.integration_id} call={selected.call_id} />}
      </>}
      <nav aria-label="Inbound queue pages" className="flex flex-wrap gap-2">
        <button className={button} disabled={page.isFetching || reviewPending || selectionError || cursors.length===1} onClick={()=>{setSelected(null);setCursors(v=>v.slice(0,-1));}}>Previous request page</button>
        <button className={button} disabled={page.isFetching || reviewPending || selectionError || page.isError || !page.data?.next_after} onClick={()=>{if(page.data?.next_after){setSelected(null);setCursors(v=>[...v,page.data!.next_after]);}}}>More request pages</button>
      </nav>
    </>}
    {selectionError && <p role="alert">Saved review selection is unavailable. Reconcile the browser session before starting another review.</p>}
    {reviewTask && <InboundRequestReview key={`${userId}:${workspace}:${reviewTask}`} userId={userId} workspace={workspace} task={reviewTask} onPending={setReviewPending} onClose={closeReview} onSaved={()=>{if(after)setCursors([null]);else void page.refetch();}} />}
  </section>;
}
