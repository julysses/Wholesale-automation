import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
import { termsSchema } from './contract-terms';
import { deadlineTerm, deadlineTerms, parseDeadlineState } from './deadline-review';
const timestamp = z.string().datetime({ offset: true });
const version = z.number().int().min(1).max(2147483647);
const sequence = z.number().int().min(0).max(2147483647);
const note = z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'));
export const findingNames = ['seller_signatures', 'buyer_signatures', 'signing_authority', 'complete_agreement'] as const;
const finding = z.object({ finding: z.enum(['confirmed', 'not_confirmed', 'unknown']),
  locator: z.string().max(1000).refine(v => !!v.trim() && !Array.from(v).some(c => c.charCodeAt(0) < 32)), note }).strict();
export const findingsSchema = z.object({ seller_signatures: finding, buyer_signatures: finding,
  signing_authority: finding, complete_agreement: finding, terms: termsSchema,
  deadline_reviews: z.array(z.object({ term: deadlineTerm, review_id: id }).strict()).min(1).max(3).optional() }).strict().superRefine((v, ctx) => {
    if (v.deadline_reviews === undefined) return; // Preserve original requests and fingerprints.
    const required = deadlineTerms.filter(name => v.terms[name].precision === 'date');
    const names = v.deadline_reviews.map(review => review.term), ids = v.deadline_reviews.map(review => review.review_id);
    if (names.length !== required.length || new Set(names).size !== names.length || new Set(ids).size !== ids.length
      || required.some(name => !names.includes(name))) ctx.addIssue({ code: 'custom', message: 'Each calendar date needs its exact reviewed interpretation.' });
  });
export const executionRequestSchema = z.object({ id, expected_version: version, expected_sequence: sequence.max(2147483646),
  status: z.enum(['approved', 'withdrawn']), artifact_id: id, verification_id: id, policy_id: id,
  expires_at: timestamp.nullable(), personally_reviewed: z.boolean(), note, findings: findingsSchema.nullable() }).strict()
  .refine(v => v.status === 'approved' ? v.personally_reviewed && v.expires_at !== null && v.findings !== null
    && findingNames.every(name => v.findings![name].finding === 'confirmed')
    && v.findings.terms.sources.every(source => source.artifact_version <= v.expected_version)
    : !v.personally_reviewed && v.expires_at === null && v.findings === null);
export const pendingExecutionSchema = z.object({ version: z.literal(1), context: contextSchema, request: executionRequestSchema }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version);
export type PendingExecution = z.infer<typeof pendingExecutionSchema>;
export const executionKey = (user: string, workspace: string) => `wholesale.contract.execution:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingExecution(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(executionKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 100000) throw new Error('Saved execution review exceeds recovery limits');
  const saved = pendingExecutionSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved execution review scope changed');
  return saved;
}
export function preserveExecution(storage: Storage, value: PendingExecution) {
  const saved = pendingExecutionSchema.parse(value), c = saved.context, key = executionKey(c.userId, c.workspaceId);
  const current = readPendingExecution(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another execution review needs recovery');
  const raw = JSON.stringify(saved); if (raw.length > 100000) throw new Error('Saved execution review exceeds recovery limits');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Execution review recovery unavailable'); return saved;
}
function clear(storage: Storage, value: PendingExecution) {
  const saved = pendingExecutionSchema.parse(value), c = saved.context, key = executionKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingExecution(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved execution review changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Execution review recovery not cleared');
}
export function clearConfirmedExecution(storage: Storage, saved: PendingExecution, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('executed_contract'),
    review_id: id, sequence: sequence.min(1), status: z.enum(['approved', 'withdrawn']), duplicate: z.boolean(),
    review_recorded: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.review_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status) throw new Error('Execution receipt mismatch');
  clear(storage, saved);
}
export function clearRejectedExecution(storage: Storage, saved: PendingExecution, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier execution review outcome is still unknown'); clear(storage, saved);
}
const stateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('executed_contract'),
  review_id: id.nullable(), sequence, status: z.enum(['not_reviewed', 'approved', 'withdrawn', 'requires_review']),
  approval_current: z.boolean(), expires_at: timestamp.nullable(), checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
const candidateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, artifact_id: id,
  status: z.enum(['paused', 'contract_unavailable', 'history_limit_reached', 'prepared_terms_required', 'reviewer_policy_required', 'evidence_review_required', 'ready_for_human_review']),
  candidate: z.object({ artifact_id: id, source_version: version, verification_id: id, sha256: z.string().regex(/^[0-9a-f]{64}$/),
    policy_id: id, expected_sequence: sequence.max(2147483646), max_expires_at: timestamp }).strict().nullable(),
  withdrawal: z.object({ review_id: id, artifact_id: id, source_version: version, verification_id: id, policy_id: id,
    expected_sequence: sequence.min(1).max(2147483646) }).strict().nullable(),
  prepared_terms: termsSchema.nullable(), current_review: stateSchema, checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
export function parseExecutionCandidate(raw: unknown, context: DocumentContext, artifact: string, now = Date.now()) {
  const value = candidateSchema.parse(raw), current = value.current_review;
  for (const item of [value, current]) {
    if (item.workspace_id !== context.workspaceId || item.contract_id !== context.contractId || item.contract_version !== context.contractVersion
      || !Number.isFinite(now) || now - Date.parse(item.checked_at) > 30000 || Date.parse(item.checked_at) - now > 5000) throw new Error('Fresh execution review context required');
  }
  if (value.artifact_id !== artifact || Date.parse(value.checked_at) !== Date.parse(current.checked_at)
    || (current.status === 'not_reviewed' ? current.review_id !== null || current.sequence !== 0 : current.review_id === null || current.sequence === 0)
    || current.approval_current !== (current.status === 'approved')
    || (current.approval_current ? current.expires_at === null || Date.parse(current.expires_at) <= Math.max(now, Date.parse(current.checked_at)) : current.expires_at !== null))
    throw new Error('Consistent execution review required');
  const choice = value.candidate, withdrawal = value.withdrawal;
  if ((value.status === 'ready_for_human_review') !== (choice !== null)
    || value.prepared_terms?.sources.some(source => source.artifact_version > context.contractVersion)
    || choice && (value.prepared_terms === null || choice.artifact_id !== artifact || choice.source_version > context.contractVersion
      || choice.expected_sequence !== current.sequence || Date.parse(choice.max_expires_at) <= Math.max(now, Date.parse(value.checked_at))
      || Date.parse(choice.max_expires_at) - Date.parse(value.checked_at) > 86400000)) throw new Error('Exact bounded execution choice required');
  if (withdrawal && (withdrawal.review_id !== current.review_id || withdrawal.source_version > context.contractVersion
    || withdrawal.expected_sequence !== current.sequence || !['approved', 'requires_review'].includes(current.status))) throw new Error('Original execution withdrawal required');
  return value;
}

export function executionTermsHold(terms: z.infer<typeof termsSchema>, prepared: z.infer<typeof termsSchema>, now = Date.now()): string | null {
  if (!Number.isFinite(now) || terms.purchase_price_cents === null || terms.earnest_money_cents === null
    || terms.assignment_allowed === null || terms.assignment_provisions === null)
    return 'Complete the price, earnest money and assignment provisions from the returned agreement.';
  if (terms.earnest_money_cents > terms.purchase_price_cents) return 'Earnest money exceeds the purchase price. Resolve the discrepancy before review.';
  for (const name of ['purchase_price_cents', 'earnest_money_cents', 'assignment_allowed', 'assignment_provisions'] as const)
    if (prepared[name] !== null && prepared[name] !== terms[name]) return 'Returned terms differ from the prepared version. A separately reviewed amendment is required.';
  for (const name of ['effective', 'inspection_deadline', 'closing_deadline'] as const) {
    if (terms[name].precision !== 'instant') return 'Unknown or date-only deadlines need reviewed resolution. Do not invent a time or time zone.';
    if (prepared[name].precision !== 'unknown' && (prepared[name].precision !== 'instant'
      || Date.parse(prepared[name].instant!) !== Date.parse(terms[name].instant!)))
      return 'Returned dates differ from the prepared version. A separately reviewed amendment is required.';
  }
  const effective = Date.parse(terms.effective.instant!), inspection = Date.parse(terms.inspection_deadline.instant!), closing = Date.parse(terms.closing_deadline.instant!);
  if (![effective, inspection, closing].every(Number.isFinite) || effective > now || effective > inspection || inspection > closing || effective >= closing || closing <= now)
    return 'The effective time or contract deadlines need review before proceeding.';
  return null;
}

/** Derived comparison copies only. Persist the original calendar terms and IDs. */
export function resolveExecutionDates(terms: z.infer<typeof termsSchema>, prepared: z.infer<typeof termsSchema>,
  context: DocumentContext, states: Partial<Record<typeof deadlineTerms[number], unknown>>, now = Date.now()) {
  const compared = { ...terms }, original = { ...prepared };
  const bindings: { term: typeof deadlineTerms[number]; review_id: string }[] = [];
  let maxExpiresAt = Infinity;
  for (const name of deadlineTerms) {
    if (terms[name].precision !== 'date') continue;
    if (prepared[name].precision !== 'date' || terms[name].calendar_date !== prepared[name].calendar_date)
      throw new Error('Returned dates differ from the prepared version. A separately reviewed amendment is required.');
    const state = parseDeadlineState(states[name], context, name, now);
    if (!state.approval_current || !state.resolution || !state.review_id || !state.expires_at
      || state.original_term.calendar_date !== terms[name].calendar_date)
      throw new Error('Complete a current date interpretation in Clarify contract dates before continuing.');
    const instant = { precision: 'instant' as const, calendar_date: null, instant: state.resolution.resolved_instant };
    compared[name] = instant; original[name] = instant;
    bindings.push({ term: name, review_id: state.review_id });
    maxExpiresAt = Math.min(maxExpiresAt, Date.parse(state.expires_at));
  }
  return { compared, original, bindings, maxExpiresAt };
}
