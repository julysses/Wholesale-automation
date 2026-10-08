import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import type { Lead } from '@/types';

interface Attempt {
  request_id: string;
  call_id: string | null;
  status: string;
}
interface Readiness {
  phone_number: string | null;
  ai_calling_paused: boolean;
  can_review: boolean;
  can_call: boolean;
  blockers: string[];
  attempt: Attempt | null;
  consent: { accepted: boolean; disclosure: string | null; submitted_at: string | null };
}

export function RetellCallDialog({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const [state, setState] = useState<Readiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [message, setMessage] = useState('');
  const reference = useRef<string | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    const response = await apiFetch(`/api/calls/retell/lead/${encodeURIComponent(lead.id)}`, { signal });
    const next: Readiness = await response.json();
    if (!signal?.aborted) setState(next);
    return next;
  }, [lead.id]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch(error => {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Unable to verify call readiness');
    });
    return () => controller.abort();
  }, [load]);
  const act = async (kind: 'review' | 'call' | 'refresh') => {
    setBusy(true); setMessage('');
    try {
      if (kind === 'review') {
        await apiFetch(`/api/calls/retell/lead/${encodeURIComponent(lead.id)}/review`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acknowledged }),
        });
        setMessage('Lead review saved. Starting a call requires a separate action.');
      } else if (kind === 'call') {
        if (!state?.can_call || !state.phone_number) throw new Error('Current readiness blocks this call');
        if (!reference.current || reference.current === state.attempt?.request_id && state.attempt.status === 'completed') {
          reference.current = crypto.randomUUID();
        }
        const response = await apiFetch('/api/calls/retell', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_id: reference.current, lead_id: lead.id, phone_number: state.phone_number }),
        });
        const result = await response.json();
        setMessage(`Call request recorded: ${result.status}. Provider acceptance does not confirm an answered call.`);
      } else if (state?.attempt?.call_id) {
        const response = await apiFetch(`/api/calls/retell/${encodeURIComponent(state.attempt.call_id)}`);
        const result = await response.json();
        setMessage(`Provider call status: ${result.call_status}`);
      }
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Call operation could not be confirmed');
      // Read the durable ledger after an uncertain response; never generate a replacement attempt automatically.
      await load().catch(() => setState(null));
    } finally { setBusy(false); }
  };
  return <Modal open onClose={onClose} title="Review AI call" size="lg">
    <div role="dialog" aria-label="Review AI call" aria-modal="true" className="space-y-4 p-5 max-h-[75vh] overflow-y-auto">
      <p className="font-medium">{lead.property_address}</p>
      <p className="text-sm">Phone: {state?.phone_number || 'not verified'}</p>
      {!state && <p className="text-sm">Call controls remain unavailable until readiness is verified.</p>}
      {state?.blockers.length ? <ul className="list-disc pl-5 text-sm text-amber-800">
        {state.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}
      </ul> : null}
      {state?.consent.accepted && <div className="rounded border p-3 text-sm">
        <p className="font-medium">Saved AI-call consent</p>
        <p>{state.consent.disclosure}</p>
        <p className="mt-2 text-gray-500">Submitted: {state.consent.submitted_at}</p>
      </div>}
      {state?.can_review && <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} disabled={busy} />
        I reviewed the saved AI-call consent and approve this lead for calling.
      </label>}
      {state?.attempt && <p className="text-sm">Latest attempt: {state.attempt.status}. Reference: {state.attempt.request_id}.
        {!state.attempt.call_id && ' The provider outcome needs reconciliation before another call.'}
      </p>}
      <div className="flex flex-wrap gap-2">
        {state?.ai_calling_paused && <Button disabled={busy || !state.can_review || !acknowledged} onClick={() => void act('review')}>Approve lead for AI call</Button>}
        <Button disabled={busy || !state?.can_call} onClick={() => void act('call')}>{state?.attempt?.status === 'completed' ? 'Start new AI call' : 'Start AI call'}</Button>
        <Button variant="outline" disabled={busy} onClick={() => void act('refresh')}>Refresh call readiness</Button>
      </div>
      {message && <p role="status" className="text-sm">{message}</p>}
      <p className="text-xs text-gray-500">Active or uncertain attempts require reconciliation. Closing this window does not cancel a provider call.</p>
    </div>
  </Modal>;
}
