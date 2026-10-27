import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

type Request = { id: string; acquisition_revision: number; acquisition_request_kind: 'request_callback' | 'request_human'; acquisition_evidence: Record<string, unknown>; acquisition_phone: string | null; acquisition_request_hash: string; created_at: string };
type Page = { workspace_id: string; integration_id: string; call_id: string; items: Request[]; execution_authorized: false };
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v);
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.trim().length > 0 && v.length <= max;
function valid(row: Request) {
  if (!row || !uuid(row.id) || !Number.isInteger(row.acquisition_revision) || row.acquisition_revision < 1 || row.acquisition_revision > 1e9
    || !/^[a-f0-9]{64}$/.test(row.acquisition_request_hash) || !Number.isFinite(Date.parse(row.created_at))) return false;
  const e = row.acquisition_evidence;
  if (!e || typeof e !== 'object' || Array.isArray(e)) return false;
  if (row.acquisition_request_kind === 'request_callback') return Object.keys(e).length === 4 && e.requested_by_caller === true
    && text(e.phone, 100) && text(e.preferred_time, 500) && text(e.purpose, 500)
    && (row.acquisition_phone === null || /^\+[1-9][0-9]{7,14}$/.test(row.acquisition_phone));
  return row.acquisition_request_kind === 'request_human' && Object.keys(e).length === 3 && row.acquisition_phone === null
    && typeof e.requested_by_caller === 'boolean' && text(e.details, 1000)
    && ['caller_requested', 'unsupported_language', 'failed_transfer', 'sensitive_situation', 'unable_to_complete'].includes(String(e.reason))
    && (e.reason !== 'caller_requested' || e.requested_by_caller === true);
}
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
export function InboundRequests({ userId, workspace, contextId, integration, call, initiallyOpen = false }: { userId: string; workspace: string; contextId: string; integration: string; call: string; initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const after = cursors.at(-1) ?? null;
  const page = useQuery({ queryKey: ['intake-inbound-requests', userId, workspace, contextId, integration, call, after], enabled: open,
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false,
    queryFn: async ({ signal }): Promise<Page> => {
      const value = await (await apiFetch(`/api/acquisition/workspaces/${workspace}/inbound/integrations/${integration}/calls/${encodeURIComponent(call)}/requests?limit=20${after ? `&after=${after}` : ''}`, { signal })).json() as Page;
      if (!value || value.workspace_id !== workspace || value.integration_id !== integration || value.call_id !== call || value.execution_authorized !== false
        || !Array.isArray(value.items) || value.items.length > 20 || !value.items.every(valid)
        || value.items.some((row, i) => (after !== null && row.id <= after) || (i > 0 && row.id <= value.items[i - 1].id))) throw new Error('Invalid inbound request evidence');
      return value;
    } });
  return <section aria-label="Inbound follow-up requests" className="border rounded-lg p-3 space-y-3">
    <button className={button} aria-expanded={open} onClick={() => setOpen(v => !v)}>{open ? 'Hide inbound requests' : 'View inbound requests'}</button>
    {open && <><p className="text-sm">Saved requests from this call, including historical revisions. These are not scheduled callbacks or completed transfers. Contact requires a separate fresh eligibility decision. Completion status is not yet available here.</p>
      {page.isFetching ? <p role="status">Checking inbound requests…</p> : page.isError ? <p role="alert">Inbound requests unavailable. Refresh and verify workspace access.</p> : page.data && <>
        {page.data.items.length === 0 && <p>No saved requests on this page.</p>}
        <ol className="space-y-3">{page.data.items.map(row => <li key={row.id} className="border-b pb-3 text-sm break-words">
          <h5 className="font-semibold">{row.acquisition_request_kind === 'request_callback' ? 'Callback requested' : 'Human assistance requested'} · revision {row.acquisition_revision}</h5>
          <p>Saved: {row.created_at}</p>
          {row.acquisition_request_kind === 'request_callback' ? <><p>Caller-provided phone: {String(row.acquisition_evidence.phone)}</p><p>Normalized candidate: {row.acquisition_phone ?? 'Unavailable'} — not verified</p><p>Requested time: {String(row.acquisition_evidence.preferred_time)} — not scheduled</p><p>Purpose: {String(row.acquisition_evidence.purpose)}</p></> : <><p>Reason: {String(row.acquisition_evidence.reason).replaceAll('_', ' ')}</p><p>{String(row.acquisition_evidence.details)}</p><p>{row.acquisition_evidence.requested_by_caller ? 'Requested by caller' : 'Raised by intake assistant'}</p></>}
          <details><summary>Request evidence</summary><p className="break-all">Record: {row.id}</p><p className="break-all">Fingerprint: {row.acquisition_request_hash}</p></details>
        </li>)}</ol>
      </>}
      <nav aria-label="Inbound request pages" className="flex flex-wrap gap-2">
        <button className={button} disabled={page.isFetching || cursors.length === 1} onClick={() => setCursors(v => v.slice(0, -1))}>Previous requests</button>
        <button className={button} disabled={page.isFetching || page.isError || page.data?.items.length !== 20} onClick={() => { const last = page.data?.items.at(-1); if (last) setCursors(v => [...v, last.id]); }}>More requests</button>
        <button className={button} disabled={page.isFetching} onClick={() => { if (after) setCursors([null]); else void page.refetch(); }}>Refresh inbound requests</button>
      </nav>
    </>}
  </section>;
}
