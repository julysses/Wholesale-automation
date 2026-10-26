import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { InquiryRecovery } from './InquiryRecovery';

type Item = { updated_at?: string; receipt_id: string; provider: string; state: string; attempts: number; reason_code: string | null;
  guidance: string; next_attempt_at: string; lease_expires_at: string | null; blockers: string[] };
type Health = { summary: Record<string, number>; items: Item[]; next_after: string | null; checked_at: string };
const metrics = [['requires_review', 'Need review'], ['retrying', 'Retrying'], ['expired_leases', 'Expired leases'],
  ['awaiting_worker', 'Awaiting worker'], ['leased', 'Processing'], ['completed', 'Completed']] as const;
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const date = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString() : 'Unavailable';
async function load(path: string, signal: AbortSignal): Promise<Health> {
  const value = await (await apiFetch(path, { signal })).json();
  if (!value || !value.summary || !Array.isArray(value.items) || typeof value.checked_at !== 'string'
    || (value.next_after !== null && typeof value.next_after !== 'string')
    || !metrics.every(([key]) => Number.isInteger(value.summary[key]) && value.summary[key] >= 0)
    || !value.items.every((item: Item) => typeof item.receipt_id === 'string' && typeof item.guidance === 'string'
      && typeof item.state === 'string' && typeof item.provider === 'string' && Number.isInteger(item.attempts)
      && (item.reason_code === null || typeof item.reason_code === 'string')
      && Array.isArray(item.blockers) && item.blockers.every(code => typeof code === 'string')))
    throw new Error('Invalid inquiry health response');
  return value;
}

export function InquiryHealth({ userId, workspace }: { userId: string; workspace: string }) {
  return <ScopedHealth key={`${userId}:${workspace}`} userId={userId} workspace={workspace} />;
}
function ScopedHealth({ userId, workspace }: { userId: string; workspace: string }) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selected, setSelected] = useState<{ item: Item; path: string } | null>(null);
  const after = cursors[cursors.length - 1];
  const healthPath = `/api/acquisition/workspaces/${workspace}/inquiries/health?limit=20${after ? `&after=${encodeURIComponent(after)}` : ''}`;
  const query = useQuery({ queryKey: ['acquisition-inquiry-health', userId, workspace, after],
    queryFn: ({ signal }) => load(healthPath, signal),
    retry: false, gcTime: 0, staleTime: 0 });
  return <section aria-labelledby="inquiry-health-title" className="rounded-xl border bg-white p-4 space-y-4">
    <div className="flex flex-wrap gap-3 items-center justify-between"><h2 id="inquiry-health-title" className="font-semibold text-lg">Seller inquiry health</h2>
      <button className={button} disabled={query.isFetching} onClick={() => { void query.refetch(); }}>Refresh inquiry health</button></div>
    <p className="text-sm text-gray-600">Review processing issues before approving recovery. Reviewed recovery requires owner/admin approval and MFA.</p>
    {query.isFetching ? <p role="status">Loading inquiry health…</p> : query.isError ?
      <p role="alert">Inquiry health is unavailable. Refresh or check your workspace access.</p> : query.data && <>
        {query.data.summary.requires_review > 0 && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-amber-900">{query.data.summary.requires_review} {query.data.summary.requires_review === 1 ? 'inquiry needs' : 'inquiries need'} review.</p>}
        <dl className="grid grid-cols-2 md:grid-cols-3 gap-3">{metrics.map(([key, label]) => <div key={key} className="rounded-lg bg-gray-50 p-3">
          <dt className="text-sm text-gray-600">{label}</dt><dd className="font-semibold text-xl">{query.data!.summary[key]}</dd></div>)}</dl>
        <p className="text-xs text-gray-500">Database status checked {date(query.data.checked_at)}. Worker runtime has not been independently verified.</p>
        {query.data.items.length === 0 && <p>No unfinished inquiries on this page.</p>}
        <ul className="space-y-3">{query.data.items.map(item => <li key={item.receipt_id} className="border rounded-lg p-3 space-y-2">
          <p className="font-medium capitalize">{item.provider} · {item.state.replaceAll('_', ' ')} · Attempt {item.attempts}</p>
          {item.reason_code && <p className="text-sm capitalize">{item.reason_code.replaceAll('_', ' ').toLowerCase()}</p>}
          <p className="text-sm">{item.guidance}</p>
          {item.blockers.length > 0 && <p className="text-sm text-amber-800">{item.blockers.map(code => code.replaceAll('_', ' ').toLowerCase()).join(' · ')}</p>}
          {item.state === 'retry' && <p className="text-xs">Next attempt after {date(item.next_attempt_at)}</p>}
          {item.state === 'leased' && <p className="text-xs">Lease expires {date(item.lease_expires_at)}</p>}
          {item.state === 'review' && <button className={button} disabled={!!selected} onClick={() => setSelected({ item, path: healthPath })}>Review hold</button>}
          <details className="text-xs text-gray-500"><summary>Inquiry reference</summary><p className="break-all mt-1">{item.receipt_id}</p></details>
        </li>)}</ul>
      </>}
    {selected && <InquiryRecovery key={selected.item.receipt_id} userId={userId} workspace={workspace} item={selected.item} healthPath={selected.path} onSaved={() => { void query.refetch(); }} onClose={() => setSelected(null)} />}
    <nav aria-label="Inquiry health pages" className="flex gap-2">
      <button className={button} disabled={query.isFetching || cursors.length === 1} onClick={() => setCursors(c => c.slice(0, -1))}>Previous inquiries</button>
      <button className={button} disabled={query.isFetching || query.isError || !query.data?.next_after} onClick={() => { if (query.data?.next_after) setCursors(c => [...c, query.data!.next_after]); }}>More inquiries</button>
    </nav>
  </section>;
}
