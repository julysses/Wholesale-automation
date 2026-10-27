import { apiFetch } from '@/lib/api';
import { costWindow } from '@/lib/costCoverage';

export type CostImportData = {
  date: string; amount_minor: number | null; coverage: 'complete' | 'partial' | 'withdrawn'; currency: 'USD';
  reporting_timezone: string; observed_at: string; external_campaign_id: string; ad_account_id: string;
  evidence_ref: string; evidence_hash: string; expected_revision: number;
};
export type CostImportRequest = { id: string; link_review_id: string; reviewed: true; data: CostImportData };
export type PendingCostImport = { user: string; workspace: string; campaign: string; request: CostImportRequest };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const numeric = /^[0-9]{1,200}$/;
const hash = /^[a-f0-9]{64}$/;
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
function keys(value: Record<string, unknown>, expected: string[]) { return Object.keys(value).sort().join('|') === expected.sort().join('|'); }

/** Decimal input is converted once, without binary floating point rounding. */
export function costMinorUnits(dollars: string): number {
  if (!/^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$/.test(dollars)) throw new Error('Enter a nonnegative USD amount with at most two decimal places');
  const [whole, fraction = ''] = dollars.split('.');
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  if (cents > 100_000_000_000_000n) throw new Error('Cost exceeds the supported amount');
  return Number(cents);
}

/** Restored requests must retain exactly the reviewed payload, never reconstructed form values. */
export function validCostRequest(value: unknown): value is CostImportRequest {
  if (!object(value) || !keys(value, ['id', 'link_review_id', 'reviewed', 'data']) || typeof value.id !== 'string' || !uuid.test(value.id)
    || typeof value.link_review_id !== 'string' || !uuid.test(value.link_review_id) || value.reviewed !== true || !object(value.data)) return false;
  const d = value.data;
  if (!keys(d, ['date','amount_minor','coverage','currency','reporting_timezone','observed_at','external_campaign_id','ad_account_id','evidence_ref','evidence_hash','expected_revision'])
    || typeof d.date !== 'string' || costWindow(d.date, d.date) !== 1 || d.currency !== 'USD'
    || !['complete','partial','withdrawn'].includes(String(d.coverage))
    || (d.coverage === 'withdrawn' ? d.amount_minor !== null : typeof d.amount_minor !== 'number' || !Number.isSafeInteger(d.amount_minor) || d.amount_minor < 0 || d.amount_minor > 100_000_000_000_000)
    || typeof d.expected_revision !== 'number' || !Number.isSafeInteger(d.expected_revision) || d.expected_revision < 0 || d.expected_revision > 999_999_999
    || typeof d.external_campaign_id !== 'string' || !numeric.test(d.external_campaign_id) || typeof d.ad_account_id !== 'string' || !numeric.test(d.ad_account_id)
    || typeof d.evidence_ref !== 'string' || d.evidence_ref.trim().length < 10 || d.evidence_ref.length > 1000
    || typeof d.evidence_hash !== 'string' || !hash.test(d.evidence_hash)
    || typeof d.reporting_timezone !== 'string' || d.reporting_timezone.length > 100
    || typeof d.observed_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.test(d.observed_at)
    || !Number.isFinite(Date.parse(d.observed_at)) || costWindow(d.observed_at.slice(0,10), d.observed_at.slice(0,10)) !== 1) return false;
  try { new Intl.DateTimeFormat('en-US', { timeZone: d.reporting_timezone }); } catch { return false; }
  return true;
}

export function validateNewCostRequest(request: CostImportRequest, now = new Date()) {
  if (!validCostRequest(request)) throw new Error('Invalid reviewed cost evidence');
  const d = request.data; const observed = new Date(d.observed_at);
  if (observed > now) throw new Error('Observation cannot be in the future');
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: d.reporting_timezone, year:'numeric', month:'2-digit', day:'2-digit' }).formatToParts(observed);
  const part = (type: string) => parts.find(p => p.type === type)!.value;
  const localDay = `${part('year')}-${part('month')}-${part('day')}`;
  if (d.coverage === 'complete' && localDay <= d.date) throw new Error('Complete evidence requires a closed account reporting day');
}

export function costImportKey(user: string, workspace: string, campaign: string) {
  if (![user,workspace,campaign].every(value => uuid.test(value))) throw new Error('Invalid cost scope');
  return `cost-import:v1:${user}:${workspace}:${campaign}`;
}
export function restoreCostImport(storage: Pick<Storage,'getItem'>, user: string, workspace: string, campaign: string): PendingCostImport | null {
  const raw = storage.getItem(costImportKey(user,workspace,campaign)); if (raw === null) return null;
  const pending: unknown = JSON.parse(raw);
  if (!object(pending) || !keys(pending,['user','workspace','campaign','request']) || pending.user !== user || pending.workspace !== workspace || pending.campaign !== campaign || !validCostRequest(pending.request)) throw new Error('Saved cost request requires reconciliation');
  return pending as PendingCostImport;
}

/** Persist before sending. Any failure retains the exact request, including rejected retries. */
export async function submitCostImport(storage: Pick<Storage,'getItem'|'setItem'|'removeItem'>, pending: PendingCostImport) {
  const { user, workspace, campaign, request } = pending; const key = costImportKey(user,workspace,campaign);
  if (!validCostRequest(request)) throw new Error('Invalid cost request');
  const saved = restoreCostImport(storage,user,workspace,campaign);
  if (saved && JSON.stringify(saved) !== JSON.stringify(pending)) throw new Error('Reconcile the pending cost request before changing evidence');
  if (!saved) validateNewCostRequest(request);
  storage.setItem(key, JSON.stringify(pending));
  const result = await (await apiFetch(`/api/acquisition/workspaces/${workspace}/cost-evidence`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(request),
  })).json();
  if (result?.id !== request.id || result.campaign_id !== campaign || result.revision !== request.data.expected_revision + 1
    || typeof result.duplicate !== 'boolean' || result.execution_authorized !== false) throw new Error('Cost result unconfirmed; reconcile the exact request');
  // Never delete a different pending request written while this response was in flight.
  const current = restoreCostImport(storage,user,workspace,campaign);
  if (!current || JSON.stringify(current) !== JSON.stringify(pending)) throw new Error('Pending cost request changed; reconcile before continuing');
  storage.removeItem(key);
  return result as { id: string; campaign_id: string; revision: number; duplicate: boolean; execution_authorized: false };
}
