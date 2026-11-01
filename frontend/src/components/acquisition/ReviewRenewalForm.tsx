import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseRenewalChoice, parseRenewalIndex, type RenewalChoice } from '@/lib/acquisition/review-renewal-choices';
import { readPendingRenewal, preserveRenewal, clearConfirmedRenewal, clearRejectedRenewal, pendingRenewalSchema,
  renewalLabels, type PendingRenewal } from '@/lib/acquisition/review-renewal';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const holds: Record<RenewalChoice['status'], string> = {
  paused: 'Acquisition review is paused.', contract_unavailable: 'Confirm the current contract before renewing a review.',
  withdrawn_or_superseded: 'This original review was withdrawn or replaced. Start with the current contract findings.',
  history_limit_reached: 'Review history needs administrator attention.', reviewer_policy_required: 'Your review authorization needs administrator attention.',
  supporting_review_required: 'Renew the earlier supporting review first.', evidence_review_required: 'Verify the original documents before renewing this review.',
  report_review_required: 'The title report needs a new review.', purchase_path_changed: 'The purchase path changed. Review the new proposal instead.',
  legal_evidence_required: 'Verify the reviewed legal source first.', ready_for_human_review: 'Read the original findings and confirm they still apply.',
};
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function ReviewRenewalForm(props: Props) {
  return <RenewalEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function RenewalEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingRenewal(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([k, v]) => context[k as keyof DocumentContext] !== v)) throw new Error('Recovery context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingRenewal | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false), [root, setRoot] = useState('');
  const [stage, setStage] = useState(1), [note, setNote] = useState(''), [confirmed, setConfirmed] = useState('');
  const [minutes, setMinutes] = useState(5), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0), [message, setMessage] = useState('');
  const lock = useRef(false), mounted = useRef(true), held = expanded || busy || !!pending || blocked;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}/review-renewals`;
  const scope = [context.userId, context.workspaceId, context.contractId, context.contractVersion];
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!held) return; const timer = setInterval(() => setNow(Date.now()), 1000);
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => { clearInterval(timer); window.removeEventListener('beforeunload', warn); }; }, [held]);
  const options = { enabled: expanded && !disabled && !blocked && !pending, retry: false, staleTime: 0, gcTime: 0,
    refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const index = useQuery({ ...options, queryKey: ['renewal-index', ...scope], queryFn: async ({ signal }) =>
    parseRenewalIndex(await (await apiFetch(base, { signal, cache: 'no-store' })).json(), context) });
  const choice = useQuery({ ...options, enabled: options.enabled && !!root, queryKey: ['renewal-choice', ...scope, root], queryFn: async ({ signal }) =>
    parseRenewalChoice(await (await apiFetch(`${base}/${root}/candidate`, { signal, cache: 'no-store' })).json(), context, root) });
  let current: RenewalChoice | null = null;
  if (!disabled && !blocked && !choice.isError && !choice.isFetching && choice.data) {
    try { current = parseRenewalChoice(choice.data, context, root, now); } catch { /* Expired choices must refresh. */ }
  }
  const candidate = current?.candidate, fingerprint = candidate?.expected_snapshot_sha256 ?? '';
  const canSave = !!candidate && confirmed === fingerprint && !!confirmed && note.trim().length >= 20 && note.length <= 4000 && !note.includes('\0');
  function close() { if (busy || pending || blocked) return; setExpanded(false); setRoot(''); setStage(1); setConfirmed(''); setNote(''); }
  function refresh() { if (busy || pending || disabled || blocked) return; setConfirmed(''); setNow(Date.now()); void index.refetch(); if (root) void choice.refetch(); }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !canSave)) return;
    lock.current = true; setBusy(true); const first = !pending; let saved = pending, sent = false;
    try {
      if (!saved) {
        const fresh = parseRenewalChoice(choice.data, context, root), selected = fresh.candidate;
        if (!selected || confirmed !== selected.expected_snapshot_sha256) throw new Error('Refresh review choices');
        const expires = Math.min(Date.parse(selected.max_expires_at), Date.now() + minutes * 60000);
        if (expires <= Date.now()) throw new Error('Review expired');
        saved = pendingRenewalSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_version: context.contractVersion,
          expected_sequence: selected.expected_sequence, kind: fresh.kind, deadline_term: fresh.deadline_term,
          root_review_id: root, previous_review_id: selected.previous_review_id, policy_id: selected.policy_id,
          expected_snapshot_sha256: selected.expected_snapshot_sha256, expires_at: new Date(expires).toISOString(), personally_reviewed: true, note } });
        try { saved = preserveRenewal(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(base, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedRenewal(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setRoot(''); setStage(1); setConfirmed(''); setNote('');
      setMessage('Review renewal recorded. Continue with the next contract review; transaction approvals remain separate.'); onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && first && sent && error instanceof ApiError && error.rejectedRenewal) {
        try { clearRejectedRenewal(sessionStorage, saved, true, true); setPending(null); setConfirmed(''); setMessage('The renewal was not saved. Refresh checks before reviewing again.'); void choice.refetch(); }
        catch { setBlocked(true); setMessage('Keep the original saved request for reconciliation.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved renewal to avoid duplicates.' : 'Review preparation could not be confirmed. Refresh checks or reconcile the saved request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Renew contract reviews" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Renew an earlier review</h3><p className="text-sm text-gray-600">Keep the original findings and contract history, then record your fresh personal review. Changed facts need a new findings review.</p>
    {blocked && <p role="alert">Saved renewal details could not be read safely. Reconcile the original request before continuing.</p>}
    {!expanded && !blocked && <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>Check review renewals</button>}
    {expanded && !pending && !blocked && <>
      {disabled && <p role="alert">Finish the adjacent contract step before continuing.</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={disabled || busy || index.isFetching || choice.isFetching} onClick={refresh}>Refresh renewal checks</button><button type="button" className={button} disabled={busy} onClick={close}>Close without saving</button></div>
      <ol aria-label="Review renewal steps" className="flex flex-wrap gap-3 text-sm">{['Choose review', 'Original findings', 'Confirm renewal'].map((label, i) => <li key={label} aria-current={stage === i + 1 ? 'step' : undefined} className={stage === i + 1 ? 'font-semibold text-orange-700' : 'text-gray-600'}>{i + 1}. {label}</li>)}</ol>
      {stage === 1 && <div className="space-y-3">{index.isError ? <p role="alert">Current reviews could not be confirmed. Refresh to try again.</p> : index.isFetching ? <p role="status">Checking contract reviews…</p> : index.data && <>
        {!index.data.items.length && <p>No earlier approved reviews are available for this contract version.</p>}
        <p className="text-sm">Work from contract dates through the purchase path. Earlier supporting reviews must be current first.</p>
        {index.data.items.map(item => <div key={item.root_review_id} className="rounded-lg border bg-white p-3 space-y-2"><h4 className="font-medium">{renewalLabels[item.kind]}{item.deadline_term ? ` · ${item.deadline_term.replaceAll('_', ' ')}` : ''}</h4>
          <p className="text-sm">{item.current_review?.approval_current && Date.parse(item.current_review.expires_at) > now ? 'Current review recorded.' : holds[item.status]}</p>
          <button type="button" className={button} disabled={disabled || busy} onClick={() => { setRoot(item.root_review_id); setStage(2); setConfirmed(''); setNote(''); }}>Read original review</button></div>)}
      </>}</div>}
      {stage > 1 && <>
        {choice.isFetching && <p role="status">Loading original findings…</p>}{choice.isError && <p role="alert">Original review could not be confirmed. Refresh to try again.</p>}
        {!current && !choice.isFetching && <p role="status">Refresh the review checks before continuing.</p>}
        {current && <><h4 className="font-semibold">{renewalLabels[current.kind]}</h4><p className="text-sm">{holds[current.status]}</p>
          {stage === 2 && <><div className="rounded-lg border bg-white p-3 space-y-3"><h5 className="font-medium">Original findings · {new Date(current.original.created_at).toLocaleString()}</h5><OriginalFields value={current.original.findings} /></div>
            {current.dependencies.map(d => <p key={d.root_review_id} className="text-sm">{renewalLabels[d.kind]}{d.deadline_term ? ` · ${d.deadline_term.replaceAll('_', ' ')}` : ''}: {d.approval_current ? 'Current' : 'Review required first'}</p>)}
            <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => { setStage(1); setConfirmed(''); }}>Back to reviews</button><button type="button" className={button} disabled={disabled || !candidate} onClick={() => setStage(3)}>Next: confirm renewal</button></div></>}
          {stage === 3 && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">Confirm your personal review</legend>
            <label className="block text-sm">Renewal validity (minutes)<input type="number" min={1} max={1440} className={input} value={minutes} onChange={e => { setMinutes(Math.max(1, Math.min(1440, Number(e.target.value) || 1))); setConfirmed(''); }} /></label>
            {candidate && <p className="text-xs">Validity is limited by the supporting evidence and review permissions, no later than {new Date(candidate.max_expires_at).toLocaleString()}.</p>}
            <label className="block text-sm">Renewal decision notes<textarea className={input} maxLength={4000} value={note} onChange={e => { setNote(e.target.value); setConfirmed(''); }} /></label>
            <p className="text-xs">Explain your review in at least 20 characters.</p>
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={!!fingerprint && confirmed === fingerprint} onChange={e => setConfirmed(e.target.checked ? fingerprint : '')} />I personally reviewed the original findings and supporting documents, and confirmed the facts remain unchanged.</label>
            <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => { setStage(2); setConfirmed(''); }}>Back to original findings</button><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={!canSave || now < retryAt} onClick={() => { void save(); }}>Record review renewal</button></div>
          </fieldset>}
        </>}
      </>}
    </>}
    {pending && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-3"><h4 className="font-semibold">Recover the saved renewal</h4><p className="text-sm">{renewalLabels[pending.request.kind]} · Contract version {pending.context.contractVersion}. The original review and saved decision stay fixed until confirmation.</p><p className="text-sm whitespace-pre-wrap break-words">{pending.request.note}</p><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Checking saved renewal…' : 'Retry saved renewal'}</button></div>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
/** Strictly parsed findings only; technical identities remain in server history. */
function OriginalFields({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>Not recorded</span>;
  if (typeof value !== 'object') return <span className="whitespace-pre-wrap break-words">{String(value)}</span>;
  if (Array.isArray(value)) return <ol className="space-y-2">{value.map((v, i) => <li key={i}><OriginalFields value={v} /></li>)}</ol>;
  return <dl className="space-y-2">{Object.entries(value).filter(([key]) => !key.endsWith('_id') && key !== 'sha256').map(([key, v]) => <div key={key} className="text-sm min-w-0"><dt className="font-medium capitalize">{key.replaceAll('_', ' ')}</dt><dd className="pl-3 border-l border-gray-200"><OriginalFields value={v} /></dd></div>)}</dl>;
}
