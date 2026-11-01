import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { parseDocuments, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReviewCandidate, reviewKinds, type ReviewKind } from '@/lib/acquisition/contract-reviews';
import { clearConfirmedReview, clearRejectedReview, pendingReviewSchema, preserveReview, readPendingReview, type PendingReview } from '@/lib/acquisition/contract-review-request';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full rounded-lg border border-gray-300 bg-white p-2';
const holds = { paused: 'Acquisition review is paused.', contract_unavailable: 'Refresh the current contract version.', reviewer_policy_required: 'A reviewed policy must authorize you for this review.', evidence_review_required: 'This document needs current verification before approval.', ready_for_human_review: 'Document and reviewer checks passed. Complete your personal review before recording a decision.' };
export function ContractReviewForm(props: { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void }) {
  return <ReviewEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function ReviewEditor({ context, disabled, onPending }: { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void }) {
  const [initial] = useState(() => { try {
    const saved = readPendingReview(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Review context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingReview | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [kind, setKind] = useState<ReviewKind>(initial.saved?.kind ?? 'contract_review');
  const [artifact, setArtifact] = useState(initial.saved?.request.artifact_id ?? '');
  const [note, setNote] = useState(''), [personallyReviewed, setPersonallyReviewed] = useState(false), [minutes, setMinutes] = useState(5);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient();
  const held = busy || !!pending || blocked, purpose = kind === 'title_review' ? 'title_report' : 'purchase_contract', after = cursors.at(-1)!;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, onPending]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: !disabled && !blocked && !pending, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const documents = useQuery({ ...options, queryKey: ['review-documents', context.userId, context.workspaceId, context.contractId, context.contractVersion, purpose, after],
    queryFn: async ({ signal }) => parseDocuments(await (await apiFetch(`${base}/documents?purpose=${purpose}&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, purpose, after) });
  const candidate = useQuery({ ...options, enabled: options.enabled && !!artifact,
    queryKey: ['review-choice', context.userId, context.workspaceId, context.contractId, context.contractVersion, kind, artifact],
    queryFn: async ({ signal }) => parseReviewCandidate(await (await apiFetch(`${base}/reviews/${kind}/documents/${artifact}/candidate`, { signal, cache: 'no-store' })).json(), context, kind, artifact) });
  const fresh = !disabled && !blocked && !candidate.isFetching && !candidate.isError && candidate.data
    && now - Date.parse(candidate.data.checked_at) <= 30000 && now - Date.parse(candidate.data.checked_at) >= -5000;
  const choice = fresh ? candidate.data!.candidate : null, withdrawal = fresh ? candidate.data!.withdrawal : null;
  const deadline = choice ? Math.min(Date.parse(choice.max_expires_at), now + minutes * 60000) : 0;
  const validNote = note.trim().length >= 20 && note.length <= 4000 && !note.includes('\0');
  const canApprove = !!choice && deadline > now && personallyReviewed && validNote;
  const canWithdraw = !!withdrawal && validNote;
  function refresh() { if (disabled || held) return; void documents.refetch(); if (artifact) void candidate.refetch(); }
  async function save(status: 'approved' | 'withdrawn') {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !(status === 'approved' ? canApprove : canWithdraw))) return;
    const firstAttempt = !pending;
    const authority = status === 'approved' ? choice : withdrawal;
    let saved = pending;
    lock.current = true; setBusy(true); setMessage('Saving your review decision…');
    let sent = false;
    try {
      if (!saved) {
        if (!authority || !candidate.data || Date.now() - Date.parse(candidate.data.checked_at) > 30000) throw new Error('Review choices expired');
        saved = pendingReviewSchema.parse({ version: 1, context, kind, request: { id: crypto.randomUUID(), expected_sequence: authority.expected_sequence,
          status, artifact_id: artifact, verification_id: authority.verification_id, policy_id: authority.policy_id,
          expires_at: status === 'approved' ? new Date(Math.min(Date.parse(choice!.max_expires_at), Date.now() + minutes * 60000)).toISOString() : null,
          personally_reviewed: status === 'approved', note } });
        try { saved = preserveReview(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(`${base}/reviews/${saved.kind}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedReview(sessionStorage, saved, receipt); setPending(null); setNote(''); setPersonallyReviewed(false);
      setMessage('Review decision recorded. Refresh current status before proceeding. No agreement was signed or sent.');
      void queryClient.invalidateQueries({ queryKey: ['contract-human-review', context.userId, context.workspaceId, context.contractId, context.contractVersion] });
      void candidate.refetch();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedReview) {
        try { clearRejectedReview(sessionStorage, saved, true, true); setPending(null); setMessage('The review was not saved. Refresh document and reviewer checks before trying again.'); }
        catch { setBlocked(true); setMessage('Saved review recovery needs reconciliation. Keep this tab and decision details.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved decision; do not create another review.' : 'Review preparation could not be confirmed. Refresh checks or reconcile the saved request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Record contract review" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <h3 className="font-semibold">Record your review</h3>
    <p className="text-sm text-gray-600">Review the exact original document and record your decision. File verification alone does not establish ownership, title or legal sufficiency.</p>
    {blocked && <p role="alert">Saved review details could not be read or preserved. Reconcile this tab before recording another decision.</p>}
    {disabled && <p role="alert">Confirm the saved contract context and finish document recovery before continuing.</p>}
    {pending ? <div className="rounded-lg border bg-white p-3"><h4 className="font-semibold">Recover the saved review</h4><p>{reviewKinds[pending.kind]} · {pending.request.status === 'approved' ? 'Approval decision' : 'Withdrawal'}</p><p className="whitespace-pre-wrap break-words">{pending.request.note}</p><p className="text-sm">The original document, reviewer policy, expiry and decision stay fixed until confirmed.</p></div> : <fieldset disabled={held || disabled} className="space-y-3">
      <label className="block text-sm font-medium">Review type<select className={input} value={kind} onChange={event => { setKind(event.target.value as ReviewKind); setArtifact(''); setCursors([null]); setPersonallyReviewed(false); setNote(''); }}>{Object.entries(reviewKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="block text-sm font-medium">Document to review<select className={input} value={artifact} onChange={event => { setArtifact(event.target.value); setPersonallyReviewed(false); setNote(''); }}><option value="">Choose a saved document</option>{!documents.isError && documents.data?.items.map((row, index) => <option key={row.artifact_id} value={row.artifact_id}>{index + 1}. {new Date(row.created_at).toLocaleString()} · {row.expected_byte_size.toLocaleString()} bytes · {row.status === 'revoked' ? 'Withdrawn' : 'Saved document'}</option>)}</select></label>
      {documents.isError && <p role="alert">Documents could not be loaded. Refresh to try again.</p>}
      <nav aria-label="Review document pages" className="flex flex-wrap gap-2"><button type="button" className={button} disabled={documents.isFetching || cursors.length === 1} onClick={() => { setCursors(values => values.slice(0, -1)); setArtifact(''); }}>Previous</button><button type="button" className={button} disabled={documents.isFetching || documents.isError || !documents.data?.next_after} onClick={() => { setCursors(values => [...values, documents.data!.next_after]); setArtifact(''); }}>More documents</button></nav>
      <button type="button" className={button} onClick={refresh} disabled={documents.isFetching || candidate.isFetching}>Refresh review choices</button>
      {candidate.isFetching && <p role="status">Checking this document and your reviewer authority…</p>}
      {candidate.isError && <p role="alert">Review choices could not be confirmed. Refresh before continuing.</p>}
      {fresh && candidate.data && <p className="text-sm">{holds[candidate.data.status]}</p>}
      {candidate.data && !fresh && !candidate.isFetching && !candidate.isError && <p>Review choices are out of date. Refresh before continuing.</p>}
      <label className="block text-sm font-medium">Review notes<textarea className={input} value={note} maxLength={4000} onChange={event => setNote(event.target.value)} /></label><p className="text-xs text-gray-600">Explain your decision in at least 20 characters.</p>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={personallyReviewed} onChange={event => setPersonallyReviewed(event.target.checked)} />I personally reviewed this exact original document for the selected review.</label>
      <label className="block text-sm font-medium">Review validity<select className={input} value={minutes} onChange={event => setMinutes(Number(event.target.value))}>{[1, 5, 15, 30, 60].map(value => <option key={value} value={value}>{value} minutes</option>)}</select></label>
      {choice && <p className="text-xs">The review will expire no later than {new Date(deadline).toLocaleString()}, subject to current document and reviewer authority.</p>}
    </fieldset>}
    <div className="flex flex-wrap gap-2">{pending ? <button className={button} disabled={busy || disabled || blocked || now < retryAt} onClick={() => { void save(pending.request.status); }}>Retry saved review</button> : <><button className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || disabled || blocked || !canApprove || now < retryAt} onClick={() => { void save('approved'); }}>Record reviewed approval</button><button className={button} disabled={busy || disabled || blocked || !canWithdraw || now < retryAt} onClick={() => { void save('withdrawn'); }}>Withdraw my review</button></>}</div>
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
    <p className="text-xs text-gray-600">Recording a review does not sign, send, market, assign or close an agreement.</p>
  </section>;
}
