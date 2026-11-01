import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import type { DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseSignatureCandidate, readPendingSignature, preserveSignature, pendingSignatureSchema,
  clearConfirmedSignature, clearRejectedSignature, type PendingSignature } from '@/lib/acquisition/signature-review';

const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full rounded-lg border border-gray-300 bg-white p-2';
const holds = { paused: 'Acquisition review is paused.', contract_unavailable: 'Refresh the current contract version.',
  history_limit_reached: 'This review history needs administrator attention.', contract_review_required: 'Complete a current purchase-contract review with sourced price and earnest-money terms above.',
  reviewer_policy_required: 'A reviewed policy must authorize you to record this signature-release review.',
  ready_for_human_review: 'Contract and reviewer checks passed. Complete your own review before recording a decision.' };
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function SignatureReviewForm(props: Props) {
  return <SignatureEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function SignatureEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingSignature(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Signature context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingSignature | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false);
  const [note, setNote] = useState(''), [reviewed, setReviewed] = useState(false), [minutes, setMinutes] = useState(5);
  const [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient();
  const held = expanded || busy || !!pending || blocked;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}/signature-review`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!expanded && !pending) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [expanded, pending]);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const candidate = useQuery({ queryKey: ['signature-review-choice', context.userId, context.workspaceId, context.contractId, context.contractVersion],
    enabled: expanded && !disabled && !pending && !blocked, retry: false, gcTime: 0, staleTime: 0,
    refetchOnWindowFocus: false, refetchOnReconnect: false,
    queryFn: async ({ signal }) => parseSignatureCandidate(await (await apiFetch(`${base}/candidate`, { signal, cache: 'no-store' })).json(), context) });
  const fresh = !disabled && !blocked && !candidate.isError && !candidate.isFetching && candidate.data
    && now - Date.parse(candidate.data.checked_at) <= 30000 && now - Date.parse(candidate.data.checked_at) >= -5000;
  const choice = fresh ? candidate.data!.candidate : null, withdrawal = fresh ? candidate.data!.withdrawal : null;
  const deadline = choice ? Math.min(Date.parse(choice.max_expires_at), now + minutes * 60000) : 0;
  const validNote = note.trim().length >= 20 && note.length <= 4000 && !note.includes('\0');
  const canApprove = !!choice && deadline > now && reviewed && validNote, canWithdraw = !!withdrawal && validNote;
  function close() { if (busy || pending || blocked) return; setExpanded(false); setNote(''); setReviewed(false); setMessage(''); }
  function refresh() { if (disabled || pending || busy || blocked) return; setReviewed(false); setNow(Date.now()); void candidate.refetch(); }
  async function save(status: 'approved' | 'withdrawn') {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !(status === 'approved' ? canApprove : canWithdraw))) return;
    const firstAttempt = !pending, authority = status === 'approved' ? choice : withdrawal;
    let saved = pending, sent = false;
    lock.current = true; setBusy(true); setMessage('Saving your signature-release review…');
    try {
      if (!saved) {
        if (!authority || !candidate.data || Date.now() - Date.parse(candidate.data.checked_at) > 30000) throw new Error('Choices expired');
        saved = pendingSignatureSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_sequence: authority.expected_sequence,
          status, basis_review_id: authority.basis_review_id, policy_id: authority.policy_id,
          expires_at: status === 'approved' ? new Date(Math.min(Date.parse(choice!.max_expires_at), Date.now() + minutes * 60000)).toISOString() : null,
          personally_reviewed: status === 'approved', note } });
        try { saved = preserveSignature(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(base, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedSignature(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setNote(''); setReviewed(false);
      setMessage('Signature-release review recorded. No agreement was sent or signed.');
      void queryClient.invalidateQueries({ queryKey: ['signature-review-choice', context.userId, context.workspaceId, context.contractId] });
      onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedSignature) {
        try { clearRejectedSignature(sessionStorage, saved, true, true); setPending(null); setReviewed(false);
          setMessage('The review was not saved. Refresh the current checks before trying again.'); void candidate.refetch(); }
        catch { setBlocked(true); setMessage('Saved signature-review recovery needs reconciliation. Keep this tab and decision details.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved signature decision; do not create another review.' : 'Review preparation could not be confirmed. Refresh checks or reconcile the saved request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Signature-release review" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <h3 className="font-semibold">Review before signing</h3>
    <p className="text-sm text-gray-600">After purchase-contract review, record a separate signature-release decision for this version. This step does not send or sign an agreement.</p>
    {blocked && <p role="alert">Saved signature-review details could not be read or preserved. Reconcile this tab before recording another decision.</p>}
    {disabled && <p className="text-sm">Finish the current document, terms or review step before continuing.</p>}
    {!expanded && !pending ? <button type="button" className={button} disabled={disabled || blocked} onClick={() => { setNow(Date.now()); setExpanded(true); setMessage(''); }}>Open signature-release review</button> : <>
      {pending ? <div className="rounded-lg border bg-white p-3 space-y-2"><h4 className="font-semibold">Recover the saved signature review</h4>
        <p>Contract version {context.contractVersion} · {pending.request.status === 'approved' ? 'Approval decision' : 'Withdrawal'}</p>
        <p className="whitespace-pre-wrap break-words">{pending.request.note}</p><p className="text-sm">The original contract review, policy, expiry and decision remain fixed until confirmed.</p></div>
        : <fieldset disabled={busy || disabled || blocked} className="space-y-3">
          <button type="button" className={button} disabled={candidate.isFetching} onClick={refresh}>Refresh signature-review choices</button>
          {candidate.isFetching && <p role="status">Checking the reviewed contract and your authority…</p>}
          {candidate.isError && <p role="alert">Signature-review choices could not be confirmed. Refresh before continuing.</p>}
          {fresh && candidate.data && <p className="text-sm">{holds[candidate.data.status]}</p>}
          {candidate.data && !fresh && !candidate.isFetching && !candidate.isError && <p>Signature-review choices are out of date. Refresh before continuing.</p>}
          {choice && <div className="rounded-lg border border-orange-200 bg-white p-3 text-sm space-y-1"><p>Reviewing contract version {context.contractVersion} using the original document from version {choice.source_version}.</p><p>Purchase-contract review recorded {new Date(choice.reviewed_at).toLocaleString()}.</p><p>This separate decision does not carry forward to changed terms.</p></div>}
          {withdrawal && <p className="text-sm">You can withdraw your original signature-release review. Its original contract-review reference will be preserved.</p>}
          <label className="block text-sm font-medium">Signature-review notes<textarea className={input} value={note} maxLength={4000} onChange={event => setNote(event.target.value)} /></label>
          <p className="text-xs text-gray-600">Explain your decision in at least 20 characters.</p>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I personally reviewed this exact contract version and original document for signature release.</label>
          <label className="block text-sm font-medium">Signature approval validity<select className={input} value={minutes} onChange={event => setMinutes(Number(event.target.value))}>{[1, 5, 15, 30, 60].map(value => <option key={value} value={value}>{value} {value === 1 ? 'minute' : 'minutes'}</option>)}</select></label>
          {choice && <p className="text-xs">Approval expires no later than {new Date(deadline).toLocaleString()}, subject to current document and reviewer authority.</p>}
        </fieldset>}
      <div className="flex flex-wrap gap-2">{pending ? <button type="button" className={button} disabled={busy || disabled || blocked || now < retryAt} onClick={() => { void save(pending.request.status); }}>Retry saved signature review</button>
        : <><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || disabled || blocked || !canApprove || now < retryAt} onClick={() => { void save('approved'); }}>Record signature-release approval</button>
          <button type="button" className={button} disabled={busy || disabled || blocked || !canWithdraw || now < retryAt} onClick={() => { void save('withdrawn'); }}>Withdraw my signature review</button>
          <button type="button" className={button} disabled={busy || blocked} onClick={close}>Close without saving</button></>}</div>
    </>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
