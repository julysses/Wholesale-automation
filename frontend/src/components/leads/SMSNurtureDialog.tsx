import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import type { Lead } from '@/types';

interface State {
  phone_number: string | null; blockers: string[]; can_enroll: boolean;
  body: string; schedule: string; consent_disclosure: string | null;
  job: { id: string; status: string; due_at: string; reason: string | null } | null;
}
export function SMSNurtureDialog({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [message, setMessage] = useState('');
  const reference = useRef<string | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    const response = await apiFetch(`/api/nurture/lead/${lead.id}`, { signal });
    const next: State = await response.json();
    if (!signal?.aborted) setState(next);
  }, [lead.id]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch(error => {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Readiness could not be verified');
    });
    return () => controller.abort();
  }, [load]);
  const act = async (cancel = false) => {
    setBusy(true); setMessage('');
    try {
      if (cancel && state?.job) {
        await apiFetch(`/api/nurture/${state.job.id}/cancel`, { method: 'POST' });
        setMessage('Scheduled follow-up canceled.');
      } else {
        reference.current ||= crypto.randomUUID();
        await apiFetch(`/api/nurture/lead/${lead.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_id: reference.current, acknowledged }) });
        setMessage('Follow-up saved to the durable schedule. No text has been sent by this action.');
      }
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Operation unconfirmed; refresh before retrying');
      await load().catch(() => setState(null));
    } finally { setBusy(false); }
  };
  const active = state?.job && ['scheduled', 'processing', 'review'].includes(state.job.status);
  return <Modal open onClose={onClose} title="Review SMS nurture" size="lg">
    <div role="dialog" aria-label="Review SMS nurture" aria-modal="true" className="space-y-4 p-5 max-h-[75vh] overflow-y-auto">
      <p className="font-medium">{lead.property_address}</p>
      <p className="text-sm">Phone: {state?.phone_number || 'not verified'}</p>
      <p className="text-sm">{state?.schedule}</p>
      {state?.blockers.length ? <ul className="list-disc pl-5 text-sm text-amber-800">
        {state.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}
      </ul> : null}
      {state?.consent_disclosure && <div className="rounded border p-3 text-sm"><p className="font-medium">Saved SMS consent</p><p>{state.consent_disclosure}</p></div>}
      {state && <div className="rounded border p-3 text-sm"><p className="font-medium">Follow-up text</p><p>{state.body}</p></div>}
      {state?.job && <p className="text-sm">Latest enrollment: {state.job.status}. Due: {new Date(state.job.due_at).toLocaleString()}. {state.job.reason}</p>}
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={acknowledged} disabled={busy || !state?.can_enroll || !!active}
        onChange={event => setAcknowledged(event.target.checked)} />I reviewed this property inquiry's saved SMS consent and approve this follow-up.</label>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || !state?.can_enroll || !acknowledged || !!active} onClick={() => void act()}>Schedule follow-up</Button>
        {state?.job?.status === 'scheduled' && <Button variant="outline" disabled={busy} onClick={() => void act(true)}>Cancel scheduled follow-up</Button>}
        <Button variant="outline" disabled={busy} onClick={() => void load().catch(error => setMessage(error instanceof Error ? error.message : 'Refresh failed'))}>Refresh</Button>
      </div>
      {message && <p role="status" className="text-sm">{message}</p>}
      <p className="text-xs text-gray-500">Uncertain attempts require reconciliation. No automatic resends. A maximum of two SMS attempts per recipient in 30 days includes earlier intake texts.</p>
    </div>
  </Modal>;
}
