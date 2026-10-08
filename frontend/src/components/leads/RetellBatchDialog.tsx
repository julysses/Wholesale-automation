import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';

interface Readiness {
  lead_id: string; property_address: string; phone_number: string | null;
  can_review: boolean; can_call: boolean; blockers: string[];
  consent: { accepted: boolean; disclosure: string | null; submitted_at: string | null };
}
interface Batch {
  id: string; lead_ids: string[]; status: string;
  outcomes: { lead_id: string; request_id: string; phone_number: string; status: string; reason?: string }[];
}
export function RetellBatchDialog({ leadIds, onClose }: { leadIds: string[]; onClose: () => void }) {
  const [rows, setRows] = useState<Readiness[]>([]);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [reviews, setReviews] = useState<Record<string, boolean>>({});
  const [acknowledged, setAcknowledged] = useState(false);
  const [message, setMessage] = useState('');
  const reference = useRef<string | null>(null);
  const selected = useRef(leadIds);
  const mounted = useRef(true);
  const preview = useCallback(async (ids: string[], signal?: AbortSignal) => {
    if (!ids.length) return;
    const response = await apiFetch('/api/calls/retell/batch/preview', { method: 'POST', signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lead_ids: ids }) });
    const state = await response.json();
    if (!signal?.aborted && mounted.current) setRows(state.leads);
  }, []);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await apiFetch('/api/calls/retell/batch/recent', { signal: controller.signal });
        const previous: Batch | null = await response.json();
        if (controller.signal.aborted) return;
        if (previous) {
          setBatch(previous); reference.current = previous.id; selected.current = previous.lead_ids;
          setMessage('Resumed your saved batch. No calls were started by opening this window.');
        }
        await preview(selected.current, controller.signal);
        if (!controller.signal.aborted) setLoaded(true);
      } catch (error) {
        if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Batch readiness unavailable');
      }
    })();
    return () => { mounted.current = false; controller.abort(); };
  }, [preview]);
  const refresh = async () => {
    if (reference.current) {
      const response = await apiFetch(`/api/calls/retell/batch/${reference.current}/reconcile`, { method: 'POST' });
      const next: Batch = await response.json();
      if (mounted.current) setBatch(next);
    }
    if (!reference.current) {
      const response = await apiFetch('/api/calls/retell/batch/recent');
      const previous: Batch | null = await response.json();
      if (previous) {
        reference.current = previous.id; selected.current = previous.lead_ids;
        if (mounted.current) setBatch(previous);
      }
    }
    await preview(selected.current);
    if (mounted.current) { setLoaded(true); setUncertain(false); }
  };
  const approve = async (leadId: string) => {
    setBusy(true); setMessage('');
    try {
      await apiFetch(`/api/calls/retell/lead/${leadId}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ acknowledged: reviews[leadId] === true }) });
      await preview(selected.current);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Lead approval unconfirmed'); }
    finally { setBusy(false); }
  };
  const run = async () => {
    setBusy(true); setMessage('');
    try {
      let current = batch;
      if (!current) {
        reference.current ||= crypto.randomUUID();
        const response = await apiFetch('/api/calls/retell/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_id: reference.current, lead_ids: selected.current, acknowledged }) });
        current = await response.json() as Batch;
        if (mounted.current) setBatch(current);
      }
      // Each HTTP request dispatches at most one call. A timeout or uncertain
      // response stops the loop, while the durable server batch survives reload.
      for (let count = 0; count < 5 && current.status === 'ready' && mounted.current; count++) {
        const response = await apiFetch(`/api/calls/retell/batch/${current.id}/next`, { method: 'POST' });
        current = await response.json() as Batch;
        if (mounted.current) setBatch(current);
      }
      if (mounted.current) setMessage(`Batch: ${current.status}. Provider acceptance does not confirm an answered call.`);
    } catch (error) {
      if (mounted.current) { setUncertain(true); setMessage(error instanceof Error ? error.message : 'Batch outcome unconfirmed; refresh before continuing'); }
      if (reference.current && mounted.current) {
        await apiFetch(`/api/calls/retell/batch/${reference.current}`).then(response => response.json()).then(next => setBatch(next)).catch(() => {});
      }
    } finally { if (mounted.current) setBusy(false); }
  };
  const cancel = async () => {
    if (!batch) return;
    setBusy(true);
    try {
      const response = await apiFetch(`/api/calls/retell/batch/${batch.id}/cancel`, { method: 'POST' });
      setBatch(await response.json()); setMessage('Remaining calls canceled. Already accepted provider calls continue.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Cancellation unconfirmed'); }
    finally { setBusy(false); }
  };
  const eligible = loaded && rows.length > 0 && rows.every(row => row.can_call);
  return <Modal open onClose={onClose} title="Review AI call batch" size="lg">
    <div role="dialog" aria-label="Review AI call batch" aria-modal="true" className="space-y-4 p-5 max-h-[75vh] overflow-y-auto">
      <p className="text-sm">Review up to five selected property inquiries. Every call uses current saved AI-call consent, suppression and contact limits.</p>
      {!loaded && <p className="text-sm">Call controls are unavailable until readiness is verified.</p>}
      {loaded && !rows.length && <p className="text-sm">No saved active batch. Select leads using the checkboxes in the Leads table.</p>}
      {rows.map(row => <div key={row.lead_id} className="rounded border p-3 text-sm space-y-2">
        <p className="font-medium">{row.property_address}</p><p>Phone: {row.phone_number || 'not verified'}</p>
        {!!row.blockers.length && <ul className="list-disc pl-5 text-amber-800">{row.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul>}
        {row.consent.accepted && <><p className="font-medium">Saved AI-call consent</p><p>{row.consent.disclosure}</p><p>Submitted: {row.consent.submitted_at}</p></>}
        {row.can_review && !batch && <><label className="flex items-start gap-2"><input type="checkbox" checked={reviews[row.lead_id] === true} disabled={busy}
          onChange={event => setReviews(current => ({ ...current, [row.lead_id]: event.target.checked }))} />I reviewed this lead's saved AI-call consent.</label>
          <Button size="sm" disabled={busy || !reviews[row.lead_id]} onClick={() => void approve(row.lead_id)}>Approve this lead for calling</Button></>}
      </div>)}
      {batch && <div className="rounded border p-3 text-sm"><p className="font-medium">Saved batch: {batch.status}</p><p>Reference: {batch.id}</p>
        <ul className="mt-2 space-y-2">{batch.outcomes.map(item => <li key={item.request_id}>{item.phone_number}: {item.status}. {item.reason}</li>)}</ul>
      </div>}
      {!batch && <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={acknowledged} disabled={busy || !eligible}
        onChange={event => setAcknowledged(event.target.checked)} />I approve starting calls to this reviewed selection.</label>}
      <div className="flex flex-wrap gap-2">
        {!batch && <Button disabled={busy || uncertain || !eligible || !acknowledged} onClick={() => void run()}>Start reviewed batch</Button>}
        {batch?.status === 'ready' && <><Button disabled={busy || uncertain} onClick={() => void run()}>Continue remaining calls</Button>
          <Button variant="outline" disabled={busy || uncertain} onClick={() => void cancel()}>Cancel remaining calls</Button></>}
        <Button variant="outline" disabled={busy} onClick={() => void refresh().catch(error => setMessage(error instanceof Error ? error.message : 'Refresh failed'))}>Refresh and reconcile</Button>
      </div>
      {message && <p role="status" className="text-sm">{message}</p>}
      <p className="text-xs text-gray-500">Closing this window stops further browser dispatches. Accepted calls continue. Active or uncertain outcomes require reconciliation and are never automatically redialed.</p>
    </div>
  </Modal>;
}
