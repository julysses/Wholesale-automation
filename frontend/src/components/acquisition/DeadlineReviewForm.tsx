import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import type { DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReferences } from '@/lib/acquisition/contract-references';
import { termLabels } from '@/lib/acquisition/contract-terms';
import { deadlineTerms, parseDeadlineCandidate, resolutionSchema, pendingDeadlineSchema, preserveDeadline, readPendingDeadline,
  clearConfirmedDeadline, clearRejectedDeadline, type PendingDeadline } from '@/lib/acquisition/deadline-review';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const holds = { paused: 'Acquisition review is paused.', contract_unavailable: 'Refresh the current awaiting-signature contract.',
  history_limit_reached: 'Review history needs administrator attention.', prepared_terms_required: 'Prepare and review the original contract terms first.',
  original_date_required: 'This term needs an original calendar date. Do not replace an unknown or already explicit time here.',
  original_evidence_review_required: 'The original date clause needs current document verification.', reviewer_policy_required: 'A reviewed policy must authorize your date interpretation.',
  evidence_review_required: 'The selected interpretation document needs current verification.', ready_for_human_review: 'Original source and reviewer checks passed. Complete your own interpretation.' };
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function DeadlineReviewForm(props: Props) {
  return <DeadlineEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function DeadlineEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingDeadline(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Date review context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingDeadline | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false);
  const [term, setTerm] = useState<typeof deadlineTerms[number]>(initial.saved?.request.term ?? 'closing_deadline');
  const [artifact, setArtifact] = useState(initial.saved?.request.artifact_id ?? ''), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [time, setTime] = useState(''), [zone, setZone] = useState(''), [offset, setOffset] = useState('');
  const [basis, setBasis] = useState<'explicit_document_time' | 'reviewed_interpretation'>('explicit_document_time');
  const [locator, setLocator] = useState(''), [rationale, setRationale] = useState(''), [note, setNote] = useState('');
  const [reviewed, setReviewed] = useState(false), [minutes, setMinutes] = useState(5), [message, setMessage] = useState('');
  const [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient(), after = cursors.at(-1)!;
  const held = expanded || busy || !!pending || blocked;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!held) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [held]);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: expanded && !disabled && !blocked && !pending, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const documents = useQuery({ ...options, queryKey: ['deadline-documents', context.userId, context.workspaceId, context.contractId, context.contractVersion, after],
    queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/references?purpose=purchase_contract&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, 'purchase_contract', after) });
  const candidate = useQuery({ ...options, enabled: options.enabled && !!artifact,
    queryKey: ['deadline-choice', context.userId, context.workspaceId, context.contractId, context.contractVersion, term, artifact],
    queryFn: async ({ signal }) => parseDeadlineCandidate(await (await apiFetch(`${base}/deadline-reviews/${term}/documents/${artifact}/candidate`, { signal, cache: 'no-store' })).json(), context, term, artifact) });
  const fresh = !disabled && !blocked && !candidate.isError && !candidate.isFetching && candidate.data
    && now - Date.parse(candidate.data.checked_at) <= 30000 && now - Date.parse(candidate.data.checked_at) >= -5000;
  const choice = fresh ? candidate.data!.candidate : null, withdrawal = fresh ? candidate.data!.withdrawal : null;
  const selected = documents.data?.items.find(row => row.artifact_id === artifact);
  const sourceMatches = !!choice && !!selected && !documents.isError && !documents.isFetching && selected.status === 'available_for_review'
    && selected.sha256 === choice.sha256 && selected.verification_id === choice.verification_id && selected.source_version === choice.source_version
    && now - Date.parse(selected.checked_at) <= 30000 && now - Date.parse(selected.checked_at) >= -5000;
  const day = candidate.data?.current_review.original_term.calendar_date;
  const proposal = resolutionSchema.safeParse({ term, calendar_date: day, local_time: time.length === 5 ? `${time}:00` : time,
    time_zone: zone, resolved_instant: `${day}T${time.length === 5 ? `${time}:00` : time}${offset}`, basis,
    source: { term, artifact_id: artifact, artifact_version: choice?.source_version, sha256: choice?.sha256, locator }, rationale });
  const validNote = note.trim().length >= 20 && note.length <= 4000 && !note.includes('\0');
  const canApprove = sourceMatches && !!choice && Date.parse(choice.max_expires_at) > now && proposal.success && reviewed && validNote;
  const canWithdraw = !!withdrawal && validNote;
  function resetEntry() { setTime(''); setZone(''); setOffset(''); setLocator(''); setRationale(''); setReviewed(false); setMessage(''); }
  function close() { if (busy || pending || blocked) return; setExpanded(false); resetEntry(); setNote(''); }
  function refresh() { if (disabled || pending || busy || blocked) return; setReviewed(false); setNow(Date.now()); void documents.refetch(); if (artifact) void candidate.refetch(); }
  async function save(status: 'approved' | 'withdrawn') {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !(status === 'approved' ? canApprove : canWithdraw))) return;
    const firstAttempt = !pending, authority = status === 'approved' ? choice : withdrawal;
    let saved = pending, sent = false;
    lock.current = true; setBusy(true); setMessage('Saving your date review…');
    try {
      if (!saved) {
        if (!authority || !candidate.data || Date.now() - Date.parse(candidate.data.checked_at) > 30000) throw new Error('Choices expired');
        saved = pendingDeadlineSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_version: context.contractVersion,
          expected_sequence: authority.expected_sequence, status, artifact_id: authority.artifact_id, verification_id: authority.verification_id, policy_id: authority.policy_id,
          expires_at: status === 'approved' ? new Date(Math.min(Date.parse(choice!.max_expires_at), Date.now() + minutes * 60000)).toISOString() : null,
          personally_reviewed: status === 'approved', note, term, resolution: status === 'approved' && proposal.success ? proposal.data : null,
          original_review_id: status === 'withdrawn' ? withdrawal!.review_id : null } });
        try { saved = preserveDeadline(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(`${base}/deadline-reviews`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedDeadline(sessionStorage, saved, receipt); setPending(null); setExpanded(false); resetEntry(); setNote('');
      setMessage('Date review recorded. The original contract date is unchanged.');
      void queryClient.invalidateQueries({ queryKey: ['deadline-choice', context.userId, context.workspaceId, context.contractId] });
      onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedDeadline) {
        try { clearRejectedDeadline(sessionStorage, saved, true, true); setPending(null); setReviewed(false);
          setMessage('The review was not saved. Refresh the checks before trying again.'); void candidate.refetch(); }
        catch { setBlocked(true); setMessage('Saved date-review recovery needs reconciliation. Keep this tab and decision details.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved date decision; do not create another review.' : 'Review preparation could not be confirmed. Refresh checks or reconcile the saved request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Contract date review" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <h3 className="font-semibold">Clarify contract dates</h3>
    <p className="text-sm text-gray-600">Before reviewing the returned agreement, clarify any calendar-only date using its original clause and a reviewed source. This does not change the signed terms.</p>
    {blocked && <p role="alert">Saved date-review details need reconciliation before another decision can be recorded.</p>}
    {disabled && <p className="text-sm">Finish the current contract step before continuing.</p>}
    {!expanded && !pending ? <button type="button" className={button} disabled={disabled || blocked} onClick={() => { setNow(Date.now()); setExpanded(true); }}>Open date review</button> : <>
      {pending ? <div className="rounded-lg border bg-white p-3 space-y-2"><h4 className="font-semibold">Recover the saved date review</h4>
        <p>Contract version {context.contractVersion} · {termLabels[pending.request.term]} · {pending.request.status === 'approved' ? 'Approval decision' : 'Withdrawal'}</p>
        <p className="whitespace-pre-wrap break-words">{pending.request.note}</p><p className="text-sm">The original source, interpretation, policy and decision stay fixed until confirmed.</p></div> : <fieldset disabled={busy || disabled || blocked} className="space-y-3 min-w-0">
        <label className="block text-sm font-medium">Date to review<select className={input} value={term} onChange={e => { setTerm(e.target.value as typeof term); resetEntry(); }}>{deadlineTerms.map(value => <option key={value} value={value}>{termLabels[value]}</option>)}</select></label>
        <label className="block text-sm font-medium">Interpretation source<select className={input} value={artifact} onChange={e => { setArtifact(e.target.value); resetEntry(); }}><option value="">Choose a contract document</option>{documents.data?.items.map(row => <option key={row.artifact_id} value={row.artifact_id}>Document from version {row.source_version} · {row.status === 'available_for_review' ? 'Verified for review' : 'Needs verification'}</option>)}</select></label>
        <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={refresh} disabled={candidate.isFetching || documents.isFetching}>Refresh date-review choices</button>
          <button type="button" className={button} disabled={cursors.length === 1 || documents.isFetching} onClick={() => { setCursors(v => v.slice(0, -1)); setArtifact(''); resetEntry(); }}>Previous documents</button>
          <button type="button" className={button} disabled={!documents.data?.next_after || documents.isFetching} onClick={() => { setCursors(v => [...v, documents.data!.next_after]); setArtifact(''); resetEntry(); }}>More documents</button></div>
        {(documents.isFetching || candidate.isFetching) && <p role="status">Checking original sources and reviewer authority…</p>}
        {(documents.isError || candidate.isError) && <p role="alert">Date-review choices could not be confirmed. Refresh before continuing.</p>}
        {fresh && candidate.data && <p className="text-sm">{holds[candidate.data.status]}</p>}
        {candidate.data && !fresh && !candidate.isFetching && !candidate.isError && <p>Choices are out of date. Refresh before continuing.</p>}
        {fresh && candidate.data && <div className="rounded-lg border bg-white p-3 text-sm space-y-1"><p>Original {termLabels[term].toLowerCase()}: {day ?? 'Not available'}</p>
          {candidate.data.original_source && <p className="break-words">Original clause: {candidate.data.original_source.locator} · version {candidate.data.original_source.artifact_version}</p>}</div>}
        {choice && <div className="space-y-3"><div className="grid gap-3 sm:grid-cols-3">
          <label className="block text-sm">Local cutoff time<input className={input} type="time" step="1" value={time} onChange={e => { setTime(e.target.value); setReviewed(false); }} /></label>
          <label className="block text-sm">Named time zone<input className={input} placeholder="America/Chicago" value={zone} onChange={e => { setZone(e.target.value); setReviewed(false); }} /></label>
          <label className="block text-sm">Explicit UTC offset<input className={input} placeholder="-06:00" value={offset} onChange={e => { setOffset(e.target.value); setReviewed(false); }} /></label></div>
          <p className="text-xs">Use the source and reviewed interpretation. A calendar date alone does not establish midnight or a time zone.</p>
          <label className="block text-sm">Interpretation basis<select className={input} value={basis} onChange={e => { setBasis(e.target.value as typeof basis); setReviewed(false); }}><option value="explicit_document_time">Explicit time in the document</option><option value="reviewed_interpretation">Reviewed interpretation</option></select></label>
          <label className="block text-sm">Interpretation source clause<input className={input} maxLength={1000} value={locator} onChange={e => { setLocator(e.target.value); setReviewed(false); }} /></label>
          <label className="block text-sm">Interpretation rationale<textarea className={input} maxLength={4000} value={rationale} onChange={e => { setRationale(e.target.value); setReviewed(false); }} /></label>
          {!proposal.success && <p className="text-sm">Complete the explicit time, matching zone and offset, source clause, and rationale of at least 20 characters.</p>}
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I personally reviewed the original date and this exact interpretation.</label>
          <label className="block text-sm">Date review validity<select className={input} value={minutes} onChange={e => setMinutes(Number(e.target.value))}>{[1, 5, 15, 30, 60].map(value => <option key={value} value={value}>{value} minutes</option>)}</select></label>
        </div>}
        {withdrawal && <p className="text-sm">You can withdraw your original review for this date, independently of the selected document.</p>}
        <label className="block text-sm font-medium">Date-review decision notes<textarea className={input} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label>
        <p className="text-xs">Explain your decision in at least 20 characters.</p>
      </fieldset>}
      <div className="flex flex-wrap gap-2">{pending ? <button type="button" className={button} disabled={busy || disabled || blocked || now < retryAt} onClick={() => { void save(pending.request.status); }}>Retry saved date review</button> : <>
        <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || disabled || blocked || !canApprove || now < retryAt} onClick={() => { void save('approved'); }}>Record date interpretation</button>
        <button type="button" className={button} disabled={busy || disabled || blocked || !canWithdraw || now < retryAt} onClick={() => { void save('withdrawn'); }}>Withdraw my date review</button>
        <button type="button" className={button} disabled={busy || blocked} onClick={close}>Close without saving</button></>}</div>
    </>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
