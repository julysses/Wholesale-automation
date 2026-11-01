import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { purposes, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReferences } from '@/lib/acquisition/contract-references';
import { termNames, termLabels, type ContractTerms, type TermName } from '@/lib/acquisition/contract-terms';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
type Props = { context: DocumentContext; draft: ContractTerms; disabled: boolean; price: string; earnest: string;
  setPrice: (value: string) => void; setEarnest: (value: string) => void; onChange: (value: ContractTerms) => void };
export function ExecutionTermsFields({ context, draft, disabled, price, earnest, setPrice, setEarnest, onChange }: Props) {
  const [kind, setKind] = useState<keyof typeof purposes>('purchase_contract'), [term, setTerm] = useState<TermName>('purchase_price');
  const [artifact, setArtifact] = useState(''), [locator, setLocator] = useState(''), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [message, setMessage] = useState('');
  const after = cursors.at(-1)!;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}`;
  const references = useQuery({ enabled: !disabled, queryKey: ['execution-term-sources', context.userId, context.workspaceId, context.contractId, context.contractVersion, kind, after],
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
    queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/versions/${context.contractVersion}/references?purpose=${kind}&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, kind, after) });
  function update<K extends keyof ContractTerms>(key: K, value: ContractTerms[K]) { onChange({ ...draft, [key]: value }); }
  function addSource() {
    const source = references.data?.items.find(row => row.artifact_id === artifact);
    if (disabled || references.isError || references.isFetching || !source || source.status !== 'available_for_review'
      || Date.now() - Date.parse(source.checked_at) > 30000 || !locator.trim() || locator.length > 1000 || Array.from(locator).some(c => c.charCodeAt(0) < 32)) {
      setMessage('Refresh document choices and enter the exact page or clause before adding a source.'); return;
    }
    update('sources', [...draft.sources.filter(row => row.term !== term), { term, artifact_id: source.artifact_id, artifact_version: source.source_version, sha256: source.sha256, locator }]);
    setLocator(''); setMessage('Source attached. Its authority will be checked again when the review is saved.');
  }
  return <fieldset disabled={disabled} className="space-y-4 min-w-0">
    <legend className="font-semibold">2. Compare the returned terms</legend>
    <p className="text-sm">Prepared values are a comparison aid, not confirmed facts. Check each against the returned agreement and attach its actual source clause. Differences require a separately reviewed amendment.</p>
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
        <label className="block text-sm">Returned-term review notes<textarea className={input} maxLength={4000} value={draft.note} onChange={e => update('note', e.target.value)} /></label>
        <p className="text-xs">Describe your comparison with the returned agreement in at least 20 characters. Every entered term needs an original document and clause; an assignment interpretation also needs its provision text.</p>
    {message && <p role="status" className="text-sm">{message}</p>}
  </fieldset>;
}
