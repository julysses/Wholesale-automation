import { useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import type { BuyerProgram } from '@/pages/BuyerEnrollment';

type Submission = { id: string; accepted: boolean; phone: string; created_at: string; evidence: { program: BuyerProgram; affirmative_action: string }; evidence_sha256: string; reviewed: boolean };
export function BuyerEnrollmentAdmin({ buyerId, onReviewed }: { buyerId: string; onReviewed: () => void }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [config, setConfig] = useState<{ available: boolean; program: BuyerProgram | null } | null>(null);
  const [history, setHistory] = useState<{ total: number; offset: number; submissions: Submission[] } | null>(null);
  const [cap, setCap] = useState<{ request_id: string; token: string } | null>(null), [link, setLink] = useState('');
  const [reviewed, setReviewed] = useState<Record<string, boolean>>({});
  const load = async (offset = 0) => {
    setBusy(true); setError('');
    try {
      const [programResponse, historyResponse] = await Promise.all([apiFetch('/api/buyers/enrollment-program'), apiFetch(`/api/buyers/${buyerId}/enrollment-submissions?offset=${offset}`)]);
      const [program, rows] = await Promise.all([programResponse.json(), historyResponse.json()]);
      if (!programResponse.ok || typeof program.available !== 'boolean' || !historyResponse.ok || rows.buyer_id !== buyerId || rows.offset !== offset || !Number.isInteger(rows.total) || !Array.isArray(rows.submissions)) throw new Error();
      setConfig(program); setHistory(rows); setOpen(true);
    } catch { setError('Enrollment details could not be confirmed. Previously shown records remain unchanged.'); }
    finally { setBusy(false); }
  };
  const create = async () => {
    if (!config?.available || !config.program || busy) return;
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    const value = cap ?? { request_id: crypto.randomUUID(), token: btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') };
    setCap(value); setBusy(true); setError('');
    try {
      const response = await apiFetch(`/api/buyers/${buyerId}/enrollment-invite`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
      const receipt = await response.json();
      if (!response.ok || receipt.id !== value.request_id || receipt.buyer_id !== buyerId || receipt.saved !== true) throw new Error();
      setLink(`${config.program.origin}/buyer-sms#reference=${value.request_id}&token=${value.token}`);
    } catch { setError('Invitation receipt is unconfirmed. Retry with the same retained reference. No invitation was sent.'); }
    finally { setBusy(false); }
  };
  const review = async (row: Submission) => {
    if (!reviewed[row.id] || busy) return; setBusy(true); setError('');
    try {
      const response = await apiFetch(`/api/buyers/${buyerId}/enrollment-submissions/${row.id}/review`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok || result.id !== row.id || result.buyer_id !== buyerId || result.saved !== true) throw new Error();
      onReviewed(); await load(history?.offset ?? 0);
    } catch { setError('Review receipt is unconfirmed or the buyer choice changed. Refresh evidence before retrying.'); }
    finally { setBusy(false); }
  };
  return <section className="space-y-3 border-t pt-3" aria-label="Buyer enrollment administration">
    <Button size="sm" variant="outline" disabled={busy} onClick={() => load()}>Prepare buyer enrollment</Button>
    {error && <p role="alert">{error}</p>}
    {open && <>
      <p className="text-xs">Private links require a request from the buyer. Creating or reviewing a link sends no SMS or email. Links expire after seven days and accept one immutable choice.</p>
      {config?.program && <details className="text-xs"><summary>Program text for owner review</summary><p>{config.program.disclosure}</p><p>{config.program.terms}</p><p>{config.program.privacy}</p><p>Version: {config.program.version}</p></details>}
      {!config?.available && <p>Enrollment is disabled until the exact program version and public details are approved.</p>}
      <Button size="sm" disabled={busy || !config?.available || !!link} onClick={create}>{cap && !link ? 'Retry same enrollment invitation' : 'Create private enrollment link'}</Button>
      {link && <><label className="block text-xs">Private buyer enrollment link<input readOnly value={link} className="block w-full border p-2" /></label><p className="text-xs">No invitation was sent. Share this private link only with the intended buyer after they request enrollment.</p></>}
      {history && <><p className="text-xs">{history.total} saved submissions · showing {history.submissions.length ? history.offset + 1 : 0}–{history.offset + history.submissions.length}</p>
        {history.submissions.map(row => <article key={row.id} className="rounded border p-3 text-xs space-y-2"><p>{row.accepted ? 'Requested buyer SMS' : 'Kept buyer SMS off'} · {row.phone}</p><p>Submitted: {row.created_at}</p>
          <details><summary>Retained submission evidence</summary><p>{row.evidence.program.disclosure}</p><p>{row.evidence.affirmative_action}</p><p>Evidence fingerprint: {row.evidence_sha256}</p><pre className="whitespace-pre-wrap">{JSON.stringify(row.evidence, null, 2)}</pre></details>
          {row.reviewed ? <p>Review receipt already saved.</p> : <><label><input type="checkbox" checked={!!reviewed[row.id]} disabled={busy} onChange={e => setReviewed({ ...reviewed, [row.id]: e.target.checked })} /> I reviewed this exact submission, program disclosure and buyer number.</label><Button size="sm" disabled={busy || !reviewed[row.id]} onClick={() => review(row)}>Save reviewed submission</Button></>}
        </article>)}
        <Button size="sm" variant="outline" disabled={busy || history.offset === 0} onClick={() => load(Math.max(0, history.offset - 20))}>Newer submissions</Button>
        <Button size="sm" variant="outline" disabled={busy || history.offset + history.submissions.length >= history.total} onClick={() => load(history.offset + 20)}>Older submissions</Button>
      </>}
    </>}
  </section>;
}
