import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { InboundRequests } from './InboundRequests';

type Item = { id: string; integration_id: string; call_id: string; request_kind: 'request_callback' | 'request_human'; revision: number; created_at: string };
type Page = { workspace_id: string; items: Item[]; next_after: string | null; checked_at: string; revision_scope: string; review_status_available: false; execution_authorized: false };
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v);
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
export function InboundRequestQueue({ userId, workspace }: { userId: string; workspace: string }) {
  const [open, setOpen] = useState(false);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selected, setSelected] = useState<Item | null>(null);
  const after = cursors.at(-1) ?? null;
  const page = useQuery({queryKey:['inbound-request-queue',userId,workspace,after],enabled:open,retry:false,gcTime:0,staleTime:0,refetchOnWindowFocus:false,
    queryFn:async({signal}):Promise<Page>=>{
      const value = await (await apiFetch(`/api/acquisition/workspaces/${workspace}/inbound/requests?limit=20${after ? `&after=${after}` : ''}`,{signal})).json() as Page;
      if (!value || value.workspace_id !== workspace || value.execution_authorized !== false || value.review_status_available !== false
        || value.revision_scope !== 'latest_per_call_and_kind_at_read' || !Number.isFinite(Date.parse(value.checked_at))
        || !Array.isArray(value.items) || value.items.length > 20
        || !value.items.every(r=>r && uuid(r.id) && uuid(r.integration_id) && /^[A-Za-z0-9_-]{1,200}$/.test(r.call_id)
          && ['request_callback','request_human'].includes(r.request_kind) && Number.isInteger(r.revision) && r.revision>0 && r.revision<=1e9 && Number.isFinite(Date.parse(r.created_at)))
        || value.items.some((r,i)=>(after !== null && r.id<=after) || (i>0 && r.id<=value.items[i-1].id))
        || !(value.next_after === null || uuid(value.next_after) && value.items.length===20 && value.next_after===value.items.at(-1)?.id)) throw new Error('Invalid inbound queue');
      return value;
    }});
  return <section className="rounded-xl border bg-white p-4 space-y-3" aria-label="Inbound request queue">
    <h2 className="font-semibold text-lg"><button aria-expanded={open} onClick={()=>{setOpen(v=>!v);setSelected(null);}}>Inbound callback and assistance requests</button></h2>
    {open && <><p className="text-sm">Includes calls without a completed intake. Each row is the latest request of its kind for that call when this page was read. Refresh to check for new revisions. Review completion is not yet tracked here; no callback or transfer is scheduled.</p>
      <button className={button} disabled={page.isFetching} onClick={()=>{setSelected(null);if(after)setCursors([null]);else void page.refetch();}}>Refresh request queue</button>
      {page.isFetching ? <p role="status">Checking inbound request queue…</p> : page.isError ? <p role="alert">Inbound queue unavailable. Verify workspace access and refresh.</p> : page.data && <>
        <p className="text-xs">Checked: {page.data.checked_at}</p>
        {!page.data.items.length && <p>No requests on this page.</p>}
        <ol className="space-y-3">{page.data.items.map(row=><li key={row.id} className="border rounded p-3 text-sm break-all">
          <h3 className="font-semibold">{row.request_kind==='request_callback'?'Callback requested':'Human assistance requested'} · revision {row.revision}</h3>
          <p>Call: {row.call_id}</p><p>Integration: {row.integration_id}</p><p>Saved: {row.created_at}</p>
          <button className={button} onClick={()=>setSelected(row)}>View call request history</button>
        </li>)}</ol>
        {selected && page.data.items.some(r=>r.id===selected.id) && <InboundRequests initiallyOpen key={`${workspace}:${selected.integration_id}:${selected.call_id}`} userId={userId} workspace={workspace} contextId={selected.id} integration={selected.integration_id} call={selected.call_id} />}
      </>}
      <nav aria-label="Inbound queue pages" className="flex flex-wrap gap-2">
        <button className={button} disabled={page.isFetching || cursors.length===1} onClick={()=>{setSelected(null);setCursors(v=>v.slice(0,-1));}}>Previous request page</button>
        <button className={button} disabled={page.isFetching || page.isError || !page.data?.next_after} onClick={()=>{if(page.data?.next_after){setSelected(null);setCursors(v=>[...v,page.data!.next_after]);}}}>More request pages</button>
      </nav>
    </>}
  </section>;
}
