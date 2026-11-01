import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
const timestamp = z.string().datetime({ offset: true });
const sequence = z.number().int().min(0).max(2147483647);
const stateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: z.number().int().min(1).max(2147483647),
  review_id: id.nullable(), basis_review_id: id.nullable(), sequence,
  status: z.enum(['not_reviewed', 'approved', 'withdrawn', 'requires_review']), approval_current: z.boolean(),
  expires_at: timestamp.nullable(), checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
const candidateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: z.number().int().min(1).max(2147483647),
  status: z.enum(['paused', 'contract_unavailable', 'history_limit_reached', 'contract_review_required', 'reviewer_policy_required', 'ready_for_human_review']),
  candidate: z.object({ basis_review_id: id, artifact_id: id, source_version: z.number().int().min(1).max(2147483647),
    sha256: z.string().regex(/^[0-9a-f]{64}$/), reviewed_at: timestamp, policy_id: id,
    expected_sequence: sequence.max(2147483646), max_expires_at: timestamp }).strict().nullable(),
  withdrawal: z.object({ review_id: id, basis_review_id: id, policy_id: id, expected_sequence: sequence.min(1).max(2147483646) }).strict().nullable(),
  current_review: stateSchema, checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
export function parseSignatureCandidate(raw: unknown, context: DocumentContext, now = Date.now()) {
  const value = candidateSchema.parse(raw), current = value.current_review;
  for (const item of [value, current]) {
    if (item.workspace_id !== context.workspaceId || item.contract_id !== context.contractId || item.contract_version !== context.contractVersion
      || !Number.isFinite(now) || now - Date.parse(item.checked_at) > 30000 || Date.parse(item.checked_at) - now > 5000)
      throw new Error('Fresh signature review context required');
  }
  if (Date.parse(current.checked_at) !== Date.parse(value.checked_at)
    || (current.status === 'not_reviewed' ? current.review_id !== null || current.basis_review_id !== null || current.sequence !== 0
      : current.review_id === null || current.basis_review_id === null || current.sequence === 0)
    || current.approval_current !== (current.status === 'approved')
    || (current.approval_current ? current.expires_at === null || Date.parse(current.expires_at) <= Math.max(now, Date.parse(current.checked_at)) : current.expires_at !== null))
    throw new Error('Consistent signature review required');
  const choice = value.candidate, withdrawal = value.withdrawal;
  if ((value.status === 'ready_for_human_review') !== (choice !== null)
    || choice && (choice.source_version > context.contractVersion || choice.expected_sequence !== current.sequence
      || Date.parse(choice.reviewed_at) > Date.parse(value.checked_at) || Date.parse(choice.max_expires_at) <= Math.max(now, Date.parse(value.checked_at))
      || Date.parse(choice.max_expires_at) - Date.parse(value.checked_at) > 86400000)) throw new Error('Exact signature choice required');
  if (withdrawal && (withdrawal.review_id !== current.review_id || withdrawal.basis_review_id !== current.basis_review_id
    || withdrawal.expected_sequence !== current.sequence || !['approved', 'requires_review'].includes(current.status)))
    throw new Error('Exact original withdrawal required');
  return value;
}
export const signatureRequestSchema = z.object({ id, expected_sequence: z.number().int().min(0).max(2147483646),
  status: z.enum(['approved', 'withdrawn']), basis_review_id: id, policy_id: id,
  expires_at: timestamp.nullable(), personally_reviewed: z.boolean(), note: z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'))
}).strict().refine(v => v.status === 'approved' ? v.personally_reviewed && v.expires_at !== null : !v.personally_reviewed && v.expires_at === null);
export const pendingSignatureSchema = z.object({ version: z.literal(1), context: contextSchema,
  request: signatureRequestSchema }).strict();
export type PendingSignature = z.infer<typeof pendingSignatureSchema>;
export const signatureKey = (user: string, workspace: string) => `wholesale.contract.signature:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingSignature(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(signatureKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 20000) throw new Error('Invalid saved review');
  const saved = pendingSignatureSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Review scope changed');
  return saved;
}
export function preserveSignature(storage: Storage, value: PendingSignature) {
  const saved = pendingSignatureSchema.parse(value), c = saved.context, key = signatureKey(c.userId, c.workspaceId);
  const current = readPendingSignature(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another review awaits recovery');
  const raw = JSON.stringify(saved); if (raw.length > 20000) throw new Error('Saved review exceeds recovery limit'); storage.setItem(key, raw);
  if (storage.getItem(key) !== raw) throw new Error('Review recovery unavailable');
  return saved;
}
function clear(storage: Storage, saved: PendingSignature) {
  const c = saved.context, key = signatureKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingSignature(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved review changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Recovery not cleared');
}
export function clearConfirmedSignature(storage: Storage, saved: PendingSignature, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: z.number().int(), review_id: id,
    sequence: z.number().int(), status: z.enum(['approved', 'withdrawn']), duplicate: z.boolean(), review_recorded: z.literal(true),
    approval_current: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.review_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status)
    throw new Error('Review confirmation mismatch');
  clear(storage, saved);
}
export function clearRejectedSignature(storage: Storage, saved: PendingSignature, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('Earlier review outcome still unknown');
  clear(storage, saved);
}
