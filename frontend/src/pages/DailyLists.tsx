import { PropstreamBulk } from '@/components/lists/PropstreamBulk';
import { PropstreamHandoff } from '@/components/lists/PropstreamHandoff';
import { ReviewControl, type Review } from '@/components/lists/ReviewControl';
import { ForeclosureActions } from '@/components/lists/ForeclosureActions';
import { LotOperations } from '@/components/lists/LotOperations';
import { ScoringOperations } from '@/components/lists/ScoringOperations';
import { TraceOperations } from '@/components/lists/TraceOperations';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useProfile } from '@/hooks/useProfile';

type Source = { source_key: string; county: string; jurisdiction: string; list_type: string; enabled: boolean; lookback_days: number; procedure_version: string | null; schedule_cron: string };
type Run = { id: string; source_id: string; status: string; processing_status: string; records_new: number; records_stacked: number; status_reason: string };
type Snapshot = { day: string; sources: Source[]; runs: Run[]; reviews: Review[]; review_count: number; digest: { status: string; generated_at: string } | null };
async function action(path: string, method: string, body?: unknown) {
  const response = await apiFetch(path, { method, headers: { 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  return response.json();
}
function SourceControl({ source, refresh }: { source: Source; refresh: () => Promise<unknown> }) {
  const [lookback, setLookback] = useState(String(source.lookback_days));
  const [version, setVersion] = useState(source.procedure_version ?? '');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function save(enabled: boolean) {
    setPending(true); setError('');
    try {
      await action(`/api/operations/lists/sources/${source.source_key}`, 'PATCH', { enabled, lookback_days: Number(lookback), procedure_version: version || null });
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Save unconfirmed. Refresh before retrying.'); }
    finally { setPending(false); }
  }
  return <article className="rounded-xl border bg-white p-4 space-y-3">
    <h2 className="font-semibold">{source.county} · {source.jurisdiction} · {source.list_type.replaceAll('_', ' ')}</h2>
    <p className="text-sm">Delivery {source.enabled ? 'enabled' : 'disabled'} · Central time · {source.schedule_cron}</p>
    <Input label="Lookback days" type="number" min="1" max={source.list_type === 'pre_foreclosure' ? '30' : '365'} value={lookback} onChange={e => setLookback(e.target.value)} />
    <Input label="Reviewed procedure version" value={version} onChange={e => setVersion(e.target.value)} />
    <p className="text-xs text-gray-600">Enabling accepts deliveries and monitors deadlines. The collector schedule and delivery credentials must also be configured.</p>
    <div className="flex gap-2"><Button disabled={pending} onClick={() => save(true)}>Save and enable delivery</Button><Button disabled={pending} onClick={() => save(false)}>Disable delivery</Button></div>
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </article>;
}
export function DailyLists() {
  const { isAdmin } = useProfile();
  const [offset, setOffset] = useState(0);
  const [message, setMessage] = useState('');
  const [scanning, setScanning] = useState(false);
  const client = useQueryClient();
  const query = useQuery<Snapshot>({ queryKey: ['daily-lists', offset], enabled: isAdmin,
    queryFn: () => action(`/api/operations/lists?offset=${offset}`, 'GET') });
  const refresh = () => client.invalidateQueries({ queryKey: ['daily-lists'] });
  if (!isAdmin) return <p>Administrator access required.</p>;
  async function scan() {
    setScanning(true); setMessage('');
    try { await action('/api/operations/lists/scan', 'POST'); await refresh(); setMessage('Status and digest refreshed. No seller outreach sent.'); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Scan unavailable'); }
    finally { setScanning(false); }
  }
  return <div className="space-y-5">
    <h1 className="text-2xl font-bold">Daily county lists</h1>
    <p>Dallas and Collin only. Code enforcement covers the named municipality, not the entire county. Reviewed records feed the CRM; contact permissions remain separate.</p>
    <ForeclosureActions />
    <PropstreamBulk /><PropstreamHandoff />
    <TraceOperations />
    <ScoringOperations />
    <LotOperations />
    <Button onClick={scan} disabled={scanning}>Refresh processing and heartbeat</Button>
    {message && <p role="status">{message}</p>}
    {query.isLoading && <p>Loading list status…</p>}
    {query.error && <p role="alert">{query.error.message}</p>}
    {query.data && <>
      <p>{query.data.day} · {query.data.review_count} records awaiting evidence · Digest: {query.data.digest?.status ?? 'not generated'}</p>
      <div className="grid gap-4 md:grid-cols-2">{query.data.sources.map(source => <SourceControl key={source.source_key} source={source} refresh={refresh} />)}</div>
      <h2 className="text-xl font-semibold">Run receipts</h2>
      {query.data.runs.length === 0 ? <p>No deliveries received for this date. This does not mean zero source records.</p> : query.data.runs.map(run => <article className="rounded border p-3" key={run.id}>
        <p>{run.id} · {run.status} · {run.processing_status}</p><p>{run.records_new} new leads · {run.records_stacked} stacked observations</p><p>{run.status_reason}</p>
      </article>)}
      <h2 className="text-xl font-semibold">Property evidence review</h2>
      {query.data.reviews.map(item => <ReviewControl key={`${item.run_id}:${item.batch_index}:${item.ordinal}`} item={item} refresh={refresh} />)}
      <div className="flex gap-3"><Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous 100</Button><Button disabled={offset + 100 >= query.data.review_count} onClick={() => setOffset(offset + 100)}>Next 100</Button><Button disabled={offset + 100 >= query.data.review_count} onClick={() => setOffset(Math.floor(Math.max(0, query.data!.review_count - 1) / 100) * 100)}>Last page</Button></div>
    </>}
  </div>;
}
