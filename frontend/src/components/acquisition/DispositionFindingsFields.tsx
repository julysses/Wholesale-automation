import { dispositionEntries, dispositionLabels, type DispositionFinding, type DispositionFindings } from '@/lib/acquisition/disposition-review';
import type { TitleSource } from '@/lib/acquisition/title-review';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
type Source = Omit<TitleSource, 'locator'>;
export function DispositionFindingsFields({ value, onChange, executed, legal, supplemental }: {
  value: DispositionFindings; onChange: (value: DispositionFindings) => void; executed: Source; legal: Source | null; supplemental: Source | null;
}) {
  return <div className="space-y-4">{dispositionEntries(value).map(({ name, finding: field }) => {
    const label = dispositionLabels[name];
    const change = (patch: Partial<DispositionFinding>) => {
      const updated = { ...field, ...patch };
      if (name === 'contractual_interest' || name === 'closing_structure' || name === 'remaining_obligations') onChange({ ...value, [name]: updated });
      else if (value.assignment) onChange({ ...value, assignment: { ...value.assignment, [name]: updated } });
    };
    const add = (source: Source) => { if (field.sources.length < 3) change({ sources: [...field.sources, { ...source, locator: '' }] }); };
    return <fieldset key={name} className="rounded-lg border bg-white p-3 space-y-2 min-w-0"><legend className="px-1 font-semibold">{label}</legend>
      <label className="block text-sm">{label} finding<select className={input} value={field.finding} onChange={e => { const finding = e.target.value as typeof field.finding; change({ finding, required_action: finding === 'satisfactory' ? null : field.required_action ?? '' }); }}>
        <option value="unknown">Unknown — needs review</option><option value="requires_resolution">Issue to resolve</option><option value="satisfactory">Satisfactory based on cited originals</option></select></label>
      <label className="block text-sm">{label} notes<textarea className={input} maxLength={4000} value={field.note} onChange={e => change({ note: e.target.value })} /></label>
      {field.finding !== 'satisfactory' && <label className="block text-sm">{label} next action<textarea className={input} maxLength={4000} value={field.required_action ?? ''} onChange={e => change({ required_action: e.target.value })} /></label>}
      <p className="text-xs text-gray-600">Explain the finding and next action in at least 20 characters. Cite original documents for satisfactory findings.</p>
      {field.sources.map((source, index) => <div key={index} className="rounded border bg-gray-50 p-2 space-y-2 min-w-0"><p className="text-xs break-all">Original version {source.artifact_version} · {source.artifact_id}</p>
        <label className="block text-sm">{label} source {index + 1} page or clause<input className={input} maxLength={1000} value={source.locator} onChange={e => change({ sources: field.sources.map((s, i) => i === index ? { ...s, locator: e.target.value } : s) })} /></label>
        <button type="button" className={button} onClick={() => change({ sources: field.sources.filter((_, i) => i !== index) })}>Remove {label.toLowerCase()} source {index + 1}</button></div>)}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={field.sources.length >= 3} onClick={() => add(executed)}>Cite executed contract for {label.toLowerCase()}</button>
        {value.assignment && <button type="button" className={button} disabled={!legal || field.sources.length >= 3} onClick={() => { if (legal) add(legal); }}>Cite reviewed legal source for {label.toLowerCase()}</button>}
        <button type="button" className={button} disabled={!supplemental || field.sources.length >= 3} onClick={() => { if (supplemental) add(supplemental); }}>Cite selected document for {label.toLowerCase()}</button></div>
    </fieldset>;
  })}</div>;
}
