import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { purposes, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReference, parseReferences } from '@/lib/acquisition/contract-references';
import { dispositionEntries, dispositionLabels, dispositionFindingsSchema, dispositionSources, parseDispositionCandidate, readPendingDisposition,
  preserveDisposition, pendingDispositionSchema, clearConfirmedDisposition, clearRejectedDisposition, type PendingDisposition, type DispositionFindings, type DispositionChoices } from '@/lib/acquisition/disposition-review';
import { DispositionFindingsFields } from './DispositionFindingsFields';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const validNote = (v: string) => v.trim().length >= 20 && v.length <= 4000 && !v.includes('\0');
const exitLabel = (v: string) => v === 'wholesale_assignment' ? 'Assign contractual interest' : 'Purchase for Hilltop';
const holds: Record<DispositionChoices['status'], string> = {
  paused: 'Acquisition review is paused.', contract_unavailable: 'Confirm the current contract is in title review.', history_limit_reached: 'Review history needs administrator attention.',
  proposal_required: 'Propose a purchase path first.', title_findings_required: 'Record title findings first.', reviewer_policy_required: 'A reviewed policy must authorize your review of this purchase path.',
  evidence_review_required: 'The executed contract needs current document verification.', execution_review_required: 'Renew the returned-agreement review before approval. You may record unresolved findings.',
  title_review_required: 'Resolve or renew title findings before approval. You may record unresolved findings.', legal_evidence_required: 'Assignment legal evidence needs verification. Record the missing evidence as unresolved.',
  ready_for_human_review: 'Review the original contract, findings and supporting documents.',
};
function blankFindings(exit: DispositionFindings['exit_type']): DispositionFindings {
  const item = () => ({ finding: 'unknown' as const, note: '', required_action: '', sources: [] });
  return { exit_type: exit, contractual_interest: item(), closing_structure: item(), remaining_obligations: item(),
    assignment: exit === 'wholesale_assignment' ? { assignment_provisions: item(), legal_basis: item(), seller_disclosure_requirements: item(), assignee_disclosure_requirements: item() } : null };
}
// Expiry/sequence may refresh; the actual reviewed proposal, originals and authority must not change beneath findings.
const identity = (v: NonNullable<DispositionChoices['resolution']>) => JSON.stringify([v.plan_id, v.exit_type, v.policy_id, v.execution_transition_id, v.title_entry_id, v.title_review_id, v.title_status,
  [v.executed_source.artifact_id, v.executed_source.source_version, v.executed_source.verification_id, v.executed_source.sha256],
  v.legal_source && [v.legal_source.artifact_id, v.legal_source.source_version, v.legal_source.verification_id, v.legal_source.sha256]]);
const citation = (s: NonNullable<DispositionChoices['resolution']>['executed_source']) => ({ artifact_id: s.artifact_id, artifact_version: s.source_version, sha256: s.sha256 });
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function DispositionReviewForm(props: Props) {
  return <DispositionEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function DispositionEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try { const saved = readPendingDisposition(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([k, v]) => context[k as keyof DocumentContext] !== v)) throw new Error('Disposition context changed');
    return { saved, blocked: false }; } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingDisposition | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false), [mode, setMode] = useState<PendingDisposition['request']['status'] | null>(null);
  const [stage, setStage] = useState(1), [selection, setSelection] = useState(''), [findings, setFindings] = useState<DispositionFindings>(() => blankFindings('principal_acquisition'));
  const [note, setNote] = useState(''), [reviewed, setReviewed] = useState(false), [minutes, setMinutes] = useState(5);
  const [cursors, setCursors] = useState<(string | null)[]>([null]), [supportPurpose, setSupportPurpose] = useState<keyof typeof purposes>('supporting_document'), [supportId, setSupportId] = useState('');
  const [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient();
  const held = expanded || busy || !!pending || blocked, after = cursors.at(-1)!;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}`;
  const scope = [context.userId, context.workspaceId, context.contractId, context.contractVersion];
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!held) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [held]);
  useEffect(() => { if (!held) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: expanded && !disabled && !blocked && !pending, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const candidate = useQuery({ ...options, queryKey: ['disposition-choice', ...scope], queryFn: async ({ signal }) => parseDispositionCandidate(await (await apiFetch(`${base}/disposition-review/candidate`, { signal, cache: 'no-store' })).json(), context) });
  const supporting = useQuery({ ...options, enabled: options.enabled && !!mode && mode !== 'withdrawn' && stage === 2,
    queryKey: ['disposition-support', ...scope, supportPurpose, after], queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/references?purpose=${supportPurpose}&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, supportPurpose, after) });
  const sources = dispositionSources(findings), resolutionData = candidate.data?.resolution;
  const originalIds = [...new Set([...(resolutionData ? [resolutionData.executed_source.artifact_id, ...(resolutionData.legal_source ? [resolutionData.legal_source.artifact_id] : [])] : []), ...sources.map(s => s.artifact_id)])].sort();
  const originals = useQuery({ ...options, enabled: options.enabled && !!mode && mode !== 'withdrawn' && originalIds.length > 0 && originalIds.length <= 23,
    queryKey: ['disposition-originals', ...scope, originalIds.join(',')], queryFn: async ({ signal }) => Promise.all(originalIds.map(async id => parseReference(await (await apiFetch(`${base}/references/${id}`, { signal, cache: 'no-store' })).json(), context, id))) });
  const isFresh = (date: string) => now - Date.parse(date) <= 30000 && now - Date.parse(date) >= -5000;
  const fresh = !disabled && !blocked && !candidate.isError && !candidate.isFetching && candidate.data && isFresh(candidate.data.checked_at);
  const resolution = fresh && resolutionData && Date.parse(resolutionData.available_until) > now ? resolutionData : null;
  const choice = fresh && candidate.data?.candidate && Date.parse(candidate.data.candidate.max_expires_at) > now ? candidate.data.candidate : null;
  const withdrawal = fresh ? candidate.data!.withdrawal : null;
  const sameSelection = mode === 'withdrawn' ? !!withdrawal && selection === JSON.stringify(withdrawal) : !!resolution && selection === identity(resolution);
  const support = supporting.data?.items.find(row => row.artifact_id === supportId);
  const supplemental = support && !supporting.isError && !supporting.isFetching && support.status === 'available_for_review' && isFresh(support.checked_at)
    ? { artifact_id: support.artifact_id, artifact_version: support.source_version, sha256: support.sha256 } : null;
  const originalsCurrent = !!resolution && !!originals.data && !originals.isError && !originals.isFetching && originals.data.length === originalIds.length
    && originals.data.every(row => row.status === 'available_for_review' && isFresh(row.checked_at))
    && [resolution.executed_source, resolution.legal_source].every(s => !s || originals.data!.some(row => row.artifact_id === s.artifact_id && row.verification_id === s.verification_id && row.sha256 === s.sha256 && row.source_version === s.source_version))
    && sources.every(s => originals.data!.some(row => row.artifact_id === s.artifact_id && row.source_version === s.artifact_version && row.sha256 === s.sha256));
  const parsed = dispositionFindingsSchema.safeParse(findings);
  const cites = (field: DispositionFindings['contractual_interest'], source: NonNullable<typeof resolution>['executed_source'] | null) => !!source && field.sources.some(s => s.artifact_id === source.artifact_id && s.artifact_version === source.source_version && s.sha256 === source.sha256);
  const rootsCited = !!resolution && (findings.contractual_interest.finding !== 'satisfactory' || cites(findings.contractual_interest, resolution.executed_source))
    && (!findings.assignment || (findings.assignment.assignment_provisions.finding !== 'satisfactory' || cites(findings.assignment.assignment_provisions, resolution.executed_source))
      && (findings.assignment.legal_basis.finding !== 'satisfactory' || cites(findings.assignment.legal_basis, resolution.legal_source)));
  const canApprove = sameSelection && !!choice && parsed.success && rootsCited && dispositionEntries(findings).every(i => i.finding.finding === 'satisfactory');
  const canRecord = sameSelection && validNote(note) && (mode === 'withdrawn' || !!mode && originalsCurrent && parsed.success && rootsCited && reviewed && (mode !== 'approved' || canApprove));
  function change(value: DispositionFindings) { setFindings(value); setReviewed(false); }
  function close() { if (busy || pending || blocked) return; setExpanded(false); setMode(null); setSelection(''); setReviewed(false); setNote(''); }
  function refresh() { if (disabled || busy || pending || blocked) return; setReviewed(false); setNow(Date.now()); void candidate.refetch(); if (mode && mode !== 'withdrawn') void originals.refetch(); if (stage === 2) void supporting.refetch(); }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !canRecord)) return;
    lock.current = true; setBusy(true); const firstAttempt = !pending; let saved = pending, sent = false;
    try {
      if (!saved) {
        const authority = mode === 'withdrawn' ? withdrawal : resolution;
        if (!authority || !candidate.data || Date.now() - Date.parse(candidate.data.checked_at) > 30000) throw new Error('Refresh disposition checks');
        const expires = mode === 'approved' && choice ? Math.min(Date.parse(choice.max_expires_at), Date.now() + minutes * 60000) : null;
        if (expires !== null && expires <= Date.now()) throw new Error('Disposition approval expired');
        saved = pendingDispositionSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_version: context.contractVersion,
          expected_sequence: authority.expected_sequence, status: mode, plan_id: authority.plan_id, original_review_id: mode === 'withdrawn' ? withdrawal!.review_id : null,
          policy_id: authority.policy_id, expires_at: expires === null ? null : new Date(expires).toISOString(), personally_reviewed: mode !== 'withdrawn', note, findings: mode === 'withdrawn' ? null : findings } });
        try { saved = preserveDisposition(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(`${base}/disposition-review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedDisposition(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setMode(null); setReviewed(false); setNote('');
      setMessage('Disposition decision recorded. Marketing, agreements and closing require separate approval.');
      void queryClient.invalidateQueries({ queryKey: ['disposition-choice', context.userId, context.workspaceId, context.contractId] });
      void queryClient.invalidateQueries({ queryKey: ['disposition-history', context.userId, context.workspaceId, context.contractId] }); onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedDisposition) {
        try { clearRejectedDisposition(sessionStorage, saved, true, true); setPending(null); setReviewed(false); setMessage('The disposition decision was not saved. Refresh checks and resolve the restriction.'); void candidate.refetch(); }
        catch { setBlocked(true); setMessage('Saved disposition recovery needs reconciliation. Keep the original request.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved disposition decision to avoid duplicates.' : 'Disposition preparation could not be confirmed. Refresh checks or reconcile the original request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Disposition findings review" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Review the purchase path</h3><p className="text-sm text-gray-600">Confirm the proposed path, review findings, then record your decision.</p>
    {blocked && <p role="alert">Saved disposition details could not be read safely. Reconcile the original request before continuing.</p>}
    {!expanded && !blocked && <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>Open disposition review</button>}
    {expanded && !pending && !blocked && <>
      {disabled && <p role="alert">Confirm the contract and finish the adjacent pending step first.</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy || disabled || candidate.isFetching || originals.isFetching} onClick={refresh}>Refresh disposition checks</button><button type="button" className={button} disabled={busy} onClick={close}>Close without saving</button></div>
      {candidate.isError && <p role="alert">Current disposition choices could not be confirmed.</p>}
      {fresh && candidate.data && <p role="status" className="text-sm">{holds[candidate.data.status]} Current decision: {candidate.data.current_review.status.replaceAll('_', ' ')}.</p>}
      {!fresh && !candidate.isFetching && <p role="status">Refresh disposition checks before saving.</p>}
      {!mode && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">1. Confirm the proposed purchase path</legend>
        {resolution && <p className="text-sm">{exitLabel(resolution.exit_type)} · Executed contract original version {resolution.executed_source.source_version}. Title findings: {resolution.title_status.replaceAll('_', ' ')}.</p>}
        <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={!resolution} onClick={() => { if (!resolution) return; setSelection(identity(resolution)); setMode('requires_resolution'); setStage(2); setFindings(blankFindings(resolution.exit_type)); setReviewed(false); setNote(''); }}>Start disposition findings</button>
        {withdrawal && <button type="button" className={button} onClick={() => { setSelection(JSON.stringify(withdrawal)); setMode('withdrawn'); setStage(3); setNote(''); }}>Withdraw my previous disposition decision</button>}
      </fieldset>}
      {mode && mode !== 'withdrawn' && <><ol aria-label="Disposition review steps" className="flex flex-wrap gap-3 text-sm">{['Purchase path', 'Findings', 'Decision'].map((label, i) => <li key={label} aria-current={stage === i + 1 ? 'step' : undefined} className={stage === i + 1 ? 'font-semibold text-orange-700' : 'text-gray-600'}>{i + 1}. {label}</li>)}</ol><p className="text-sm font-medium">Reviewing: {exitLabel(findings.exit_type)}</p></>}
      {mode && !sameSelection && <p role="alert">The selected review context changed or expired. Refresh checks; if the purchase path or original review changed, close and start a new review.</p>}
      {mode && mode !== 'withdrawn' && stage === 2 && <fieldset disabled={disabled || busy || !sameSelection} className="space-y-3 min-w-0"><legend className="font-semibold">2. Record findings and next actions</legend>
        <details className="rounded-lg border bg-white p-3"><summary className="cursor-pointer font-medium">Choose an optional supporting document</summary><div className="space-y-2 mt-2">
          <label className="block text-sm">Supporting document type<select className={input} value={supportPurpose} onChange={e => { setSupportPurpose(e.target.value as typeof supportPurpose); setCursors([null]); setSupportId(''); }}>{Object.entries(purposes).map(([p, label]) => <option key={p} value={p}>{label}</option>)}</select></label>
          <label className="block text-sm">Supporting document<select className={input} value={supportId} onChange={e => setSupportId(e.target.value)}><option value="">Choose an original document</option>{supporting.data?.items.map((row, i) => <option key={row.artifact_id} value={row.artifact_id}>{i + 1}. Original version {row.source_version} · {row.status.replaceAll('_', ' ')}</option>)}</select></label>
          <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={supporting.isFetching || cursors.length === 1} onClick={() => { setCursors(c => c.slice(0, -1)); setSupportId(''); }}>Previous supporting documents</button><button type="button" className={button} disabled={supporting.isFetching || supporting.isError || !supporting.data?.next_after} onClick={() => { setCursors(c => [...c, supporting.data!.next_after]); setSupportId(''); }}>More supporting documents</button></div>
          {supporting.isError && <p role="alert">Supporting documents could not be confirmed.</p>}
        </div></details>
        {resolution && <DispositionFindingsFields value={findings} onChange={change} executed={citation(resolution.executed_source)} legal={resolution.legal_source ? citation(resolution.legal_source) : null} supplemental={supplemental} />}
        <button type="button" className={button} disabled={!parsed.success || !rootsCited} onClick={() => setStage(3)}>Next: disposition decision</button>
        {!rootsCited && <p role="status" className="text-sm">Cite the executed contract for satisfactory contractual-interest and assignment-provision findings, and the reviewed legal source for a satisfactory legal-basis finding.</p>}
      </fieldset>}
      {mode && stage === 3 && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">3. Record your disposition decision</legend>
        {mode !== 'withdrawn' ? <><label className="block text-sm">Disposition decision<select className={input} value={mode} onChange={e => { setMode(e.target.value as typeof mode); setReviewed(false); }}><option value="requires_resolution">Keep on hold for resolution</option><option value="approved" disabled={!canApprove}>Approve the reviewed findings</option></select></label>
          {dispositionEntries(findings).filter(i => i.finding.finding !== 'satisfactory').map(i => <p key={i.name} className="text-sm break-words"><strong>{dispositionLabels[i.name]}:</strong> {i.finding.required_action}</p>)}
          {!canApprove && <p role="status" className="text-sm">Approval needs satisfactory findings, cited originals and current review authority.</p>}{!originalsCurrent && <p role="status" className="text-sm">Refresh the original document checks before saving.</p>}
          {mode === 'approved' && <label className="block text-sm">Disposition review validity (minutes)<input type="number" min={1} max={1440} className={input} value={minutes} onChange={e => { setMinutes(Math.max(1, Math.min(1440, Number(e.target.value) || 1))); setReviewed(false); }} /></label>}
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I personally reviewed the original contract, findings, sources and required actions.</label></> : <p className="text-sm">Withdraw your previous disposition decision. Its original purchase path, findings and decision remain in history.</p>}
        <label className="block text-sm">Disposition decision notes<textarea className={input} maxLength={4000} value={note} onChange={e => { setNote(e.target.value); setReviewed(false); }} /></label><p className="text-xs">Explain the decision in at least 20 characters. Review approval does not authorize marketing or closing.</p>
        <div className="flex flex-wrap gap-2">{mode !== 'withdrawn' && <button type="button" className={button} onClick={() => { setStage(2); setReviewed(false); }}>Back to disposition findings</button>}<button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={!canRecord || now < retryAt} onClick={() => { void save(); }}>{mode === 'withdrawn' ? 'Record disposition withdrawal' : mode === 'approved' ? 'Record disposition approval' : 'Record disposition resolution hold'}</button></div>
      </fieldset>}
    </>}
    {pending && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-3 min-w-0"><h4 className="font-semibold">Recover the saved disposition decision</h4><p className="text-sm">Original contract version {pending.context.contractVersion}. The purchase path, findings and decision remain fixed until confirmation.</p>
      {pending.request.findings && dispositionEntries(pending.request.findings).map(i => <div key={i.name} className="text-sm break-words"><strong>{dispositionLabels[i.name]}: {i.finding.finding.replaceAll('_', ' ')}</strong><p>{i.finding.note}</p><p>{i.finding.required_action}</p></div>)}
      <p className="text-sm whitespace-pre-wrap break-words">{pending.request.note}</p><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Checking saved disposition decision…' : 'Retry saved disposition decision'}</button></div>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
