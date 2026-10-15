import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useProfile } from '@/hooks/useProfile';
import { ForeclosureActions } from '@/components/lists/ForeclosureActions';

type Snapshot = { day: string; review_count: number; runs: { id: string; status: string; processing_status: string; records_new: number; records_stacked: number; status_reason: string }[] };
type TraceSnapshot = { total: number; total_budget: { remaining_cents: number; committed_cents: number }; items: { lead_id: string; county: string; address_std: string; stage: string; handoff: { follow_up_task_id: string | null } | null }[] };
type CaptureStatus = { counties: { county: string; documents: number; complete_documents: number; captured_pages: number; expected_pages: number; extracted_pages?: number; extracted_documents?: number; quality_review_pages?: number; updated_at: string | null }[];
  bulk_batches?: { batch_id: string; day: string; evidence_current: boolean; summary: { county: string; documents: number; appraisal_situs_matched: number; property_groups: number; exception_documents: number } }[];
  appraisal_batches?: { batch_id: string; source_as_of: string; summary: { county: string; documents: number; unique_situs_matches: number; exception_documents: number } }[] };
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
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  async function exportDialer() {
    setExporting(true); setExportError('');
    try {
      const response = await apiFetch('/api/operations/lists/dialer-export');
      if (!response.ok) throw new Error('Export unavailable');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = 'wholesaleos-dialer-preparation.zip';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setExportError('Export could not be completed. Refresh the queue and try again.'); }
    finally { setExporting(false); }
  }
  const query = useQuery<Snapshot>({ queryKey: ['daily-lists', actor], refetchInterval: 60000,
    queryFn: async () => (await apiFetch('/api/operations/lists?offset=0')).json() });
  const traces = useQuery<TraceSnapshot>({ queryKey: ['propstream-handoff', actor, offset], refetchInterval: 60000,
    queryFn: async () => (await apiFetch(`/api/operations/lists/propstream?offset=${offset}`)).json() });
  const captures = useQuery<CaptureStatus>({ queryKey: ['foreclosure-captures', actor], refetchInterval: 60000,
    queryFn: async () => (await apiFetch('/api/operations/lists/captures')).json() });
  return <div className="space-y-6">
    <header><h1 className="text-2xl font-bold">Daily lead pipeline</h1>
      <p>Dallas and Collin · Bulk sourcing → verification → skip tracing → outreach preparation</p></header>
    <section aria-label="Automation readiness" className="rounded-xl border border-amber-400 bg-amber-50 p-5 space-y-2">
      <h2 className="text-lg font-semibold">Automation setup in progress</h2>
      <p>GPT schedules bulk processing while your Mac and GPT app are available. Foreclosure collection is limited to once daily and tax files to once weekly per county. The first unattended end-to-end run still needs verification.</p>
      <p>New CRM properties create a notification and a high-priority daily task. Repeat imports do not create duplicate alerts.</p>
      <p>Dated Excel batches are saved in your local WholesaleOS folder. GPT prepares new eligible properties for PropStream and brings completed results back here. DNC and unresolved contact checks stay out of campaign files.</p>
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
    <section aria-label="County document capture" className="rounded-xl border bg-white p-5 space-y-3">
      <h2 className="text-xl font-semibold">County document capture</h2>
      {captures.isPending && <p>Loading saved document receipts…</p>}
      {captures.error && <p role="alert">Document capture status unavailable. <Button onClick={() => captures.refetch()}>Retry document status</Button></p>}
      {captures.data && !captures.error && captures.data.counties.map(county => <div key={county.county}>
        <p><strong>{county.county}</strong> · {county.documents} {county.documents === 1 ? 'notice' : 'notices'} captured · {county.complete_documents} complete {county.complete_documents === 1 ? 'document' : 'documents'} · {county.captured_pages}/{county.expected_pages} pages saved</p>
        {county.extracted_pages !== undefined && <p className="text-sm">Text extracted from {county.extracted_pages} pages across {county.extracted_documents} complete documents · {county.quality_review_pages} pages flagged for text-quality review</p>}
      </div>)}
      <p className="text-sm text-gray-600">Counts cover saved capture receipts. Document capture is followed by content extraction, property matching and current-sale verification; it does not establish county coverage or tracing eligibility.</p>
    </section>
    <section aria-label="Bulk property matching" className="rounded-xl border bg-white p-5 space-y-3">
      <h2 className="text-xl font-semibold">Bulk property matching</h2>
      <p>County notices are processed together and matched to official appraisal data. Repeat property filings share one group; separate liens retain their own evidence.</p>
      {captures.isPending && <p>Loading batch results…</p>}
      {captures.error && <p role="alert">Bulk matching status unavailable.</p>}
      {captures.data && !captures.error && captures.data.appraisal_batches?.map(batch => <article key={batch.batch_id} className="border-t pt-3">
        <p><strong>{batch.summary.county}</strong> · Appraisal data as of {batch.source_as_of} · {batch.summary.documents} index notices processed together</p>
        <p>{batch.summary.unique_situs_matches} addresses matched to one appraisal account · {batch.summary.exception_documents} matching exceptions</p>
        <p className="text-sm text-gray-600">Index discovery only. Complete notice pages and current-sale verification remain required.</p>
      </article>)}
      {captures.data && !captures.error && (!captures.data.bulk_batches?.length
        ? <p>No completed property-matching batch saved yet.</p>
        : captures.data.bulk_batches.map(batch => <article key={batch.batch_id} className="border-t pt-3">
          <p><strong>{batch.summary.county}</strong> · {batch.day} · {batch.summary.documents} notices processed together</p>
          <p>{batch.summary.appraisal_situs_matched} notice addresses matched to fresh appraisal data · {batch.summary.property_groups} property or unresolved-notice groups</p>
          <p>{batch.summary.exception_documents} notices have extraction or matching exceptions.</p>
          {!batch.evidence_current && <p className="text-amber-800">County evidence has changed since this batch. Matching needs to run again.</p>}
        </article>))}
      <p className="text-sm text-gray-600">Batch matching prepares the verification queue. It does not confirm an active foreclosure, authorize tracing, or send outreach.</p>
    </section>
    <ForeclosureActions />
    <section aria-label="Skip tracing and follow-up" className="rounded-xl border bg-white p-5 space-y-3">
      <h2 className="text-xl font-semibold">Skip tracing and follow-up</h2>
      <Button disabled={exporting} onClick={exportDialer}>{exporting ? 'Preparing all properties…' : 'Export dialer and SMS preparation'}</Button>
      <p className="text-sm">One ZIP covers all property pages: contacts for review, Retell SMS message drafts, and excluded records. SMS drafts use your Dallas investor message and show missing identity, consent, and clearance checks. Call and SMS readiness remain on hold until channel checks are recorded. No campaign is started.</p>
      {exportError && <p role="alert">{exportError}</p>}
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
