import { useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';

export function AppointmentActions({ appointment, onSaved }: { appointment: { id: string; status: string; scheduled_at: string }; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  const transition = async (status: string) => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try {
      await apiFetch(`/api/appointments/${appointment.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_status: appointment.status, status }) });
      onSaved();
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Status unconfirmed. Refresh before continuing.'); }
    finally { pending.current = false; setBusy(false); }
  };
  if (!['scheduled', 'confirmed'].includes(appointment.status)) return null;
  const overdue = new Date(appointment.scheduled_at).getTime() <= Date.now();
  return <div className="space-y-2" aria-label="Appointment actions">
    <div className="flex flex-wrap gap-2">
      {appointment.status === 'scheduled' && <Button size="sm" disabled={busy} onClick={() => transition('confirmed')}>Confirm</Button>}
      <Button size="sm" disabled={busy || !overdue} onClick={() => transition('completed')}>Complete</Button>
      <Button size="sm" disabled={busy || !overdue} onClick={() => transition('no_show')}>No-show</Button>
      <Button size="sm" variant="secondary" disabled={busy} onClick={() => transition('cancelled')}>Cancel appointment</Button>
    </div>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
  </div>;
}
