import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

export type HeldInquiry = { receipt_id: string; state: string; updated_at?: string; reason_code: string | null; blockers: string[] };
type Recovery = { id: string; cycle: number; reason_code: string; review_note: string; evidence_ref: string; created_at: string };
type Request = { id: string; expected_updated_at: string; expected_reason: string; review_note: string; evidence_ref: string };
const reasons = ['CREDENTIALS_INVALID', 'PERMISSION_DENIED', 'RETRY_EXHAUSTED', 'INVALID_PROVIDER_DATA', 'IDENTITY_CONFLICT', 'UNSUPPORTED_EVENT'];
const eligible = (item: HeldInquiry) => item.state === 'review' && !!item.updated_at && Number.isFinite(Date.parse(item.updated_at))
  && reasons.includes(item.reason_code ?? '') && item.blockers.every(code => code === item.reason_code);
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }

export function InquiryRecovery({ userId, workspace, item, healthPath, onSaved, onClose }: {
  userId: string; workspace: string; item: HeldInquiry; healthPath: string; onSaved: () => void; onClose: () => void;
}) {
  const base = `/api/acquisition/workspaces/${workspace}`;
  const path = `${base}/inquiries/${item.receipt_id}/recoveries`;
  const access = useQuery({ queryKey: ['inquiry-recovery-access', userId, workspace], retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => {
      const rows = await read(`${base}/memberships`, signal);
      if (!Array.isArray(rows)) throw new Error('Invalid membership response');
      return rows.some(row => row.user_id === userId && row.workspace_id === workspace && row.status === 'active' && ['owner', 'admin'].includes(row.role));
    } });
  const history = useQuery({ queryKey: ['inquiry-recovery-history', userId, workspace, item.receipt_id], retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }): Promise<Recovery[]> => {
      const rows = await read(path, signal);
      if (!Array.isArray(rows) || rows.length > 3 || !rows.every(row => typeof row.id === 'string' && Number.isInteger(row.cycle)
        && row.cycle >= 1 && row.cycle <= 3 && ['reason_code', 'review_note', 'evidence_ref', 'created_at'].every(key => typeof row[key] === 'string')))
        throw new Error('Invalid recovery history');
      return rows;
    } });
  const [note, setNote] = useState(''); const [evidence, setEvidence] = useState(''); const [ack, setAck] = useState(false);
  const [pending, setPending] = useState<Request | null>(null); const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false); const [feedback, setFeedback] = useState(''); const inFlight = useRef(false);
  const canReview = access.data === true && !access.isFetching && !access.isError && !history.isFetching && !history.isError
    && !!history.data && history.data.length < 3 && eligible(item) && !saved;
  const valid = canReview && note.trim().length >= 20 && note.trim().length <= 2000 && evidence.trim().length > 0 && evidence.trim().length <= 500 && ack;
  async function submit() {
    if (inFlight.current || (!pending && !valid)) return;
    inFlight.current = true; setBusy(true); setFeedback(''); let request = pending;
    try {
      if (!request) {
        const health = await read(healthPath);
        const fresh = Array.isArray(health?.items) ? health.items.find((row: HeldInquiry) => row.receipt_id === item.receipt_id) : null;
        if (!fresh || !Array.isArray(fresh.blockers) || !eligible(fresh) || fresh.updated_at !== item.updated_at || fresh.reason_code !== item.reason_code)
          throw new Error('The inquiry changed or recovery is blocked. Close this review and refresh inquiry health.');
        request = { id: crypto.randomUUID(), expected_updated_at: item.updated_at!, expected_reason: item.reason_code!, review_note: note.trim(), evidence_ref: evidence.trim() };
        setPending(request);
      }
      const result = await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
      if (result?.recovery_id !== request.id || result.receipt_id !== item.receipt_id || !Number.isInteger(result.cycle)
        || result.cycle < 1 || result.cycle > 3 || typeof result.duplicate !== 'boolean' || result.outreach_authorized !== false)
        throw new Error('Unconfirmed result');
      setPending(null); setSaved(true); setFeedback('Recovery approval recorded. Processing remains subject to current gates; no seller contact was authorized.');
      void history.refetch(); onSaved();
    } catch (error) {
      const definite = error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (definite) { setPending(null); void history.refetch(); void access.refetch(); }
      setFeedback(request && !definite ? 'The result is unconfirmed. Retry the exact request to reconcile approval. Keep this review open until resolved.'
        : request ? 'Recovery was rejected. Check MFA, workspace access and the current inquiry state before reviewing again.'
        : 'The inquiry changed or could not be checked. Close this review and refresh inquiry health.');
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Inquiry recovery review" className="rounded-lg border p-4 space-y-3">
    <h3 className="font-semibold">Review held inquiry</h3>
    <p className="text-sm break-all">Inquiry {item.receipt_id}</p>
    <p className="text-sm">Hold: {item.reason_code?.replaceAll('_', ' ')}. State recorded: {item.updated_at ?? 'Unavailable'}.</p>
    <p className="text-sm">An owner or administrator must complete MFA and document the correction. Approval permits another bounded processing cycle, with a maximum of three reviewed recoveries.</p>
    <h4 className="font-medium">Recovery history</h4>
    {history.isFetching ? <p>Loading recovery history…</p> : history.isError ? <p role="alert">Recovery history unavailable.</p>
      : history.data?.length ? <ol className="space-y-2">{history.data.map(row => <li key={row.id} className="text-sm break-words">Cycle {row.cycle} · {row.created_at}<p>{row.review_note}</p><p>Evidence: {row.evidence_ref}</p></li>)}</ol> : <p className="text-sm">No recovery approvals recorded.</p>}
    {!canReview && !pending && !saved && <p className="text-sm">Approval unavailable: verify owner/admin access, review history and current recovery gates.</p>}
    <fieldset disabled={!canReview || busy || !!pending} className="space-y-3">
      <label className="block text-sm">Correction and review note<textarea className="block border rounded w-full p-2" value={note} minLength={20} maxLength={2000} onChange={event => setNote(event.target.value)} /></label>
      <label className="block text-sm">Evidence reference<input className="block border rounded w-full p-2" value={evidence} maxLength={500} onChange={event => setEvidence(event.target.value)} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />I reviewed this specific hold and its correction and approve one additional processing cycle.</label>
    </fieldset>
    {feedback && <p role="status" className="text-sm">{feedback}</p>}
    <div className="flex flex-wrap gap-2"><button className={button} disabled={busy || (!pending && !valid)} onClick={() => { void submit(); }}>{busy ? 'Checking recovery…' : pending ? 'Retry exact recovery request' : 'Approve recovery cycle'}</button>
      <button className={button} disabled={busy || !!pending} onClick={onClose}>Close recovery review</button></div>
  </section>;
}
