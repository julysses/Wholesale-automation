import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useProfile } from '@/hooks/useProfile';
import { ForeclosureActions } from '@/components/lists/ForeclosureActions';

type Snapshot = { day: string; review_count: number; runs: { id: string; status: string; processing_status: string; records_new: number; records_stacked: number; status_reason: string }[] };
type TraceSnapshot = { total: number; total_budget: { remaining_cents: number; committed_cents: number }; items: { lead_id: string; county: string; address_std: string; stage: string; handoff: { follow_up_task_id: string | null } | null }[] };
const stages: Record<string, string> = {
  current_status_review: 'On hold — current sale needs verification',
  identity_incomplete: 'On hold — owner identity needs verification',
  quote_and_evidence_required: 'Waiting for verified evidence and provider quote',
  reserved: 'Quote reserved — provider submission pending',
  reconciliation_required: 'Provider result needs reconciliation — do not reorder',
  result_saved: 'Result saved — outreach eligibility remains separate',
  suppressed: 'Suppressed — no new tracing or outreach',
};
export function DailyLists() {
  const { isAdmin, profile } = useProfile();
  return isAdmin && profile ? <Pipeline key={profile.id} actor={profile.id} /> : <p>Administrator access required.</p>;
}
function Pipeline({ actor }: { actor: string }) {
  const [offset, setOffset] = useState(0);
  const query = useQuery<Snapshot>({ queryKey: ['daily-lists', actor], refetchInterval: 60000,
    queryFn: async () => (await apiFetch('/api/operations/lists?offset=0')).json() });
  const traces = useQuery<TraceSnapshot>({ queryKey: ['propstream-handoff', actor, offset], refetchInterval: 60000,
    queryFn: async () => (await apiFetch(`/api/operations/lists/propstream?offset=${offset}`)).json() });
  return <div className="space-y-6">
    <header><h1 className="text-2xl font-bold">Daily lead pipeline</h1>
      <p>Dallas and Collin · Bulk sourcing → verification → skip tracing → outreach preparation</p></header>
    <section aria-label="Automation readiness" className="rounded-xl border border-amber-400 bg-amber-50 p-5 space-y-2">
      <h2 className="text-lg font-semibold">Automation setup in progress</h2>
      <p>Daily scheduling and automatic provider processing are not active. Bulk collection is being verified before launch.</p>
      <p>This page shows saved results and exceptions. No CSV uploads or lead-by-lead entry are required here.</p>
    </section>
    {query.isPending && <p>Loading collection receipts…</p>}
    {query.error && <p role="alert">Collection status unavailable. <Button onClick={() => query.refetch()}>Retry collection status</Button></p>}
    {query.data && !query.error && <section aria-label="Collection status" className="rounded-xl border bg-white p-5 space-y-3">
      <h2 className="text-xl font-semibold">Collection and verification</h2>
      <p>{query.data.day} · {query.data.review_count.toLocaleString()} source records awaiting evidence across all list types</p>
      {!query.data.runs.length && <p>No collection receipts for this date. This does not mean there are no new county notices.</p>}
      {query.data.runs.map(run => <article key={run.id} className="border-t pt-3">
        <p className="font-medium">{run.status.replaceAll('_', ' ')} · {run.processing_status.replaceAll('_', ' ')}</p>
        <p>{run.records_new} new CRM leads · {run.records_stacked} added observations</p><p>{run.status_reason}</p>
      </article>)}
    </section>}
    <ForeclosureActions />
    <section aria-label="Skip tracing and follow-up" className="rounded-xl border bg-white p-5 space-y-3">
      <h2 className="text-xl font-semibold">Skip tracing and follow-up</h2>
      <p>Only new eligible leads proceed. Existing results are reused; uncertain orders stay on hold to avoid duplicate charges.</p>
      {traces.isPending && <p>Loading saved tracing status…</p>}
      {traces.error && <p role="alert">Tracing status unavailable. <Button onClick={() => traces.refetch()}>Retry tracing status</Button></p>}
      {traces.data && !traces.error && <>
        <p>${(traces.data.total_budget.remaining_cents / 100).toFixed(2)} remaining in the $50 total limit · ${(traces.data.total_budget.committed_cents / 100).toFixed(2)} committed</p>
        <p>{traces.data.total} associated foreclosure properties. Association alone does not establish tracing or outreach eligibility.</p>
        {!traces.data.total && <p>No foreclosure properties have reached the tracing queue yet.</p>}
        {traces.data.items.map(row => <article key={row.lead_id} className="border-t pt-3">
          <h3 className="font-semibold">{row.address_std} · {row.county}</h3>
          <p>{stages[row.stage] ?? 'On hold — eligibility check pending'}</p>
          {row.handoff?.follow_up_task_id && <p>Follow-up task saved in the CRM.</p>}
        </article>)}
        <div className="flex items-center gap-3"><Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous properties</Button>
          <span>{traces.data.total ? offset + 1 : 0}–{Math.min(offset + 50, traces.data.total)} of {traces.data.total}</span>
          <Button disabled={offset + 50 >= traces.data.total} onClick={() => setOffset(offset + 50)}>Next properties</Button></div>
      </>}
      <p className="text-sm text-gray-600">A returned phone number does not authorize automated messaging. Outreach stays on hold until its channel checks pass.</p>
    </section>
  </div>;
}
