import { formatAcquisitionMetric } from '@/lib/acquisitionMetric';
const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);

function record(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
export function ScenarioSummary({ output }: { output: unknown }) {
  const results = record(output);
  const cases = record(results.cases);
  return <section aria-label="Underwriting cases" className="space-y-3"><h3 className="font-semibold">Scenario comparison</h3>
    <div className="grid gap-3 lg:grid-cols-3">{['downside', 'base', 'upside'].map(name => {
      const result = record(cases[name]);
      const metrics = record(result.metrics);
      const mao = result.mao == null ? null : Number(result.mao);
      return <article key={name} className="rounded-lg bg-gray-50 p-3 space-y-2"><h4 className="capitalize font-semibold">{name}</h4>
        {Array.isArray(result.missing_inputs) && result.missing_inputs.length > 0 && <p className="text-sm text-amber-800">Missing inputs: {result.missing_inputs.map(String).join(', ')}</p>}
        <p>Maximum allowable offer: {mao !== null && Number.isFinite(mao) ? money(mao) : 'Incomplete'}</p>
        <dl className="text-sm space-y-1">{Object.entries(metrics).map(([key, value]) => <div key={key}><dt className="text-gray-600">{key.replaceAll('_', ' ')}</dt><dd>{formatAcquisitionMetric(key, value)}</dd></div>)}</dl>
        {Array.isArray(result.warnings) && result.warnings.map((warning, index) => <p className="text-xs text-amber-800" key={index}>{String(warning).toLowerCase().replaceAll('_', ' ')}</p>)}
      </article>;
    })}</div>
    <p className="text-sm text-gray-600">Estimates require verification. Review input sources, cost categories and uncertainty notes below.</p>
  </section>;
}
