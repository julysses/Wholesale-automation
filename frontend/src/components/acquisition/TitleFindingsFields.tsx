import { titleLabels, titleFindingNames, type TitleFindings, type TitleSource } from '@/lib/acquisition/title-review';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
export function TitleFindingsFields({ value, onChange, report, supplemental }: {
  value: TitleFindings; onChange: (value: TitleFindings) => void; report: Omit<TitleSource, 'locator'>; supplemental: Omit<TitleSource, 'locator'> | null;
}) {
  return <div className="space-y-4">{titleFindingNames.map(name => {
    const field = value[name], label = titleLabels[name];
    const change = (patch: Partial<typeof field>) => onChange({ ...value, [name]: { ...field, ...patch } });
    const add = (source: Omit<TitleSource, 'locator'>) => { if (field.sources.length < 3) change({ sources: [...field.sources, { ...source, locator: '' }] }); };
    return <fieldset key={name} className="rounded-lg border bg-white p-3 space-y-2 min-w-0"><legend className="px-1 font-semibold">{label}</legend>
      <label className="block text-sm">{label} finding<select className={input} value={field.finding} onChange={e => { const finding = e.target.value as typeof field.finding; change({ finding, required_action: finding === 'satisfactory' ? null : field.required_action ?? '' }); }}>
        <option value="unknown">Unknown — needs review</option><option value="requires_resolution">Issue to resolve</option><option value="satisfactory">Satisfactory based on cited originals</option></select></label>
      <label className="block text-sm">{label} notes<textarea className={input} maxLength={4000} value={field.note} onChange={e => change({ note: e.target.value })} /></label>
      {field.finding !== 'satisfactory' && <label className="block text-sm">{label} next action<textarea className={input} maxLength={4000} value={field.required_action ?? ''} onChange={e => change({ required_action: e.target.value })} /></label>}
      <p className="text-xs text-gray-600">Explain the finding and any next action in at least 20 characters. Satisfactory findings require a source.</p>
      {field.sources.map((source, index) => <div key={index} className="rounded border bg-gray-50 p-2 space-y-2 min-w-0"><p className="text-xs break-all">Original version {source.artifact_version} · {source.artifact_id}</p>
        <label className="block text-sm">{label} source {index + 1} page or clause<input className={input} maxLength={1000} value={source.locator} onChange={e => change({ sources: field.sources.map((s, i) => i === index ? { ...s, locator: e.target.value } : s) })} /></label>
        <button type="button" className={button} onClick={() => change({ sources: field.sources.filter((_, i) => i !== index) })}>Remove {label.toLowerCase()} source {index + 1}</button></div>)}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={field.sources.length >= 3} onClick={() => add(report)}>Cite title report for {label.toLowerCase()}</button>
        <button type="button" className={button} disabled={!supplemental || field.sources.length >= 3} onClick={() => { if (supplemental) add(supplemental); }}>Cite selected document for {label.toLowerCase()}</button></div>
    </fieldset>;
  })}</div>;
}
