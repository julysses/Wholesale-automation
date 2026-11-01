import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import type { DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReferences } from '@/lib/acquisition/contract-references';
import { termsSchema, centsToDollars, dollarsToCents, type ContractTerms } from '@/lib/acquisition/contract-terms';
import { parseExecutionCandidate, readPendingExecution, preserveExecution, pendingExecutionSchema, findingNames,
  clearConfirmedExecution, clearRejectedExecution, executionTermsHold, type PendingExecution } from '@/lib/acquisition/execution-review';
import { TermsSummary } from './ContractTermsForm';
import { ExecutionTermsFields } from './ExecutionTermsFields';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const labels = { seller_signatures: 'Seller signatures', buyer_signatures: 'Buyer signatures', signing_authority: 'Signing authority', complete_agreement: 'Complete agreement' };
const holds = { paused: 'Acquisition review is paused.', contract_unavailable: 'Refresh the current awaiting-signature contract.',
  history_limit_reached: 'Review history needs administrator attention.', prepared_terms_required: 'Prepare and review the contract terms first.',
  reviewer_policy_required: 'A reviewed policy must authorize you for this execution review.', evidence_review_required: 'The selected agreement needs current document verification.',
  ready_for_human_review: 'Document and reviewer checks passed. Complete your own findings and term comparison.' };
type Checks = Omit<NonNullable<PendingExecution['request']['findings']>, 'terms'>;
const blankChecks = (): Checks => {
  const item = () => ({ finding: 'unknown' as const, locator: '', note: '' });
  return { seller_signatures: item(), buyer_signatures: item(), signing_authority: item(), complete_agreement: item() };
};
const validNote = (value: string) => value.trim().length >= 20 && value.length <= 4000 && !value.includes('\0');
const validLocator = (value: string) => !!value.trim() && value.length <= 1000 && !Array.from(value).some(c => c.charCodeAt(0) < 32);
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function ExecutionReviewForm(props: Props) {
  return <ExecutionEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function ExecutionEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingExecution(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Execution context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingExecution | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false), [artifact, setArtifact] = useState(initial.saved?.request.artifact_id ?? '');
  const [mode, setMode] = useState<'approved' | 'withdrawn' | null>(null), [stage, setStage] = useState<'findings' | 'terms' | 'decision'>('findings');
  const [checks, setChecks] = useState<Checks>(blankChecks), [draft, setDraft] = useState<ContractTerms | null>(null);
  const [price, setPrice] = useState(''), [earnest, setEarnest] = useState(''), [note, setNote] = useState(''), [reviewed, setReviewed] = useState(false), [minutes, setMinutes] = useState(5);
  const [cursors, setCursors] = useState<(string | null)[]>([null]), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient(), after = cursors.at(-1)!;
  const held = expanded || busy || !!pending || blocked;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!held) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [held]);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: expanded && !disabled && !blocked && !pending, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const documents = useQuery({ ...options, queryKey: ['execution-documents', context.userId, context.workspaceId, context.contractId, context.contractVersion, after],
    queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/references?purpose=purchase_contract&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, 'purchase_contract', after) });
  const candidate = useQuery({ ...options, enabled: options.enabled && !!artifact,
    queryKey: ['execution-choice', context.userId, context.workspaceId, context.contractId, context.contractVersion, artifact],
    queryFn: async ({ signal }) => parseExecutionCandidate(await (await apiFetch(`${base}/execution-review/documents/${artifact}/candidate`, { signal, cache: 'no-store' })).json(), context, artifact) });
  const fresh = !disabled && !blocked && !candidate.isError && !candidate.isFetching && candidate.data
    && now - Date.parse(candidate.data.checked_at) <= 30000 && now - Date.parse(candidate.data.checked_at) >= -5000;
  const choice = fresh ? candidate.data!.candidate : null, withdrawal = fresh ? candidate.data!.withdrawal : null;
  const selected = documents.data?.items.find(row => row.artifact_id === artifact);
  const sourceMatches = !!choice && !!selected && !documents.isError && !documents.isFetching && selected.status === 'available_for_review'
    && selected.sha256 === choice.sha256 && selected.verification_id === choice.verification_id && selected.source_version === choice.source_version
    && now - Date.parse(selected.checked_at) <= 30000 && now - Date.parse(selected.checked_at) >= -5000;
  const checksComplete = findingNames.every(name => checks[name].finding === 'confirmed' && validLocator(checks[name].locator) && validNote(checks[name].note));
  let proposed: ContractTerms | null = null;
  try { if (draft) { const parsed = termsSchema.safeParse({ ...draft, purchase_price_cents: dollarsToCents(price), earnest_money_cents: dollarsToCents(earnest) }); if (parsed.success) proposed = parsed.data; } } catch { /* Incomplete entry remains visible, never submitted. */ }
  const termHold = proposed && candidate.data?.prepared_terms ? executionTermsHold(proposed, candidate.data.prepared_terms, now) : 'Complete every entered term, its source clause, and your comparison notes.';
  const canApprove = sourceMatches && !!choice && Date.parse(choice.max_expires_at) > now && checksComplete && !!proposed && !termHold && reviewed && validNote(note);
  const canWithdraw = !!withdrawal && validNote(note);
  function close() { if (busy || pending || blocked) return; setExpanded(false); setMode(null); setDraft(null); setChecks(blankChecks()); setNote(''); setReviewed(false); setMessage(''); }
  function refresh() { if (disabled || pending || busy || blocked) return; setReviewed(false); setNow(Date.now()); void documents.refetch(); if (artifact) void candidate.refetch(); }
  function begin() {
    if (!sourceMatches || !candidate.data?.prepared_terms || pending || busy || disabled) return;
    const prepared = candidate.data.prepared_terms;
    setDraft({ ...prepared, sources: [], note: '' }); setPrice(centsToDollars(prepared.purchase_price_cents)); setEarnest(centsToDollars(prepared.earnest_money_cents));
    setChecks(blankChecks()); setReviewed(false); setMode('approved'); setStage('findings'); setMessage('');
  }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !(mode === 'approved' ? canApprove : mode === 'withdrawn' && canWithdraw))) return;
    const firstAttempt = !pending; let saved = pending, sent = false;
    lock.current = true; setBusy(true); setMessage('Saving the execution review…');
    try {
      if (!saved) {
        const authority = mode === 'approved' ? choice : withdrawal;
        if (!authority || !candidate.data || Date.now() - Date.parse(candidate.data.checked_at) > 30000) throw new Error('Choices expired');
        saved = pendingExecutionSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_version: context.contractVersion,
          expected_sequence: authority.expected_sequence, status: mode, artifact_id: authority.artifact_id, verification_id: authority.verification_id,
          policy_id: authority.policy_id, expires_at: mode === 'approved' ? new Date(Math.min(Date.parse(choice!.max_expires_at), Date.now() + minutes * 60000)).toISOString() : null,
          personally_reviewed: mode === 'approved', note, findings: mode === 'approved' ? { ...checks, terms: proposed } : null } });
        try { saved = preserveExecution(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(`${base}/execution-review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedExecution(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setMode(null); setDraft(null); setChecks(blankChecks()); setReviewed(false); setNote('');
      setMessage('Execution review recorded. Contract status has not changed; advancing it is a separate reviewed step.');
      void queryClient.invalidateQueries({ queryKey: ['execution-choice', context.userId, context.workspaceId, context.contractId] }); onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedExecution) {
        try { clearRejectedExecution(sessionStorage, saved, true, true); setPending(null); setReviewed(false);
          setMessage('The review was not saved. Refresh checks and resolve the restriction before trying again.'); void candidate.refetch(); }
        catch { setBlocked(true); setMessage('Saved execution-review recovery needs reconciliation. Keep this tab and the original findings.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved execution review; do not create another decision.' : 'Review preparation could not be confirmed. Refresh checks or reconcile the saved request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Execution review" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Review the returned agreement</h3>
    <p className="text-sm text-gray-600">After document verification, record your own findings about signatures, authority and terms. This review does not sign an agreement or advance its status.</p>
    {blocked && <p role="alert">Saved execution-review details could not be read safely. Reconcile the original request before continuing.</p>}
    {!expanded && !blocked && <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>Open execution review</button>}
    {expanded && !pending && !blocked && <>
      {disabled && <p role="alert">Confirm the contract and finish the adjacent pending step first.</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy || disabled || candidate.isFetching || documents.isFetching} onClick={refresh}>Refresh review checks</button>
        <button type="button" className={button} disabled={busy} onClick={close}>Close without saving</button></div>
      {!mode && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-medium">Choose the returned agreement</legend>
        <label className="block text-sm">Verified purchase-contract document<select className={input} value={artifact} onChange={e => { setArtifact(e.target.value); setReviewed(false); }}><option value="">Choose a retained agreement</option>
          {documents.data?.items.map((row, i) => <option key={row.artifact_id} value={row.artifact_id}>{i + 1}. {new Date(row.source_created_at).toLocaleDateString()} · Original version {row.source_version} · {row.status === 'available_for_review' ? 'Available' : 'Needs verification'}</option>)}</select></label>
        <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={documents.isFetching || cursors.length === 1} onClick={() => { setCursors(c => c.slice(0, -1)); setArtifact(''); }}>Previous agreements</button>
          <button type="button" className={button} disabled={documents.isFetching || documents.isError || !documents.data?.next_after} onClick={() => { setCursors(c => [...c, documents.data!.next_after]); setArtifact(''); }}>More agreements</button></div>
      </fieldset>}
      {(documents.isError || candidate.isError) && <p role="alert">Current agreement or review choices could not be confirmed. Refresh before continuing.</p>}
      {fresh && candidate.data && <p role="status" className="text-sm">{holds[candidate.data.status]}</p>}
      {!fresh && artifact && !candidate.isFetching && <p role="status" className="text-sm">Refresh the review checks before saving a decision.</p>}
      {!mode && <div className="flex flex-wrap gap-2"><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || !sourceMatches} onClick={begin}>Start agreement review</button>
        {withdrawal && <button type="button" className={button} disabled={disabled || busy} onClick={() => { setMode('withdrawn'); setStage('decision'); setNote(''); }}>Withdraw my previous execution review</button>}</div>}
      {mode === 'approved' && stage === 'findings' && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">1. Record signature and authority findings</legend>
        <p className="text-sm">Review the actual retained agreement. Unresolved findings need human follow-up before approval.</p>
        {findingNames.map(name => <div key={name} className="rounded-lg border bg-white p-3 space-y-2">
          <label className="block text-sm">{labels[name]}<select className={input} value={checks[name].finding} onChange={e => setChecks(previous => ({ ...previous, [name]: { ...previous[name], finding: e.target.value as Checks[typeof name]['finding'] } }))}><option value="unknown">Not yet reviewed</option><option value="not_confirmed">Not confirmed / needs follow-up</option><option value="confirmed">Personally confirmed</option></select></label>
          <label className="block text-sm">{labels[name]} page or clause<input className={input} maxLength={1000} value={checks[name].locator} onChange={e => setChecks(previous => ({ ...previous, [name]: { ...previous[name], locator: e.target.value } }))} /></label>
          <label className="block text-sm">{labels[name]} findings<textarea className={input} maxLength={4000} value={checks[name].note} onChange={e => setChecks(previous => ({ ...previous, [name]: { ...previous[name], note: e.target.value } }))} /></label>
        </div>)}
        <p className="text-xs">Each finding needs its actual page or clause and at least 20 characters describing what you reviewed.</p>
        <button type="button" className={button} disabled={!checksComplete} onClick={() => setStage('terms')}>Next: compare terms</button>
      </fieldset>}
      {mode === 'approved' && stage === 'terms' && draft && <><ExecutionTermsFields context={context} draft={draft} disabled={disabled || busy} price={price} earnest={earnest} setPrice={setPrice} setEarnest={setEarnest} onChange={setDraft} />
        {termHold && <p role="status" className="text-sm">{termHold}</p>}
        <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy} onClick={() => setStage('findings')}>Back to findings</button><button type="button" className={button} disabled={disabled || busy || !proposed || !!termHold} onClick={() => setStage('decision')}>Next: review decision</button></div></>}
      {mode && stage === 'decision' && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">3. Record your decision</legend>
        {mode === 'approved' && proposed ? <><TermsSummary terms={proposed} /><label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I personally reviewed the selected agreement, all four findings and every sourced term.</label>
          <label className="block text-sm">Review validity (minutes)<input type="number" min={1} max={1440} className={input} value={minutes} onChange={e => setMinutes(Math.max(1, Math.min(1440, Number(e.target.value) || 1)))} /></label>
          <p className="text-xs">Validity is capped by current document and reviewer checks. Other cited sources are checked again on save.</p></> : <p className="text-sm">Withdraw only your previous recorded execution review. Its original agreement and findings remain in history.</p>}
        <label className="block text-sm">Decision notes<textarea className={input} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label><p className="text-xs">Explain your decision in at least 20 characters.</p>
        <div className="flex flex-wrap gap-2">{mode === 'approved' && <button type="button" className={button} onClick={() => { setStage('terms'); setReviewed(false); }}>Back to terms</button>}
          <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={now < retryAt || !(mode === 'approved' ? canApprove : canWithdraw)} onClick={() => { void save(); }}>{mode === 'approved' ? 'Record execution review' : 'Record withdrawal'}</button></div>
      </fieldset>}
    </>}
    {pending && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-3 min-w-0"><h4 className="font-semibold">Recover the saved execution review</h4>
      <p className="text-sm">Original contract version {pending.context.contractVersion}. The agreement, findings and decision remain fixed until confirmation.</p>
      {pending.request.findings && <><TermsSummary terms={pending.request.findings.terms} />{findingNames.map(name => <div key={name} className="break-words text-sm"><strong>{labels[name]}:</strong> {pending.request.findings![name].locator}<p>{pending.request.findings![name].note}</p></div>)}</>}
      <p className="whitespace-pre-wrap break-words text-sm">{pending.request.note}</p>
      <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Checking saved review…' : 'Retry saved execution review'}</button>
    </div>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
