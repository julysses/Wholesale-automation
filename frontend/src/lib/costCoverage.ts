import { apiFetch } from '@/lib/api';

export type CostDay = { date: string; coverage: 'complete' | 'partial' | 'withdrawn' | 'missing'; amount_minor: string | null; revision_id: string | null; revision: number | null; evidence_hash: string | null; observed_at: string | null; attribution_current: boolean | null; link_review_id: string | null };
export type CostCoverage = { workspace_id: string; campaign_id: string; start_date: string; end_date: string; as_of: string; currency: 'USD'; reporting_timezone: string | null; status: 'complete' | 'incomplete' | 'requires_review' | 'unavailable'; reason_codes: string[]; total_cost_minor: string | null; observed_cost_minor: string | null; days: CostDay[]; complete_days?: number; requested_days?: number; execution_authorized: false; cost_per_lead_minor: null; qualified_cost_per_lead_minor: null; denominator_status: 'NOT_RECONCILED'; projection_version?: string; evidence_basis?: string; minor_unit_exponent?: number; attribution_checked_at?: string };
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value);
const money = (value: unknown): value is string => typeof value === 'string' && /^(0|[1-9][0-9]{0,16})$/.test(value);
const stamp = (value: unknown) => typeof value === 'string' && /T.*(Z|[+-][0-9]{2}:[0-9]{2})$/.test(value) && Number.isFinite(Date.parse(value));
const dayTime = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value ? Date.parse(value) : NaN;
export function costWindow(start: string, end: string) {
  const length = (dayTime(end) - dayTime(start)) / 86400000 + 1;
  return Number.isInteger(length) && length >= 1 && length <= 366 ? length : null;
}
export function usdMinor(value: string | null) {
  if (value === null) return 'Unavailable';
  const amount = BigInt(value);
  return `$${(amount / 100n).toLocaleString('en-US')}.${(amount % 100n).toString().padStart(2, '0')}`;
}
export async function readCostCoverage(workspace: string, campaign: string, start: string, end: string, signal?: AbortSignal): Promise<CostCoverage> {
  const length = costWindow(start, end);
  if (!length) throw new Error('Invalid reporting dates');
  const data = await (await apiFetch(`/api/acquisition/workspaces/${workspace}/campaigns/${campaign}/cost-coverage?start_date=${start}&end_date=${end}`, { signal })).json() as CostCoverage;
  const invalid = () => { throw new Error('Cost coverage could not be verified'); };
  if (!data || data.workspace_id !== workspace || data.campaign_id !== campaign || data.start_date !== start || data.end_date !== end
    || data.currency !== 'USD' || !stamp(data.as_of) || data.execution_authorized !== false || data.cost_per_lead_minor !== null
    || data.qualified_cost_per_lead_minor !== null || data.denominator_status !== 'NOT_RECONCILED' || !Array.isArray(data.reason_codes) || !Array.isArray(data.days)) invalid();
  if (data.status === 'unavailable') {
    if (data.reporting_timezone !== null || data.total_cost_minor !== null || data.observed_cost_minor !== null || data.days.length !== 0
      || data.reason_codes.length !== 1 || data.reason_codes[0] !== 'COST_REPORTING_TIMEZONE_UNKNOWN') invalid();
    return data;
  }
  if (!['complete', 'incomplete', 'requires_review'].includes(data.status) || typeof data.reporting_timezone !== 'string' || !data.reporting_timezone
    || data.projection_version !== 'acquisition-cost-coverage-v1' || data.evidence_basis !== 'reviewed_import' || data.minor_unit_exponent !== 2
    || !stamp(data.attribution_checked_at) || data.days.length !== length || data.requested_days !== length) invalid();
  try { new Intl.DateTimeFormat('en-US', { timeZone: data.reporting_timezone! }).format(); } catch { invalid(); }
  let observed = 0n, known = 0, complete = 0, stale = false;
  const reasons = new Set<string>(); const identities = new Set<string>();
  data.days.forEach((day, index) => {
    if (!day || day.date !== new Date(dayTime(start) + index * 86400000).toISOString().slice(0, 10)
      || !['complete', 'partial', 'withdrawn', 'missing'].includes(day.coverage)) invalid();
    if (day.coverage === 'missing') {
      if (day.amount_minor !== null || day.revision_id !== null || day.revision !== null || day.evidence_hash !== null || day.observed_at !== null || day.attribution_current !== null || day.link_review_id !== null) invalid();
    } else {
      if (!uuid(day.revision_id) || identities.has(day.revision_id) || !Number.isSafeInteger(day.revision) || day.revision! < 1 || day.revision! > 2147483647
        || typeof day.evidence_hash !== 'string' || !/^[a-f0-9]{64}$/.test(day.evidence_hash) || !stamp(day.observed_at)
        || Date.parse(day.observed_at!) > Date.parse(data.as_of) || typeof day.attribution_current !== 'boolean' || !uuid(day.link_review_id)) invalid();
      identities.add(day.revision_id!); stale ||= day.attribution_current === false;
      if (day.coverage === 'withdrawn' ? day.amount_minor !== null : !money(day.amount_minor) || BigInt(day.amount_minor) > 100000000000000n) invalid();
    }
    if (day.amount_minor !== null) { observed += BigInt(day.amount_minor); known += 1; }
    if (day.coverage === 'complete') complete += 1;
    else reasons.add(`COST_${day.coverage.toUpperCase()}`);
  });
  if (stale) reasons.add('COST_ATTRIBUTION_NOT_CURRENT');
  const status = stale ? 'requires_review' : complete === length ? 'complete' : 'incomplete';
  if (data.status !== status || data.complete_days !== complete
    || data.total_cost_minor !== (status === 'complete' ? observed.toString() : null)
    || data.observed_cost_minor !== (!stale && known ? observed.toString() : null)
    || JSON.stringify([...reasons].sort()) !== JSON.stringify([...data.reason_codes].sort())) invalid();
  return data;
}
