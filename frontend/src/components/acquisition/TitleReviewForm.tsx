import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { purposes, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReference, parseReferences } from '@/lib/acquisition/contract-references';
import { dateTerm } from '@/lib/acquisition/contract-terms';
import { titleLabels, titleFindingNames, titleFindingsSchema, titleSources, titleApprovalExpiry, parseTitleCandidate, readPendingTitle,
  preserveTitle, pendingTitleSchema, clearConfirmedTitle, clearRejectedTitle, type PendingTitle, type TitleFindings } from '@/lib/acquisition/title-review';
import { TitleFindingsFields } from './TitleFindingsFields';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const validNote = (v: string) => v.trim().length >= 20 && v.length <= 4000 && !v.includes('\0');
const holds = { paused: 'Acquisition review is paused.', contract_unavailable: 'Confirm the current contract is in title review.', history_limit_reached: 'Review history needs administrator attention.', document_required: 'Choose a retained title report.', reviewer_policy_required: 'A reviewed policy must authorize your title review.', evidence_review_required: 'The report needs current document verification.', execution_review_required: 'The returned-agreement review needs renewal before title approval. You may still record unresolved findings.', report_freshness_policy_required: 'A reviewed report-age policy is needed before approval. You may still record unresolved findings.', ready_for_human_review: 'Complete your personal review of the original report and supporting documents.' };
function blankFindings(): TitleFindings {
  const item = () => ({ finding: 'unknown' as const, note: '', required_action: '', sources: [] });
  return { report_as_of: { precision: 'unknown', calendar_date: null, instant: null }, report_as_of_source: null, report_note: '',
    ownership: item(), legal_description: item(), liens_and_payoffs: item(), exceptions_and_encumbrances: item(), occupancy_and_possession: item() };
}
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function TitleReviewForm(props: Props) {
  return <TitleEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function TitleEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try { const saved = readPendingTitle(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([k, v]) => context[k as keyof DocumentContext] !== v)) throw new Error('Title context changed');
    return { saved, blocked: false }; } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingTitle | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false), [artifact, setArtifact] = useState(initial.saved?.request.artifact_id ?? '');
  const [mode, setMode] = useState<PendingTitle['request']['status'] | null>(null), [stage, setStage] = useState(1);
  const [findings, setFindings] = useState<TitleFindings>(blankFindings), [note, setNote] = useState(''), [reviewed, setReviewed] = useState(false), [minutes, setMinutes] = useState(5);
  const [cursors, setCursors] = useState<(string | null)[]>([null]), [supportCursors, setSupportCursors] = useState<(string | null)[]>([null]);
  const [supportPurpose, setSupportPurpose] = useState<keyof typeof purposes>('supporting_document'), [supportId, setSupportId] = useState('');
  const [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient();
  const held = expanded || busy || !!pending || blocked, after = cursors.at(-1)!, supportAfter = supportCursors.at(-1)!;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}`;
  const scope = [context.userId, context.workspaceId, context.contractId, context.contractVersion];
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!held) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [held]);
  useEffect(() => { if (!held) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: expanded && !disabled && !blocked && !pending, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const documents = useQuery({ ...options, queryKey: ['title-documents', ...scope, after], queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/references?purpose=title_report&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, 'title_report', after) });
  const candidate = useQuery({ ...options, queryKey: ['title-choice', ...scope, artifact], queryFn: async ({ signal }) => parseTitleCandidate(await (await apiFetch(`${base}/title-review/candidate${artifact ? `?artifact_id=${artifact}` : ''}`, { signal, cache: 'no-store' })).json(), context, artifact || null) });
  const supporting = useQuery({ ...options, enabled: options.enabled && !!mode && mode !== 'withdrawn' && stage === 2,
    queryKey: ['title-support', ...scope, supportPurpose, supportAfter], queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/references?purpose=${supportPurpose}&limit=20${supportAfter ? `&after=${supportAfter}` : ''}`, { signal, cache: 'no-store' })).json(), context, supportPurpose, supportAfter) });
  const sources = titleSources(findings), originalIds = [...new Set([...(artifact ? [artifact] : []), ...sources.map(s => s.artifact_id)])].sort();
  const originals = useQuery({ ...options, enabled: options.enabled && !!mode && mode !== 'withdrawn' && originalIds.length > 0 && originalIds.length <= 16,
    queryKey: ['title-originals', ...scope, originalIds.join(',')], queryFn: async ({ signal }) => Promise.all(originalIds.map(async id => parseReference(await (await apiFetch(`${base}/references/${id}`, { signal, cache: 'no-store' })).json(), context, id))) });
  const isFresh = (date: string) => now - Date.parse(date) <= 30000 && now - Date.parse(date) >= -5000;
  const fresh = !disabled && !blocked && !candidate.isError && !candidate.isFetching && candidate.data && isFresh(candidate.data.checked_at);
  const resolution = fresh ? candidate.data!.resolution : null, choice = fresh ? candidate.data!.candidate : null, withdrawal = fresh ? candidate.data!.withdrawal : null;
  const selected = documents.data?.items.find(row => row.artifact_id === artifact);
  const sourceMatches = !!resolution && !!selected && !documents.isError && !documents.isFetching && selected.status === 'available_for_review'
    && selected.sha256 === resolution.sha256 && selected.verification_id === resolution.verification_id && selected.source_version === resolution.source_version
    && isFresh(selected.checked_at) && Date.parse(resolution.available_until) > now;
  const report = selected ? { artifact_id: selected.artifact_id, artifact_version: selected.source_version, sha256: selected.sha256 } : null;
  const support = supporting.data?.items.find(row => row.artifact_id === supportId);
  const supplemental = support && !supporting.isError && !supporting.isFetching && support.status === 'available_for_review' && isFresh(support.checked_at)
    ? { artifact_id: support.artifact_id, artifact_version: support.source_version, sha256: support.sha256 } : null;
  const originalsCurrent = !!originals.data && !originals.isError && !originals.isFetching && originals.data.length === originalIds.length
    && originals.data.every(row => row.status === 'available_for_review' && isFresh(row.checked_at))
    && originals.data.some(row => row.artifact_id === artifact && row.verification_id === resolution?.verification_id && row.sha256 === resolution?.sha256 && row.source_version === resolution?.source_version)
    && sources.every(s => originals.data!.some(row => row.artifact_id === s.artifact_id && row.source_version === s.artifact_version && row.sha256 === s.sha256));
  const parsed = titleFindingsSchema.safeParse(findings);
  const reportComplete = dateTerm.safeParse(findings.report_as_of).success && validNote(findings.report_note)
    && (findings.report_as_of.precision === 'unknown' || !!findings.report_as_of_source?.locator.trim());
  let maxExpiry: number | null = null, approvalHold = 'All five findings need satisfactory outcomes and original sources before approval.';
  if (parsed.success && titleFindingNames.every(name => findings[name].finding === 'satisfactory') && choice) {
    try { maxExpiry = titleApprovalExpiry(parsed.data, choice, now); approvalHold = ''; } catch (error) { approvalHold = error instanceof Error ? error.message : 'Report freshness needs review.'; }
  }
  const canRecord = mode === 'withdrawn' ? !!withdrawal && validNote(note) : !!mode && sourceMatches && originalsCurrent && parsed.success && reviewed && validNote(note) && (mode !== 'approved' || maxExpiry !== null);
  function change(value: TitleFindings) { setFindings(value); setReviewed(false); }
  function close() { if (busy || pending || blocked) return; setExpanded(false); setMode(null); setFindings(blankFindings()); setReviewed(false); setNote(''); }
  function refresh() { if (disabled || busy || pending || blocked) return; setReviewed(false); setNow(Date.now()); void documents.refetch(); void candidate.refetch(); if (mode && mode !== 'withdrawn') void originals.refetch(); if (stage === 2) void supporting.refetch(); }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !canRecord)) return;
    lock.current = true; setBusy(true); const firstAttempt = !pending; let saved = pending, sent = false;
    try {
      if (!saved) {
        const authority = mode === 'withdrawn' ? withdrawal : resolution;
        if (!authority || !candidate.data || Date.now() - Date.parse(candidate.data.checked_at) > 30000) throw new Error('Refresh title checks');
        const expires = mode === 'approved' && choice ? Math.min(titleApprovalExpiry(findings, choice), Date.now() + minutes * 60000) : null;
        saved = pendingTitleSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_version: context.contractVersion,
          expected_sequence: authority.expected_sequence, status: mode, artifact_id: authority.artifact_id, verification_id: authority.verification_id,
          policy_id: authority.policy_id, expires_at: expires === null ? null : new Date(expires).toISOString(), personally_reviewed: mode !== 'withdrawn', note, findings: mode === 'withdrawn' ? null : findings } });
        try { saved = preserveTitle(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(`${base}/title-review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedTitle(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setMode(null); setReviewed(false); setNote('');
      setMessage('Title decision recorded. Disposition and closing require separate review and approval.');
      void queryClient.invalidateQueries({ queryKey: ['title-choice', context.userId, context.workspaceId, context.contractId] }); onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedTitle) {
        try { clearRejectedTitle(sessionStorage, saved, true, true); setPending(null); setReviewed(false); setMessage('The title decision was not saved. Refresh checks and resolve the restriction.'); void candidate.refetch(); }
        catch { setBlocked(true); setMessage('Saved title recovery needs reconciliation. Keep the original request.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved title decision to avoid duplicates.' : 'Title review preparation could not be confirmed. Refresh checks or reconcile the original request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Title findings review" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Review title findings</h3><p className="text-sm text-gray-600">Follow the report, findings and decision steps. Record unresolved issues with a specific next action.</p>
    {blocked && <p role="alert">Saved title details could not be read safely. Reconcile the original request before continuing.</p>}
    {!expanded && !blocked && <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>Open title review</button>}
    {expanded && !pending && !blocked && <>
      {disabled && <p role="alert">Confirm the contract and finish the adjacent pending step first.</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy || disabled || candidate.isFetching || documents.isFetching || originals.isFetching} onClick={refresh}>Refresh title checks</button><button type="button" className={button} disabled={busy} onClick={close}>Close without saving</button></div>
      {(documents.isError || candidate.isError) && <p role="alert">Current title documents or choices could not be confirmed.</p>}
      {fresh && candidate.data && <p role="status" className="text-sm">{holds[candidate.data.status]} Current decision: {candidate.data.current_review.status.replaceAll('_', ' ')}.</p>}
      {!fresh && !candidate.isFetching && <p role="status">Refresh title checks before saving.</p>}
      {!mode && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-medium">Choose the original title report</legend>
        <label className="block text-sm">Title report<select className={input} value={artifact} onChange={e => { setArtifact(e.target.value); setReviewed(false); }}><option value="">Choose a retained title report</option>{documents.data?.items.map((row, i) => <option key={row.artifact_id} value={row.artifact_id}>{i + 1}. {new Date(row.source_created_at).toLocaleDateString()} · Original version {row.source_version} · {row.status === 'available_for_review' ? 'Available' : 'Needs verification'}</option>)}</select></label>
        <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={documents.isFetching || cursors.length === 1} onClick={() => { setCursors(c => c.slice(0, -1)); setArtifact(''); }}>Previous title reports</button><button type="button" className={button} disabled={documents.isFetching || documents.isError || !documents.data?.next_after} onClick={() => { setCursors(c => [...c, documents.data!.next_after]); setArtifact(''); }}>More title reports</button></div>
        <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={!sourceMatches} onClick={() => { setMode('requires_resolution'); setStage(1); setFindings(blankFindings()); setReviewed(false); setNote(''); }}>Start title findings</button>
        {withdrawal && <button type="button" className={button} onClick={() => { setMode('withdrawn'); setStage(3); setNote(''); }}>Withdraw my previous title decision</button>}
      </fieldset>}
      {mode && mode !== 'withdrawn' && <ol aria-label="Title review steps" className="flex flex-wrap gap-3 text-sm">{['Report', 'Findings', 'Decision'].map((label, i) => <li key={label} aria-current={stage === i + 1 ? 'step' : undefined} className={stage === i + 1 ? 'font-semibold text-orange-700' : 'text-gray-600'}>{i + 1}. {label}</li>)}</ol>}
      {mode && mode !== 'withdrawn' && stage === 1 && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">1. Describe the report</legend>
        <label className="block text-sm">Report cutoff precision<select className={input} value={findings.report_as_of.precision} onChange={e => { const precision = e.target.value as TitleFindings['report_as_of']['precision']; change({ ...findings, report_as_of: { precision, calendar_date: precision === 'date' ? '' : null, instant: precision === 'instant' ? '' : null }, report_as_of_source: precision === 'unknown' || !report ? null : { ...report, locator: '' } }); }}><option value="unknown">Unknown</option><option value="date">Calendar date only</option><option value="instant">Exact time with time zone</option></select></label>
        {findings.report_as_of.precision === 'date' && <label className="block text-sm">Original report date<input type="date" className={input} value={findings.report_as_of.calendar_date ?? ''} onChange={e => change({ ...findings, report_as_of: { ...findings.report_as_of, calendar_date: e.target.value } })} /></label>}
        {findings.report_as_of.precision === 'instant' && <label className="block text-sm">Original report timestamp<input className={input} placeholder="2026-11-01T09:00:00-06:00" value={findings.report_as_of.instant ?? ''} onChange={e => change({ ...findings, report_as_of: { ...findings.report_as_of, instant: e.target.value } })} /></label>}
        {findings.report_as_of_source && <label className="block text-sm">Report cutoff page or clause<input className={input} maxLength={1000} value={findings.report_as_of_source.locator} onChange={e => change({ ...findings, report_as_of_source: { ...findings.report_as_of_source!, locator: e.target.value } })} /></label>}
        <p className="text-xs">Use the original precision. A calendar date is never converted into a claimed report timestamp.</p>
        <label className="block text-sm">Report scope and limitations<textarea className={input} maxLength={4000} value={findings.report_note} onChange={e => change({ ...findings, report_note: e.target.value })} /></label><p className="text-xs">At least 20 characters.</p>
        <button type="button" className={button} disabled={!reportComplete} onClick={() => setStage(2)}>Next: title findings</button>
      </fieldset>}
      {mode && mode !== 'withdrawn' && stage === 2 && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">2. Record findings and next actions</legend>
        <details className="rounded-lg border bg-white p-3"><summary className="cursor-pointer font-medium">Choose an optional supporting document</summary><div className="space-y-2 mt-2">
          <label className="block text-sm">Supporting document type<select className={input} value={supportPurpose} onChange={e => { setSupportPurpose(e.target.value as typeof supportPurpose); setSupportCursors([null]); setSupportId(''); }}>{Object.entries(purposes).map(([p, label]) => <option key={p} value={p}>{label}</option>)}</select></label>
          <label className="block text-sm">Supporting document<select className={input} value={supportId} onChange={e => setSupportId(e.target.value)}><option value="">Choose an original document</option>{supporting.data?.items.map((row, i) => <option key={row.artifact_id} value={row.artifact_id}>{i + 1}. Original version {row.source_version} · {row.status.replaceAll('_', ' ')}</option>)}</select></label>
          <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={supporting.isFetching || supportCursors.length === 1} onClick={() => { setSupportCursors(c => c.slice(0, -1)); setSupportId(''); }}>Previous supporting documents</button><button type="button" className={button} disabled={supporting.isFetching || supporting.isError || !supporting.data?.next_after} onClick={() => { setSupportCursors(c => [...c, supporting.data!.next_after]); setSupportId(''); }}>More supporting documents</button></div>
          {supporting.isError && <p role="alert">Supporting documents could not be confirmed.</p>}
        </div></details>
        {report && <TitleFindingsFields value={findings} onChange={change} report={report} supplemental={supplemental} />}
        <div className="flex flex-wrap gap-2"><button type="button" className={button} onClick={() => setStage(1)}>Back to report</button><button type="button" className={button} disabled={!parsed.success} onClick={() => setStage(3)}>Next: title decision</button></div>
      </fieldset>}
      {mode && stage === 3 && <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-semibold">3. Record your title decision</legend>
        {mode !== 'withdrawn' ? <><label className="block text-sm">Title decision<select className={input} value={mode} onChange={e => { setMode(e.target.value as typeof mode); setReviewed(false); }}><option value="requires_resolution">Keep on hold for resolution</option><option value="approved" disabled={maxExpiry === null}>Approve the reviewed findings</option></select></label>
          {titleFindingNames.filter(name => findings[name].finding !== 'satisfactory').map(name => <p key={name} className="text-sm break-words"><strong>{titleLabels[name]}:</strong> {findings[name].required_action}</p>)}
          {approvalHold && <p role="status" className="text-sm">{approvalHold}</p>}{(!sourceMatches || !originalsCurrent) && <p role="status" className="text-sm">Refresh the original document checks before saving.</p>}
          {mode === 'approved' && <label className="block text-sm">Title review validity (minutes)<input type="number" min={1} max={1440} className={input} value={minutes} onChange={e => { setMinutes(Math.max(1, Math.min(1440, Number(e.target.value) || 1))); setReviewed(false); }} /></label>}
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I personally reviewed the original report, all findings, sources and required actions.</label></> : <p className="text-sm">Withdraw your previous title decision. The original report, findings and decision remain in history.</p>}
        <label className="block text-sm">Title decision notes<textarea className={input} maxLength={4000} value={note} onChange={e => { setNote(e.target.value); setReviewed(false); }} /></label><p className="text-xs">Explain the decision in at least 20 characters. Approval remains bounded by the current report-age and reviewer policies.</p>
        <div className="flex flex-wrap gap-2">{mode !== 'withdrawn' && <button type="button" className={button} onClick={() => { setStage(2); setReviewed(false); }}>Back to title findings</button>}<button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={!canRecord || now < retryAt} onClick={() => { void save(); }}>{mode === 'withdrawn' ? 'Record title withdrawal' : mode === 'approved' ? 'Record title approval' : 'Record resolution hold'}</button></div>
      </fieldset>}
    </>}
    {pending && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-3 min-w-0"><h4 className="font-semibold">Recover the saved title decision</h4><p className="text-sm">Original contract version {pending.context.contractVersion}. The report, findings and decision remain fixed until confirmation.</p>
      {pending.request.findings && <><p className="text-sm break-words">{pending.request.findings.report_note}</p>{titleFindingNames.map(name => <div key={name} className="text-sm break-words"><strong>{titleLabels[name]}: {pending.request.findings![name].finding.replaceAll('_', ' ')}</strong><p>{pending.request.findings![name].note}</p><p>{pending.request.findings![name].required_action}</p></div>)}</>}
      <p className="text-sm whitespace-pre-wrap break-words">{pending.request.note}</p><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Checking saved title decision…' : 'Retry saved title decision'}</button></div>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
