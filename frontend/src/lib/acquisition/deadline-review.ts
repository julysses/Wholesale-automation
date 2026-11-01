import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
import { dateTerm, sourceSchema } from './contract-terms';
export const deadlineTerms = ['effective', 'inspection_deadline', 'closing_deadline'] as const;
export const deadlineTerm = z.enum(deadlineTerms);
const timestamp = z.string().datetime({ offset: true });
const version = z.number().int().min(1).max(2147483647);
const sequence = z.number().int().min(0).max(2147483647);
const note = z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'));
export const resolutionSchema = z.object({ term: deadlineTerm, calendar_date: z.string(),
  local_time: z.string().regex(/^\d{2}:\d{2}:\d{2}$/), time_zone: z.string().min(1).max(100), resolved_instant: timestamp,
  basis: z.enum(['explicit_document_time', 'reviewed_interpretation']), source: sourceSchema, rationale: note }).strict().refine(v => {
  if (v.source.term !== v.term || !dateTerm.safeParse({ precision: 'date', calendar_date: v.calendar_date, instant: null }).success) return false;
  // The operator supplies the explicit offset. Never choose an ambiguous DST
  // occurrence, invent midnight, or alter the original contract date.
  if (!/T\d{2}:\d{2}:\d{2}(?:\.0+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v.resolved_instant)) return false;
  if (v.resolved_instant.slice(0, 19) !== `${v.calendar_date}T${v.local_time}`) return false;
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: v.time_zone, hourCycle: 'h23',
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
      .formatToParts(new Date(v.resolved_instant));
    const get = (name: string) => parts.find(p => p.type === name)?.value;
    return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}:${get('second')}` === `${v.calendar_date}T${v.local_time}`;
  } catch { return false; }
}, 'Date, local time, named time zone and explicit offset must agree.');
export const deadlineRequestSchema = z.object({ id, expected_version: version, expected_sequence: sequence.max(2147483646),
  status: z.enum(['approved', 'withdrawn']), artifact_id: id, verification_id: id, policy_id: id,
  expires_at: timestamp.nullable(), personally_reviewed: z.boolean(), note, term: deadlineTerm,
  resolution: resolutionSchema.nullable(), original_review_id: id.nullable() }).strict().refine(v => v.status === 'approved'
    ? v.personally_reviewed && v.expires_at !== null && v.original_review_id === null && v.resolution !== null
      && v.resolution.term === v.term && v.resolution.source.artifact_id === v.artifact_id && v.resolution.source.artifact_version <= v.expected_version
    : !v.personally_reviewed && v.expires_at === null && v.resolution === null && v.original_review_id !== null
      && v.original_review_id !== v.id && v.expected_sequence > 0);
export const pendingDeadlineSchema = z.object({ version: z.literal(1), context: contextSchema, request: deadlineRequestSchema }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version);
export type PendingDeadline = z.infer<typeof pendingDeadlineSchema>;
export const deadlineKey = (user: string, workspace: string) => `wholesale.contract.deadline:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingDeadline(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(deadlineKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 50000) throw new Error('Saved date review exceeds recovery limits');
  const value = pendingDeadlineSchema.parse(JSON.parse(raw));
  if (value.context.userId !== user || value.context.workspaceId !== workspace) throw new Error('Saved date review scope changed');
  return value;
}
export function preserveDeadline(storage: Storage, value: PendingDeadline) {
  const saved = pendingDeadlineSchema.parse(value), c = saved.context, key = deadlineKey(c.userId, c.workspaceId);
  const prior = readPendingDeadline(storage, c.userId, c.workspaceId);
  if (prior && JSON.stringify(prior) !== JSON.stringify(saved)) throw new Error('Another date review needs recovery');
  const raw = JSON.stringify(saved); if (raw.length > 50000) throw new Error('Saved date review exceeds recovery limits');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Date review recovery unavailable'); return saved;
}
function clear(storage: Storage, value: PendingDeadline) {
  const saved = pendingDeadlineSchema.parse(value), c = saved.context;
  if (JSON.stringify(readPendingDeadline(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved date review changed');
  storage.removeItem(deadlineKey(c.userId, c.workspaceId));
  if (storage.getItem(deadlineKey(c.userId, c.workspaceId)) !== null) throw new Error('Date review recovery not cleared');
}
export function clearConfirmedDeadline(storage: Storage, saved: PendingDeadline, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('deadline_resolution'),
    review_id: id, interpretation_review_id: id, term: deadlineTerm, sequence: sequence.min(1), status: z.enum(['approved', 'withdrawn']),
    duplicate: z.boolean(), review_recorded: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.review_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status || receipt.term !== r.term
    || receipt.interpretation_review_id !== (r.status === 'approved' ? r.id : r.original_review_id)) throw new Error('Date review receipt mismatch');
  clear(storage, saved);
}
export function clearRejectedDeadline(storage: Storage, saved: PendingDeadline, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier date review outcome is still unknown'); clear(storage, saved);
}
export const deadlineStateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version,
  kind: z.literal('deadline_resolution'), term: deadlineTerm, sequence, review_sequence: sequence.min(1).nullable(),
  review_id: id.nullable(), interpretation_review_id: id.nullable(), original_term: dateTerm, resolution: resolutionSchema.nullable(),
  status: z.enum(['not_reviewed', 'approved', 'withdrawn', 'requires_review']), approval_current: z.boolean(),
  expires_at: timestamp.nullable(), checked_at: timestamp, execution_authorized: z.literal(false) }).strict().refine(v => {
  if (v.approval_current !== (v.status === 'approved') || (v.approval_current
    ? v.expires_at === null || Date.parse(v.expires_at) <= Date.parse(v.checked_at) : v.expires_at !== null)) return false;
  if (v.status === 'not_reviewed') return [v.review_id, v.interpretation_review_id, v.review_sequence, v.resolution].every(x => x === null);
  return v.review_id !== null && v.interpretation_review_id !== null && v.review_sequence !== null && v.review_sequence <= v.sequence
    && (v.status === 'withdrawn') !== (v.review_id === v.interpretation_review_id) && v.resolution !== null
    && v.resolution.term === v.term && v.resolution.source.artifact_version <= v.contract_version && v.original_term.precision === 'date'
    && v.original_term.calendar_date === v.resolution.calendar_date;
});
const candidateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, term: deadlineTerm, artifact_id: id,
  status: z.enum(['paused', 'contract_unavailable', 'history_limit_reached', 'prepared_terms_required', 'original_date_required',
    'original_evidence_review_required', 'reviewer_policy_required', 'evidence_review_required', 'ready_for_human_review']),
  candidate: z.object({ artifact_id: id, source_version: version, verification_id: id, sha256: z.string().regex(/^[a-f0-9]{64}$/),
    policy_id: id, expected_sequence: sequence.max(2147483646), max_expires_at: timestamp }).strict().nullable(),
  withdrawal: z.object({ review_id: id, artifact_id: id, source_version: version, verification_id: id, policy_id: id,
    expected_sequence: sequence.min(1).max(2147483646) }).strict().nullable(),
  original_source: sourceSchema.extend({ verification_id: id }).nullable(), current_review: deadlineStateSchema,
  checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
export function parseDeadlineState(raw: unknown, context: DocumentContext, term: typeof deadlineTerms[number], now = Date.now()) {
  const value = deadlineStateSchema.parse(raw);
  if (value.workspace_id !== context.workspaceId || value.contract_id !== context.contractId || value.contract_version !== context.contractVersion
    || value.term !== term || !Number.isFinite(now) || now - Date.parse(value.checked_at) > 30000 || Date.parse(value.checked_at) - now > 5000
    || value.approval_current && Date.parse(value.expires_at!) <= now) throw new Error('Fresh exact date review required');
  return value;
}
export function parseDeadlineCandidate(raw: unknown, context: DocumentContext, term: typeof deadlineTerms[number], artifact: string, now = Date.now()) {
  const value = candidateSchema.parse(raw), state = parseDeadlineState(value.current_review, context, term, now);
  if (value.workspace_id !== context.workspaceId || value.contract_id !== context.contractId || value.contract_version !== context.contractVersion
    || value.term !== term || value.artifact_id !== artifact || Date.parse(value.checked_at) !== Date.parse(state.checked_at)
    || (value.status === 'ready_for_human_review') !== (value.candidate !== null)) throw new Error('Exact date review choice required');
  const original = value.original_source, choice = value.candidate, withdrawal = value.withdrawal;
  if (original && (original.term !== term || original.artifact_version >= context.contractVersion)) throw new Error('Original date source required');
  if (choice && (!original || state.original_term.precision !== 'date' || choice.artifact_id !== artifact || choice.source_version > context.contractVersion
    || choice.expected_sequence !== state.sequence || Date.parse(choice.max_expires_at) <= Math.max(now, Date.parse(value.checked_at))
    || Date.parse(choice.max_expires_at) - Date.parse(value.checked_at) > 86400000)) throw new Error('Bounded date review choice required');
  if (withdrawal && (withdrawal.source_version > context.contractVersion || withdrawal.review_id !== state.review_id
    || withdrawal.expected_sequence !== state.sequence || !['approved', 'requires_review'].includes(state.status) || !state.resolution
    || withdrawal.artifact_id !== state.resolution.source.artifact_id || withdrawal.source_version !== state.resolution.source.artifact_version))
    throw new Error('Original date review withdrawal required');
  return value;
}
