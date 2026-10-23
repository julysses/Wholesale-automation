import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import { queryAllConfirmed } from '@/lib/queryAll';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';

interface OutreachRow {
  id: string;
  buyer_id: string | null;
  buyer_snapshot?: { id?: string; first_name?: string | null; last_name?: string | null };
  request_id?: string | null;
  outcome_reason?: string | null;
  created_at: string;
  channel: string;
  direction?: string | null;
  status: string;
  body: string;
  subject?: string | null;
  to_address: string;
  provider?: string | null;
  provider_msg_id?: string | null;
  provider_submission_id?: string | null;
  replied_at?: string | null;
  buyers?: { first_name: string; last_name: string } | null;
}

export function BuyerOutreachHistory() {
  const [search, setSearch] = useState('');
  const [channel, setChannel] = useState('');
  const [page, setPage] = useState(1);
  const [reconciling, setReconciling] = useState<string | null>(null);
  const [reconcileMessage, setReconcileMessage] = useState('');
  const [reconcileError, setReconcileError] = useState('');
  const history = useQuery({
    queryKey: ['buyer_outreach_log', 'all-pages'],
    queryFn: () => queryAllConfirmed<OutreachRow>((from, to) => supabase.from('buyer_outreach_log')
      .select('*, buyers(first_name, last_name)', { count: 'exact' })
      .order('created_at', { ascending: false }).order('id', { ascending: true }).range(from, to), 'Buyer outreach history'),
    retry: false,
    staleTime: 0,
  });
  const reconcile = async (reference: string) => {
    if (reconciling) return;
    setReconciling(reference); setReconcileMessage(''); setReconcileError('');
    try {
      const response = await apiFetch(`/api/buyers/outreach/${reference}/reconcile`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok || result.request_id !== reference || !Number.isInteger(result.checked)
        || result.checked < 1 || result.provider_calls !== 0) throw new Error('Stored outreach results could not be confirmed for this reference.');
      setReconcileMessage(`${result.checked} stored attempts checked. No messages were sent. Review any remaining held or unknown records.`);
      await history.refetch();
    } catch (error) {
      setReconcileError(error instanceof Error ? error.message : 'Reconciliation unavailable. Refresh saved history.');
    } finally { setReconciling(null); }
  };
  const saved = history.data;
  const query = search.trim().toLowerCase();
  const filtered = (saved ?? []).filter(row => (!channel || row.channel === channel)
    && (!query || [row.buyers?.first_name, row.buyers?.last_name,
      `${row.buyers?.first_name ?? ''} ${row.buyers?.last_name ?? ''}`, row.buyer_id,
      row.to_address, row.subject, row.body, row.status, row.provider, row.provider_msg_id, row.provider_submission_id,
      row.buyer_snapshot?.first_name, row.buyer_snapshot?.last_name, row.buyer_snapshot?.id, row.request_id, row.outcome_reason]
      .some(value => String(value ?? '').toLowerCase().includes(query))));
  const currentPage = Math.min(page, Math.max(1, Math.ceil(filtered.length / 25)));
  const visible = filtered.slice((currentPage - 1) * 25, currentPage * 25);

  return <section aria-label="Buyer outreach history" className="space-y-3">
    <div className="flex justify-between items-start gap-3">
      <div>
        <h2 className="text-base font-semibold">Saved outreach records</h2>
        <p className="text-sm text-gray-500">{saved ? `${saved.length.toLocaleString()} saved activity records`
          : history.isPending ? 'Loading outreach history…' : 'Outreach totals unavailable'}</p>
        <p className="text-xs text-gray-500">Delivery confirmation requires a recorded delivery receipt. Missing send logs require provider review.</p>
      </div>
      <Button variant="outline" disabled={history.isFetching} onClick={() => void history.refetch()}>Refresh outreach history</Button>
    </div>
    {history.isError && <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-2">
      <p>Unable to load outreach history: {history.error.message}. {saved && 'Showing last confirmed saved records.'}</p>
      <Button variant="outline" disabled={history.isFetching} onClick={() => void history.refetch()}>Retry outreach history</Button>
    </div>}
    {reconcileMessage && <p role="status" className="text-sm text-gray-600">{reconcileMessage}</p>}
    {reconcileError && <p role="alert" className="text-sm text-amber-700">{reconcileError}</p>}
    <div className="flex flex-wrap gap-3">
      <input aria-label="Search outreach history" placeholder="Search buyer, destination, message or receipt"
        className="border rounded-lg px-3 py-2 text-sm flex-1" value={search}
        onChange={event => { setSearch(event.target.value); setPage(1); }} />
      <select aria-label="Outreach history channel" value={channel} className="border rounded-lg px-3 py-2 text-sm"
        onChange={event => { setChannel(event.target.value); setPage(1); }}>
        <option value="">All channels</option><option value="sms">SMS</option><option value="email">Email</option>
      </select>
    </div>
    <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="border-b bg-gray-50">
          {['Buyer', 'Destination', 'Channel', 'Direction', 'Recorded status', 'Message', 'Recorded', 'Reply', 'Provider receipt'].map(label =>
            <th key={label} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 whitespace-nowrap">{label}</th>)}
        </tr></thead>
        <tbody className="divide-y divide-gray-100">
          {!saved ? <tr><td colSpan={9} className="p-8 text-center text-gray-500">
            {history.isPending ? 'Loading saved outreach records…' : 'Saved outreach history unavailable.'}
          </td></tr> : filtered.length === 0 ? <tr><td colSpan={9} className="p-8 text-center text-gray-500">
            {saved.length === 0 ? 'No saved outreach records' : 'No saved records match these filters'}
          </td></tr> : visible.map(row => <tr key={row.id}>
            <td className="px-4 py-3">{row.buyer_snapshot?.first_name ? `${row.buyer_snapshot.first_name} ${row.buyer_snapshot.last_name ?? ''}` : row.buyers ? `${row.buyers.first_name} ${row.buyers.last_name}` : 'Buyer name unavailable'}
              <span className="block text-xs text-gray-400">{row.buyer_snapshot?.id || row.buyer_id}</span></td>
            <td className="px-4 py-3 whitespace-nowrap">{row.to_address || '—'}</td>
            <td className="px-4 py-3 uppercase text-xs">{row.channel}</td>
            <td className="px-4 py-3 text-xs">{row.direction || 'Unknown'}</td>
            <td className="px-4 py-3 text-xs">{row.status || 'Unknown'}<span className="block text-gray-500">{row.outcome_reason}</span></td>
            <td className="px-4 py-3 min-w-48 max-w-80">
              {row.subject && <p className="font-medium">{row.subject}</p>}
              <p className="truncate text-xs">{row.body}</p>
              <details><summary className="text-xs cursor-pointer">View recorded message</summary>
                <p className="whitespace-pre-wrap break-words text-xs mt-2">{row.body}</p></details>
            </td>
            <td className="px-4 py-3 text-xs whitespace-nowrap"><time dateTime={row.created_at} title={row.created_at}>{formatDate(row.created_at)}</time></td>
            <td className="px-4 py-3 text-xs">{row.replied_at
              ? <time dateTime={row.replied_at} title={row.replied_at}>Reply recorded · {formatDate(row.replied_at)}</time> : '—'}</td>
            <td className="px-4 py-3 text-xs break-all">{row.provider || 'Unknown provider'}<span className="block">{row.provider_msg_id || 'No event reference recorded'}</span>{row.provider_submission_id && <span className="block">Submission: {row.provider_submission_id}</span>}{row.request_id && <span className="block text-gray-400">Request: {row.request_id}</span>}
              {row.request_id && ['submitting', 'unknown'].includes(row.status) && <Button variant="outline" disabled={reconciling !== null}
                onClick={() => { if (row.request_id) void reconcile(row.request_id); }}>Reconcile saved request</Button>}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
    {saved && <nav aria-label="Outreach history pages" className="flex flex-wrap justify-between items-center gap-2 text-sm">
      <span>{filtered.length ? (currentPage - 1) * 25 + 1 : 0}–{Math.min(currentPage * 25, filtered.length)} of {filtered.length.toLocaleString()} saved records</span>
      <div className="flex gap-2">
        <Button variant="outline" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous outreach page</Button>
        <Button variant="outline" disabled={currentPage * 25 >= filtered.length} onClick={() => setPage(currentPage + 1)}>Next outreach page</Button>
      </div>
    </nav>}
  </section>;
}
