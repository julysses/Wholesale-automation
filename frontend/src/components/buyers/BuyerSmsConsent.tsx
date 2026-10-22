import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';

type ConsentStatus = { buyer_id: string; phone: string | null; can_review: boolean; consent_ready: boolean;
  suppressed: boolean; receipt_id: string | null; accepted: boolean | null; recorded_at: string | null;
  sending_available: boolean; evidence: Record<string, string> | null };

/** A retained written artifact is reviewed by an administrator; no SMS is sent here. */
export function BuyerSmsConsent({ buyerId }: { buyerId: string }) {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState('');
  const [pending, setPending] = useState(false);
  const [checkingFile, setCheckingFile] = useState(false);
  const fileVersion = useRef(0);
  const [draft, setDraft] = useState({ request_id: '', phone: '', source_type: 'written_web_form', source_url: '', sha256: '',
    consented_at: '', disclosure: '', affirmative_action: '', reviewed_written_evidence: false, accepted: true });
  const status = useQuery({ queryKey: ['buyer_sms_consent', buyerId], retry: false,
    queryFn: async ({ signal }) => {
      const response = await apiFetch(`/api/buyers/${buyerId}/sms-consent`, { signal });
      const data = await response.json();
      if (!response.ok || data.buyer_id !== buyerId || ['can_review', 'consent_ready', 'suppressed', 'sending_available'].some(k => typeof data[k] !== 'boolean')) {
        throw new Error('Buyer consent could not be confirmed.');
      }
      return data as ConsentStatus;
    },
  });
  const data = status.data;
  const begin = () => {
    setDraft({ request_id: crypto.randomUUID(), phone: data?.phone ?? '', source_type: 'written_web_form', source_url: '', sha256: '',
      consented_at: '', disclosure: '', affirmative_action: '', reviewed_written_evidence: false, accepted: true });
    fileVersion.current += 1; setCheckingFile(false);
    setError(''); setSaved(''); setEditing(true);
  };
  const fingerprint = async (file: File | undefined) => {
    const version = ++fileVersion.current;
    setDraft(value => ({ ...value, sha256: '' }));
    if (!file) { setCheckingFile(false); return; }
    if (file.size === 0 || file.size > 10_000_000) { setError('Choose a nonempty retained evidence file up to 10 MB.'); setCheckingFile(false); return; }
    setCheckingFile(true); setError('');
    try {
      const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
      if (version === fileVersion.current) setDraft(value => ({ ...value, sha256: Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') }));
    } catch { if (version === fileVersion.current) setError('Unable to fingerprint the evidence file. Keep the original and retry.'); }
    finally { if (version === fileVersion.current) setCheckingFile(false); }
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (pending || checkingFile || !draft.reviewed_written_evidence) return;
    setPending(true); setError('');
    try {
      const response = await apiFetch(`/api/buyers/${buyerId}/sms-consent`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft) });
      const receipt = await response.json();
      if (!response.ok || receipt.id !== draft.request_id || receipt.buyer_id !== buyerId || receipt.saved !== true || receipt.accepted !== draft.accepted) {
        throw new Error('Consent receipt is unconfirmed.');
      }
      setSaved(`Written consent review saved. Reference: ${receipt.id}. No SMS was sent.`); setEditing(false);
      await status.refetch();
    } catch {
      setError(`Consent receipt is unconfirmed. Retry with this same review reference: ${draft.request_id}. Sending remains unavailable.`);
    } finally { setPending(false); }
  };
  return <section className="rounded-lg border border-gray-200 p-3 space-y-2" aria-label="Buyer SMS consent">
    <h3 className="text-sm font-semibold">Buyer SMS consent</h3>
    <p className="text-xs text-gray-600">Buyer deal alerts need written consent for this buyer’s number. Imported contact details and property inquiry consent do not enroll a buyer.</p>
    {status.isPending && <p>Checking saved consent…</p>}
    {status.isError && <div role="alert">Saved consent is unavailable. <Button size="sm" onClick={() => status.refetch()}>Retry buyer consent</Button></div>}
    {data && <>
      <p className="text-xs">{data.suppressed ? 'Phone is suppressed. This screen cannot clear it.' : data.consent_ready ? 'Written consent review is saved for the current number.' : 'Current number has no accepted written consent review.'}</p>
      <p className="text-xs text-amber-800">SMS sending remains unavailable until the buyer campaign and delivery workflow pass acceptance.</p>
      {data.receipt_id && <details className="text-xs"><summary>Saved consent review</summary>
        <p>Reference: {data.receipt_id}</p><p>Phone: {data.phone}</p><p>Recorded: {data.recorded_at}</p>
        <p className="whitespace-pre-wrap">Disclosure: {data.evidence?.disclosure}</p>
        <p className="whitespace-pre-wrap">Buyer action: {data.evidence?.affirmative_action}</p>
        <p>Evidence reference: {data.evidence?.source_url}</p><p>Evidence SHA-256: {data.evidence?.sha256}</p>
      </details>}
      {!editing && (data.can_review ? <Button size="sm" variant="outline" onClick={begin}>Review written buyer consent</Button> : <p className="text-xs">An approved administrator must review written evidence.</p>)}
    </>}
    {editing && <form onSubmit={save} className="space-y-2 text-xs">
      <p>Keep the original signed document or form receipt. Paste the exact disclosure and affirmative action shown in that evidence. This review records an administrator’s attestation; it does not verify phone ownership or approve a campaign.</p>
      <p>Review reference: {draft.request_id}</p>
      <label className="block">Buyer phone<input required disabled={pending} value={draft.phone} onChange={e => setDraft({ ...draft, phone: e.target.value })} className="block w-full border p-2" /></label>
      <label className="block">Evidence type<select disabled={pending} value={draft.source_type} onChange={e => setDraft({ ...draft, source_type: e.target.value })} className="block w-full border p-2"><option value="written_web_form">Written web form receipt</option><option value="signed_document">Signed document</option></select></label>
      <label className="block">Retained evidence URL<input required type="url" disabled={pending} value={draft.source_url} onChange={e => setDraft({ ...draft, source_url: e.target.value })} className="block w-full border p-2" /></label>
      <label className="block">Select the retained evidence file<input type="file" disabled={pending} onChange={e => void fingerprint(e.target.files?.[0])} className="block w-full border p-2" /></label>
      <p>The file stays on this device. Its fingerprint is saved with your review; keep the original at the evidence URL.</p>
      {checkingFile && <p role="status">Checking the evidence file…</p>}
      <label className="block">Evidence SHA-256<input required pattern="[0-9a-f]{64}" disabled={pending || checkingFile} value={draft.sha256} onChange={e => setDraft({ ...draft, sha256: e.target.value })} className="block w-full border p-2" /></label>
      <label className="block">Consent date and time with time zone<input required placeholder="2026-10-22T14:00:00-05:00" disabled={pending} value={draft.consented_at} onChange={e => setDraft({ ...draft, consented_at: e.target.value })} className="block w-full border p-2" /></label>
      <label className="block">Exact written disclosure<textarea required minLength={40} maxLength={4000} disabled={pending} value={draft.disclosure} onChange={e => setDraft({ ...draft, disclosure: e.target.value })} className="block w-full border p-2" /></label>
      <label className="block">Recorded affirmative buyer action<textarea required minLength={3} maxLength={2000} disabled={pending} value={draft.affirmative_action} onChange={e => setDraft({ ...draft, affirmative_action: e.target.value })} className="block w-full border p-2" /></label>
      <label className="block">Review decision<select disabled={pending} value={String(draft.accepted)} onChange={e => setDraft({ ...draft, accepted: e.target.value === 'true' })} className="block w-full border p-2"><option value="true">Accept written buyer SMS consent</option><option value="false">Record refusal or withdrawn consent</option></select></label>
      <label className="block"><input type="checkbox" required disabled={pending} checked={draft.reviewed_written_evidence} onChange={e => setDraft({ ...draft, reviewed_written_evidence: e.target.checked })} /> I reviewed the retained written evidence for buyer deal-alert SMS, its disclosure, date and this exact number.</label>
      <Button type="submit" size="sm" disabled={pending || checkingFile || !draft.reviewed_written_evidence || (data?.suppressed && draft.accepted)}>Save written consent review</Button>
      <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => setEditing(false)}>Close review</Button>
    </form>}
    {error && <p role="alert">{error}</p>}{saved && <p role="status">{saved}</p>}
  </section>;
}
