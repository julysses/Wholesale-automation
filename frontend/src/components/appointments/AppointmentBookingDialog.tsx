import { useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';

export function AppointmentBookingDialog({ leadId, address, onClose, onSaved }: {
  leadId: string; address: string; onClose: () => void; onSaved: () => void;
}) {
  const [date, setDate] = useState('');
  const [time, setTime] = useState('');
  const [type, setType] = useState('phone');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState('');
  const pending = useRef(false);
  const reference = useRef<string | null>(null);
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const submit = async () => {
    if (pending.current || saved) return;
    const scheduled = new Date(`${date}T${time}`);
    if (!date || !time || Number.isNaN(scheduled.getTime()) || (!uncertain && scheduled.getTime() <= Date.now())) {
      setMessage('Choose a future date and time.'); return;
    }
    pending.current = true; setBusy(true); setMessage('');
    reference.current ||= crypto.randomUUID();
    try {
      const response = await apiFetch('/api/appointments', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: reference.current, lead_id: leadId, scheduled_at: scheduled.toISOString(), appointment_type: type, notes }) });
      const booking = await response.json();
      if (!booking.id) throw new Error('Booking acknowledgement missing');
      setSaved(true); setUncertain(false);
      setMessage(`Appointment saved. ${booking.calendar_sync === 'synced' ? 'Calendar synced.' : 'External calendar sync is unavailable. Add this booking to your calendar manually.'}`);
      onSaved();
    } catch (error) {
      setUncertain(true);
      setMessage(`${error instanceof Error ? error.message : 'Booking outcome unconfirmed'} Retry unchanged details to recover this booking. Closing does not cancel a saved appointment.`);
    } finally { pending.current = false; setBusy(false); }
  };
  const locked = busy || uncertain || saved;
  return <Modal open title="Schedule appointment" onClose={() => { if (!pending.current) onClose(); }}>
    <div className="space-y-4 p-6" role="dialog" aria-label="Schedule appointment">
      <p>{address}</p>
      <p className="text-sm text-gray-600">Date and time use {zone}. Book only a time agreed with the seller.</p>
      <label className="block">Date<input aria-label="Appointment date" type="date" value={date} disabled={locked} onChange={event => setDate(event.target.value)} className="block w-full rounded border p-2" /></label>
      <label className="block">Time<input aria-label="Appointment time" type="time" value={time} disabled={locked} onChange={event => setTime(event.target.value)} className="block w-full rounded border p-2" /></label>
      <label className="block">Type<select aria-label="Appointment type" value={type} disabled={locked} onChange={event => setType(event.target.value)} className="block w-full rounded border p-2">
        <option value="phone">Phone call</option><option value="video">Video walkthrough</option><option value="in_person">In-person inspection</option>
      </select></label>
      <label className="block">Notes<textarea aria-label="Appointment notes" maxLength={4000} value={notes} disabled={locked} onChange={event => setNotes(event.target.value)} className="block w-full rounded border p-2" /></label>
      {message && <p role="status">{message}</p>}
      {!saved && <Button disabled={busy || !date || !time} onClick={submit}>{busy ? 'Saving…' : uncertain ? 'Retry same booking' : 'Save appointment'}</Button>}
      <Button variant="secondary" disabled={busy} onClick={onClose}>{saved ? 'Done' : 'Close'}</Button>
    </div>
  </Modal>;
}
