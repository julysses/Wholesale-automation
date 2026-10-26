import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type Capture = { id: string; workspace_id: string; source_id: string; link_review_id: string; campaign_id: string; preparation_hash: string; created_at: string; attribution_current: boolean };
type Page = { workspace_id: string; source_id: string; preparation_hash: string; current_link_review_id: string | null; current_campaign_id: string | null; current_capture: Capture | null; items: Capture[]; next_after: string | null; execution_authorized: false };
type Pending = { id: string; link_review_id: string; campaign_id: string; preparation_hash: string };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const hash = /^[a-f0-9]{64}$/;
const options = { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false } as const;
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const validPending = (value: Pending) => value && uuid.test(value.id) && uuid.test(value.link_review_id) && uuid.test(value.campaign_id) && hash.test(value.preparation_hash);
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }
async function readPage(path: string, workspace: string, source: string, signal?: AbortSignal): Promise<Page> {
  const page = await read(path, signal) as Page;
  if (!page || page.workspace_id !== workspace || page.source_id !== source || !hash.test(page.preparation_hash) || page.execution_authorized !== false
    || !(page.current_link_review_id === null ? page.current_campaign_id === null : uuid.test(page.current_link_review_id) && uuid.test(page.current_campaign_id!))) throw new Error('Invalid attribution state');
  const valid = (row: Capture) => row && uuid.test(row.id) && row.workspace_id === workspace && row.source_id === source && uuid.test(row.link_review_id)
    && uuid.test(row.campaign_id) && row.preparation_hash === page.preparation_hash && typeof row.created_at === 'string'
    && typeof row.attribution_current === 'boolean' && row.attribution_current === (page.current_link_review_id !== null && row.link_review_id === page.current_link_review_id)
    && (!row.attribution_current || row.campaign_id === page.current_campaign_id);
  if (!Array.isArray(page.items) || page.items.length > 20 || !page.items.every(valid)
    || !(page.next_after === null || (uuid.test(page.next_after) && page.next_after === page.items.at(-1)?.id))
    || !(page.current_capture === null || valid(page.current_capture) && page.current_capture.attribution_current)) throw new Error('Invalid attribution history');
  return page;
}

export function SourceAttribution({ userId, workspace, intake, revision, locked, onPending }: { userId: string; workspace: string; intake: string; revision: number; locked: boolean; onPending: (pending: boolean) => void }) {
  const base = `/api/acquisition/workspaces/${workspace}`; const path = `${base}/intakes/${intake}/source-campaign-reviews`;
  const storageKey = `source-attribution:v1:${userId}:${workspace}:${intake}`;
  const [initial] = useState(() => { try {
    const raw = sessionStorage.getItem(storageKey); if (!raw) return { request: null, invalid: false };
    const value = JSON.parse(raw) as Pending; if (!validPending(value)) throw new Error('Invalid saved request'); return { request: value, invalid: false };
  } catch { return { request: null, invalid: true }; } });
  const [pending, setPending] = useState<Pending | null>(initial.request); const [busy, setBusy] = useState(false); const inFlight = useRef(false);
  const [feedback, setFeedback] = useState(''); const [cursors, setCursors] = useState<(string | null)[]>([null]); const after = cursors.at(-1);
  useEffect(() => { onPending(!!pending || busy || initial.invalid); }, [pending, busy, initial.invalid, onPending]);
  const history = useQuery({ ...options, queryKey: ['source-attribution', userId, workspace, intake, revision, after], queryFn: async ({ signal }) => {
    const result = await readPage(`${path}?limit=20${after ? `&after=${after}` : ''}`, workspace, intake, signal);
    if (after && result.next_after === after) throw new Error('Invalid history cursor'); return result;
  } });
  const access = useQuery({ ...options, queryKey: ['source-attribution-access', userId, workspace], queryFn: async ({ signal }) => {
    const rows = await read(`${base}/memberships`, signal);
    return Array.isArray(rows) && rows.some(row => row?.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin', 'operator'].includes(row.role));
  } });
  const available = !locked && !initial.invalid && access.data === true && !access.isError && !access.isFetching && !history.isError && !history.isFetching
    && !!history.data?.current_link_review_id && history.data.current_capture === null;
  async function capture() {
    if (inFlight.current || locked || initial.invalid || (!pending && !available)) return;
    inFlight.current = true; setBusy(true); setFeedback(''); let request = pending; const retrying = !!pending; let sent = false;
    try {
      if (!request) {
        const fresh = await readPage(`${path}?limit=20`, workspace, intake);
        if (!fresh.current_link_review_id || fresh.current_capture || fresh.current_link_review_id !== history.data!.current_link_review_id
          || fresh.current_campaign_id !== history.data!.current_campaign_id || fresh.preparation_hash !== history.data!.preparation_hash) throw new Error('Attribution changed');
        request = { id: crypto.randomUUID(), link_review_id: fresh.current_link_review_id, campaign_id: fresh.current_campaign_id!, preparation_hash: fresh.preparation_hash };
      }
      sessionStorage.setItem(storageKey, JSON.stringify(request)); setPending(request); sent = true;
      const result = await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: request.id, link_review_id: request.link_review_id }) })).json();
      if (result?.id !== request.id || result.source_id !== intake || result.link_review_id !== request.link_review_id || result.campaign_id !== request.campaign_id
        || typeof result.duplicate !== 'boolean' || result.execution_authorized !== false) throw new Error('Unconfirmed capture');
      sessionStorage.removeItem(storageKey); setPending(null); setCursors([null]);
      setFeedback('Attribution snapshot recorded. Its current status is checked against the latest campaign review.'); void history.refetch();
    } catch (error) {
      const rejected = !retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (rejected) { try { sessionStorage.removeItem(storageKey); setPending(null); } catch { /* Keep the original pending capture. */ } }
      setFeedback(rejected ? 'Capture rejected. Refresh attribution and check current workspace access.' : sent || retrying ? 'Capture result unconfirmed. Retry the exact capture; it is retained in this browser tab.' : 'Attribution changed or browser storage is unavailable. No capture was sent. Refresh before trying again.');
      if (!sent || rejected) void history.refetch();
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Source attribution snapshots" className="border rounded p-4 space-y-3">
    <h5 className="font-semibold">Source attribution snapshots</h5><p className="text-sm">Preserve this inquiry’s association with an exact reviewed campaign version. Corrections remain visible in history. This does not merge leads, report costs or authorize outreach.</p>
    {initial.invalid && <p role="alert">Saved capture could not be read. Reconcile the earlier capture before recording another in this tab.</p>}
    {history.isFetching ? <p>Checking attribution…</p> : history.isError ? <p role="alert">Source attribution unavailable. Verify campaign evidence and workspace access.</p> : history.data && <>
      <p className="text-sm">{history.data.current_capture ? 'The current campaign review has a recorded snapshot.' : history.data.current_link_review_id ? 'The current campaign review has not been captured for this inquiry.' : 'No current reviewed campaign is available for capture.'}</p>
      {history.data.current_capture && <p className="text-xs break-all">Current snapshot: {history.data.current_capture.id} · Campaign: {history.data.current_capture.campaign_id}</p>}
      <ol className="space-y-2">{history.data.items.map(row => <li key={row.id} className="border-b py-2 text-sm break-all"><strong>{row.attribution_current ? 'Current attribution' : 'Historical attribution'}</strong><p>Campaign: {row.campaign_id}</p><p>Review: {row.link_review_id}</p><p>Snapshot: {row.id} · {row.created_at}</p></li>)}</ol>
      {history.data.items.length === 0 && <p className="text-sm">No snapshots on this page.</p>}
    </>}
    <div className="flex flex-wrap gap-2"><button className={button} disabled={busy || locked || initial.invalid || (!pending && !available)} onClick={() => { void capture(); }}>{busy ? 'Recording attribution…' : pending ? 'Retry exact attribution capture' : 'Capture current attribution'}</button><button className={button} disabled={busy} onClick={() => { void history.refetch(); void access.refetch(); }}>Refresh source attribution</button></div>
    <nav aria-label="Source snapshot pages" className="flex gap-2"><button className={button} disabled={history.isFetching || cursors.length === 1} onClick={() => setCursors(value => value.slice(0, -1))}>Previous snapshots</button><button className={button} disabled={history.isFetching || history.isError || !history.data?.next_after} onClick={() => { if (history.data?.next_after) setCursors(value => [...value, history.data!.next_after]); }}>More snapshots</button></nav>
    {pending && <p className="text-xs break-all">Pending capture: {pending.id}</p>}{feedback && <p role="status">{feedback}</p>}
  </section>;
}
