import { z } from 'zod';
import { id, date } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
export const termNames = ['purchase_price', 'earnest_money', 'assignment', 'effective', 'inspection_deadline', 'closing_deadline'] as const;
export const termLabels = { purchase_price: 'Purchase price', earnest_money: 'Earnest money', assignment: 'Assignment provisions', effective: 'Effective date', inspection_deadline: 'Inspection deadline', closing_deadline: 'Closing deadline' };
export type TermName = typeof termNames[number];
const version = z.number().int().min(1).max(2147483647);
const calendar = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(v => v.slice(0, 4) !== '0000' && !Number.isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v);
export const dateTerm = z.object({ precision: z.enum(['unknown', 'date', 'instant']), calendar_date: calendar.nullable(), instant: z.string().datetime({ offset: true }).refine(v => calendar.safeParse(v.slice(0, 10)).success).nullable() }).strict()
  .refine(v => v.precision === 'unknown' ? v.calendar_date === null && v.instant === null : v.precision === 'date' ? v.calendar_date !== null && v.instant === null : v.calendar_date === null && v.instant !== null);
export const sourceSchema = z.object({ term: z.enum(termNames), artifact_id: id, artifact_version: version,
  sha256: z.string().regex(/^[a-f0-9]{64}$/), locator: z.string().min(1).max(1000).refine(v => !!v.trim() && !Array.from(v).some(c => c.charCodeAt(0) < 32)) }).strict();
const text = z.string().min(1).max(4000).refine(v => !!v.trim() && !v.includes('\0'));
export const termsSchema = z.object({ purchase_price_cents: z.number().int().min(1).max(Number.MAX_SAFE_INTEGER).nullable(),
  earnest_money_cents: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER).nullable(), assignment_allowed: z.boolean().nullable(),
  assignment_provisions: text.nullable(), effective: dateTerm, inspection_deadline: dateTerm, closing_deadline: dateTerm,
  sources: z.array(sourceSchema).max(6), note: text.refine(v => v.trim().length >= 20) }).strict().superRefine((v, ctx) => {
    const names = new Set(v.sources.map(s => s.term));
    const known = { purchase_price: v.purchase_price_cents !== null, earnest_money: v.earnest_money_cents !== null,
      assignment: v.assignment_allowed !== null || v.assignment_provisions !== null, effective: v.effective.precision !== 'unknown',
      inspection_deadline: v.inspection_deadline.precision !== 'unknown', closing_deadline: v.closing_deadline.precision !== 'unknown' };
    if (names.size !== v.sources.length || termNames.some(name => known[name] && !names.has(name))) ctx.addIssue({ code: 'custom', message: 'Every entered term needs one original document and clause reference.' });
    if (v.assignment_allowed !== null && v.assignment_provisions === null) ctx.addIssue({ code: 'custom', message: 'Include the original assignment provision text.' });
  });
export type ContractTerms = z.infer<typeof termsSchema>;
export type TermSource = z.infer<typeof sourceSchema>;
export const termsRequest = z.object({ id, expected_version: version.max(2147483646), terms: termsSchema }).strict()
  .refine(v => v.terms.sources.every(s => s.artifact_version <= v.expected_version), 'Future document version is not a source.');
export const pendingTermsSchema = z.object({ version: z.literal(1), context: contextSchema, request: termsRequest }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version, 'Saved contract version changed.');
export type PendingTerms = z.infer<typeof pendingTermsSchema>;
export const termsKey = (user: string, workspace: string) => `wholesale.contract.terms:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingTerms(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(termsKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 40000) throw new Error('Saved terms exceed recovery limits.');
  const saved = pendingTermsSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved terms scope changed.');
  return saved;
}
export function preserveTerms(storage: Storage, value: PendingTerms) {
  const saved = pendingTermsSchema.parse(value), c = saved.context, key = termsKey(c.userId, c.workspaceId);
  const previous = readPendingTerms(storage, c.userId, c.workspaceId);
  if (previous && JSON.stringify(previous) !== JSON.stringify(saved)) throw new Error('Another terms request needs recovery.');
  const raw = JSON.stringify(saved); if (raw.length > 40000) throw new Error('Saved terms exceed recovery limits.');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Recovery storage unavailable.'); return saved;
}
function clear(storage: Storage, saved: PendingTerms) {
  const c = saved.context, key = termsKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingTerms(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved terms changed.');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Recovery was not cleared.');
}
export function clearConfirmedTerms(storage: Storage, saved: PendingTerms, raw: unknown) {
  const r = z.object({ request_id: id, workspace_id: id, contract_id: id, version: version.min(2), status: z.literal('draft'),
    duplicate: z.boolean(), execution_authorized: z.literal(false) }).strict().parse(raw), c = saved.context;
  if (r.request_id !== saved.request.id || r.workspace_id !== c.workspaceId || r.contract_id !== c.contractId || r.version !== saved.request.expected_version + 1) throw new Error('Terms confirmation identity changed.');
  clear(storage, saved); return r;
}
export function clearRejectedTerms(storage: Storage, saved: PendingTerms, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier terms outcome is still unknown.'); clear(storage, saved);
}
const versionRecord = z.object({ id, workspace_id: id, deal_id: id, version, status: z.literal('draft'), previous_version: version.nullable(),
  terms: termsSchema.nullable(), actor_id: id, created_at: date }).strict().refine(v => v.version === 1 ? v.previous_version === null && v.terms === null
    : v.previous_version === v.version - 1 && v.terms !== null && v.terms.sources.every(s => s.artifact_version < v.version));
export function parseContractVersions(raw: unknown, context: DocumentContext, after: number | null = null) {
  const page = z.object({ workspace_id: id, contract_id: id, items: z.array(versionRecord).max(20), next_after: version.nullable(), execution_authorized: z.literal(false) }).strict().parse(raw);
  if (page.workspace_id !== context.workspaceId || page.contract_id !== context.contractId) throw new Error('Contract history scope changed.');
  let previous = after ?? 0; const seen = new Set<string>();
  for (const row of page.items) {
    if (row.workspace_id !== context.workspaceId || row.deal_id !== context.contractId || row.version <= previous || row.version > context.contractVersion || seen.has(row.id)) throw new Error('Refresh the current contract history.');
    previous = row.version; seen.add(row.id);
  }
  if (page.next_after !== null && (page.items.length !== 20 || page.next_after !== previous)) throw new Error('Contract history cursor changed.');
  return page;
}
export function parseTermsVersion(raw: unknown, context: DocumentContext) {
  const page = z.object({ workspace_id: id, contract_id: id, items: z.array(versionRecord).length(1), next_after: version.nullable(), execution_authorized: z.literal(false) }).strict().parse(raw);
  const row = page.items[0];
  if (page.workspace_id !== context.workspaceId || page.contract_id !== context.contractId || row.workspace_id !== context.workspaceId || row.deal_id !== context.contractId
    || row.version !== context.contractVersion || page.next_after !== null) throw new Error('Refresh the current contract version before editing terms.');
  return row;
}
export function dollarsToCents(value: string): number | null {
  if (value === '') return null;
  if (!/^(0|[1-9]\d*)(\.\d{1,2})?$/.test(value)) throw new Error('Use dollars with at most two decimal places.');
  const [whole, fraction = ''] = value.split('.');
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  if (cents > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('Amount exceeds supported precision.');
  return Number(cents);
}
export function centsToDollars(value: number | null) {
  if (value === null) return '';
  const cents = BigInt(value); return `${cents / 100n}.${(cents % 100n).toString().padStart(2, '0')}`;
}
export const emptyTerms = (): ContractTerms => ({ purchase_price_cents: null, earnest_money_cents: null, assignment_allowed: null,
  assignment_provisions: null, effective: { precision: 'unknown', calendar_date: null, instant: null },
  inspection_deadline: { precision: 'unknown', calendar_date: null, instant: null }, closing_deadline: { precision: 'unknown', calendar_date: null, instant: null }, sources: [], note: '' });
