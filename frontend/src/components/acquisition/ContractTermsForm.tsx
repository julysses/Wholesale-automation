import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { purposes, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReferences } from '@/lib/acquisition/contract-references';
import { clearConfirmedTerms, clearRejectedTerms, readPendingTerms, preserveTerms, parseTermsVersion, termsRequest,
  emptyTerms, dollarsToCents, centsToDollars, termNames, termLabels, type ContractTerms, type TermName, type PendingTerms } from '@/lib/acquisition/contract-terms';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
function TermsSummary({ terms }: { terms: ContractTerms }) {
  const deadline = (name: 'effective' | 'inspection_deadline' | 'closing_deadline') => terms[name].precision === 'date'
    ? `${terms[name].calendar_date} (date only)` : terms[name].instant ?? 'Unknown';
  const values = { 'Purchase price': terms.purchase_price_cents === null ? 'Unknown' : `$${centsToDollars(terms.purchase_price_cents)}`,
    'Earnest money': terms.earnest_money_cents === null ? 'Unknown' : `$${centsToDollars(terms.earnest_money_cents)}`,
    'Assignment': terms.assignment_allowed === null ? 'Needs review' : terms.assignment_allowed ? 'Provision permits assignment; review required' : 'Provision does not permit assignment',
    'Effective date': deadline('effective'), 'Inspection deadline': deadline('inspection_deadline'), 'Closing deadline': deadline('closing_deadline') };
  return <dl className="grid sm:grid-cols-2 gap-2 text-sm">{Object.entries(values).map(([label, value]) => <div key={label} className="min-w-0 break-words"><dt className="font-medium">{label}</dt><dd>{value}</dd></div>)}</dl>;
}
type Props = { context: DocumentContext; disabled: boolean; onPending: (held: boolean) => void; onSaved: () => void };
export function ContractTermsForm(props: Props) {
  return <TermsEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function TermsEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingTerms(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Terms context changed.');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingTerms | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [draft, setDraft] = useState<ContractTerms | null>(null), [price, setPrice] = useState(''), [earnest, setEarnest] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [completed, setCompleted] = useState(false);
  const [kind, setKind] = useState<keyof typeof purposes>('purchase_contract'), [term, setTerm] = useState<TermName>('purchase_price');
  const [artifact, setArtifact] = useState(''), [locator, setLocator] = useState(''), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const lock = useRef(false), mounted = useRef(true), after = cursors.at(-1)!;
  const held = busy || !!pending || blocked;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held || !!draft); }, [held, draft, onPending]);
  useEffect(() => { if (!held && !draft) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held, draft]);
  const options = { enabled: !disabled && !held && !completed, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const history = useQuery({ ...options, queryKey: ['contract-terms-version', context.userId, context.workspaceId, context.contractId, context.contractVersion],
    queryFn: async ({ signal }) => parseTermsVersion(await (await apiFetch(`${base}/versions?limit=1${context.contractVersion > 1 ? `&after=${context.contractVersion - 1}` : ''}`, { signal, cache: 'no-store' })).json(), context) });
  const references = useQuery({ ...options, enabled: options.enabled && !!draft, queryKey: ['contract-terms-sources', context.userId, context.workspaceId, context.contractId, context.contractVersion, kind, after],
    queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/versions/${context.contractVersion}/references?purpose=${kind}&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, kind, after) });
  function edit() {
    if (disabled || held || completed || !history.data || history.isError || history.isFetching) return;
    const value = history.data.terms ?? emptyTerms(); setDraft({ ...value, note: '' });
    setPrice(centsToDollars(value.purchase_price_cents)); setEarnest(centsToDollars(value.earnest_money_cents)); setMessage('');
  }
  function update<K extends keyof ContractTerms>(key: K, value: ContractTerms[K]) { setDraft(previous => previous ? { ...previous, [key]: value } : previous); }
  function addSource() {
    const source = references.data?.items.find(row => row.artifact_id === artifact);
    if (!draft || disabled || held || references.isError || references.isFetching || !source || source.status !== 'available_for_review'
      || Date.now() - Date.parse(source.checked_at) > 30000 || !locator.trim() || locator.length > 1000 || Array.from(locator).some(c => c.charCodeAt(0) < 32)) {
      setMessage('Refresh document choices and enter the exact page or clause before adding a source.'); return;
    }
    update('sources', [...draft.sources.filter(row => row.term !== term), { term, artifact_id: source.artifact_id, artifact_version: source.source_version, sha256: source.sha256, locator }]);
    setLocator(''); setMessage('Original source attached to this term. It will be checked again when saved.');
  }
  let proposed: ReturnType<typeof termsRequest.safeParse> | null = null;
  try { if (draft) proposed = termsRequest.safeParse({ id: '00000000-0000-4000-8000-000000000001', expected_version: context.contractVersion,
    terms: { ...draft, purchase_price_cents: dollarsToCents(price), earnest_money_cents: dollarsToCents(earnest) } }); } catch { /* Inline guidance remains visible; no request can be sent. */ }
  async function save() {
    if (lock.current || disabled || blocked || completed || (!pending && (!proposed?.success || !history.data || history.isError || history.isFetching))) return;
    const firstAttempt = !pending; let saved = pending, sent = false;
    lock.current = true; setBusy(true); setMessage('Saving this draft version…');
    try {
      if (!saved && proposed?.success) {
        saved = preserveTerms(sessionStorage, { version: 1, context, request: { ...proposed.data, id: crypto.randomUUID() } }); setPending(saved);
      }
      if (!saved) throw new Error('Complete the terms first.');
      sent = true;
      const response = await apiFetch(`${base}/terms`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      clearConfirmedTerms(sessionStorage, saved, await response.json());
      if (mounted.current) { setPending(null); setDraft(null); setCompleted(true); setMessage('New draft version saved. Refresh the contract and complete fresh reviews before proceeding.'); onSaved(); }
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && error instanceof ApiError && error.rejectedTerms) {
        try { clearRejectedTerms(sessionStorage, saved, true, true); setPending(null); setMessage('The terms were not saved. Refresh the contract and resolve the restriction before editing again.'); setDraft(null); onSaved(); return; }
        catch { /* Uncertain storage must remain held. */ }
      }
      if (!sent && !saved) setBlocked(true);
      setMessage(saved ? 'Save is unconfirmed. Retry the same saved terms; do not create another version.' : 'Terms could not be preserved for recovery. Resolve browser storage before continuing.');
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Contract terms" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <h3 className="font-semibold">Prepare contract terms</h3>
    <p className="text-sm">Record terms from the original documents, then save a new draft version. Leave unknown details blank. Existing approvals do not carry forward.</p>
    {blocked ? <p role="alert">Saved terms could not be read safely. Reconcile the saved request before continuing.</p> : pending ? <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-2">
      <h4 className="font-semibold">Recover the saved terms</h4><p className="text-sm">Original contract version {pending.context.contractVersion}. All values and source references stay fixed until confirmation.</p><TermsSummary terms={pending.request.terms} /><p className="whitespace-pre-wrap break-words">{pending.request.terms.note}</p>
    </div> : <>
      {disabled && <p role="alert">Confirm the current contract and finish any saved document or review request first.</p>}
      {history.isError && <p role="alert">Current terms could not be confirmed. Refresh the contract before editing.</p>}
      {!draft && history.data && !history.isError && (history.data.terms ? <TermsSummary terms={history.data.terms} /> : <p className="text-sm">No contract terms recorded yet.</p>)}
      {!draft ? <div className="flex flex-wrap gap-2"><button className={button} disabled={disabled || held || completed || !history.data || history.isError || history.isFetching} onClick={edit}>Edit draft terms</button>
        <button className={button} disabled={disabled || held || history.isFetching} onClick={() => { setCompleted(false); void history.refetch(); }}>Refresh terms</button></div> : <fieldset disabled={disabled || held || completed} className="space-y-4 min-w-0">
        <legend className="font-medium">Editing from contract version {context.contractVersion}</legend>
        <div className="grid sm:grid-cols-2 gap-3"><label className="text-sm">Purchase price ($)<input className={input} inputMode="decimal" value={price} onChange={e => setPrice(e.target.value)} /></label>
          <label className="text-sm">Earnest money ($)<input className={input} inputMode="decimal" value={earnest} onChange={e => setEarnest(e.target.value)} /></label></div>
        <p className="text-xs">Blank means unknown. Enter dollars with at most two decimal places; zero earnest money is an explicit recorded amount.</p>
        <label className="block text-sm">Assignment interpretation<select className={input} value={draft.assignment_allowed === null ? 'unknown' : draft.assignment_allowed ? 'allowed' : 'not_allowed'} onChange={e => update('assignment_allowed', e.target.value === 'unknown' ? null : e.target.value === 'allowed')}><option value="unknown">Unknown / needs review</option><option value="allowed">Provision permits assignment, subject to review</option><option value="not_allowed">Provision does not permit assignment</option></select></label>
        <label className="block text-sm">Original assignment provision<textarea className={input} maxLength={4000} value={draft.assignment_provisions ?? ''} onChange={e => update('assignment_provisions', e.target.value || null)} /></label>
        {(['effective', 'inspection_deadline', 'closing_deadline'] as const).map(name => <div key={name} className="rounded-lg border bg-white p-3 space-y-2">
          <label className="block text-sm">{termLabels[name]} precision<select className={input} value={draft[name].precision} onChange={e => update(name, { precision: e.target.value as 'unknown' | 'date' | 'instant', calendar_date: null, instant: null })}><option value="unknown">Unknown</option><option value="date">Calendar date only</option><option value="instant">Exact time with time zone</option></select></label>
          {draft[name].precision === 'date' && <label className="block text-sm">{termLabels[name]}<input className={input} type="date" value={draft[name].calendar_date ?? ''} onChange={e => update(name, { ...draft[name], calendar_date: e.target.value || null })} /></label>}
          {draft[name].precision === 'instant' && <label className="block text-sm">{termLabels[name]} with time zone<input className={input} placeholder="2026-11-20T17:00:00-06:00" value={draft[name].instant ?? ''} onChange={e => update(name, { ...draft[name], instant: e.target.value || null })} /><span className="text-xs">Copy the explicit date, time and UTC offset from the source. A calendar date does not imply a midnight cutoff.</span></label>}
        </div>)}
        <div className="rounded-lg border border-orange-200 bg-white p-3 space-y-3"><h4 className="font-semibold">Attach a source to each entered term</h4>
          <label className="block text-sm">Term to cite<select className={input} value={term} onChange={e => setTerm(e.target.value as TermName)}>{termNames.map(name => <option key={name} value={name}>{termLabels[name]}</option>)}</select></label>
          <label className="block text-sm">Source document type<select className={input} value={kind} onChange={e => { setKind(e.target.value as keyof typeof purposes); setCursors([null]); setArtifact(''); }}>{Object.entries(purposes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="block text-sm">Original source document<select className={input} value={artifact} onChange={e => setArtifact(e.target.value)}><option value="">Choose a verified source</option>{references.data?.items.map((row, i) => <option key={row.artifact_id} value={row.artifact_id} disabled={row.status !== 'available_for_review'}>{i + 1}. {new Date(row.source_created_at).toLocaleDateString()} · Source version {row.source_version} · {row.status === 'available_for_review' ? 'Available' : 'Needs review'}</option>)}</select></label>
          {references.isError && <p role="alert">Source documents could not be confirmed.</p>}
          <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={references.isFetching || cursors.length === 1} onClick={() => { setCursors(c => c.slice(0, -1)); setArtifact(''); }}>Previous sources</button><button type="button" className={button} disabled={references.isFetching || references.isError || !references.data?.next_after} onClick={() => { setCursors(c => [...c, references.data!.next_after]); setArtifact(''); }}>More sources</button><button type="button" className={button} disabled={references.isFetching} onClick={() => { void references.refetch(); }}>Refresh sources</button></div>
          <label className="block text-sm">Page or clause reference<input className={input} maxLength={1000} value={locator} onChange={e => setLocator(e.target.value)} /></label>
          <button type="button" className={button} disabled={!artifact || !locator.trim() || references.isError || references.isFetching} onClick={addSource}>Attach source to term</button>
          <ul className="space-y-2">{draft.sources.map(source => <li key={source.term} className="break-words text-sm">{termLabels[source.term]} · Original version {source.artifact_version} · {source.locator}<button type="button" className={`${button} ml-2`} onClick={() => update('sources', draft.sources.filter(s => s.term !== source.term))}>Remove {termLabels[source.term].toLowerCase()} source</button></li>)}</ul>
        </div>
        <label className="block text-sm">Reason for this version<textarea className={input} maxLength={4000} value={draft.note} onChange={e => update('note', e.target.value)} /></label>
        <p className="text-xs">Describe what changed in at least 20 characters. Every entered term needs an original document and clause; an assignment interpretation also needs its provision text.</p>
        <button type="button" className={button} onClick={() => { setDraft(null); setMessage('Unsaved edits discarded.'); }}>Discard unsaved edits</button>
      </fieldset>}
    </>}
    {(pending || draft) && <button className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || completed || (!pending && (!proposed?.success || history.isError || history.isFetching))} onClick={() => { void save(); }}>{busy ? 'Saving…' : pending ? 'Retry saved terms' : 'Save new draft version'}</button>}
    {message && <p role="status" className="text-sm">{message}</p>}<p className="text-xs">Saving terms does not sign an agreement, change its legal status, or authorize assignment.</p>
  </section>;
}
