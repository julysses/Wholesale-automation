import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
interface State {
  snapshot: { database: boolean; intake: boolean; owner: boolean; aged: Record<string, number>; open_incidents: number };
  incidents: { id: string; category: string; reference: string; first_seen: string }[];
}
export function LaunchMonitorPanel() {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const response = await apiFetch('/api/operations/monitor', { signal });
    const value = await response.json();
    if (!signal?.aborted) setState(value);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal).catch(error => { if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : 'Monitor unavailable'); });
    return () => controller.abort();
  }, [refresh]);
  const run = async (scan = false) => {
    if (busy) return;
    setBusy(true); setMessage('');
    try {
      if (scan) {
        const response = await apiFetch('/api/operations/monitor/scan', { method: 'POST' });
        const result = await response.json();
        setMessage(result.busy ? 'Another scan is running. Refresh for its result.' : `${result.created} new escalations saved. No seller outreach was replayed.`);
      }
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Monitor outcome unconfirmed. Refresh before continuing.'); }
    finally { setBusy(false); }
  };
  return <section aria-label="Launch monitoring" className="space-y-3 rounded-lg border p-4">
    <h3 className="font-medium">Launch monitoring</h3>
    <p className="text-sm">Stalled work creates an assigned task and an in-app alert. Scans run through Supabase Cron; GitHub Actions checks availability independently. A green availability check does not prove provider delivery or final launch readiness.</p>
    {state && <>
      <p>Database: {state.snapshot.database ? 'available' : 'unavailable'} · Intake forms: {state.snapshot.intake ? 'available' : 'unavailable'} · Intake owner: {state.snapshot.owner ? 'approved' : 'unavailable'}</p>
      <p>Open monitor incidents: {state.snapshot.open_incidents}</p>
      {Object.entries(state.snapshot.aged).map(([category, count]) => <p key={category}>{category}: {count} aged outcomes need review</p>)}
      {state.incidents.map(incident => <p key={incident.id} className="text-sm">{incident.category} · {incident.reference} · {new Date(incident.first_seen).toLocaleString()}</p>)}
      <a href="/tasks" className="text-blue-700 underline">Review assigned tasks</a>
    </>}
    <div className="flex gap-2"><Button variant="outline" disabled={busy} onClick={() => { void run(); }}>Refresh monitoring</Button>
      <Button disabled={busy} onClick={() => { void run(true); }}>Scan stalled work</Button></div>
    {message && <p role="status">{message}</p>}
  </section>;
}
