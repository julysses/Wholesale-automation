import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema } from './contract-documents';
const timestamp = z.string().datetime({ offset: true });
export const reviewRequestSchema = z.object({ id, expected_sequence: z.number().int().min(0).max(2147483646),
  status: z.enum(['approved', 'withdrawn']), artifact_id: id, verification_id: id, policy_id: id,
  expires_at: timestamp.nullable(), personally_reviewed: z.boolean(), note: z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'))
}).strict().refine(v => v.status === 'approved' ? v.personally_reviewed && v.expires_at !== null : !v.personally_reviewed && v.expires_at === null);
export const pendingReviewSchema = z.object({ version: z.literal(1), context: contextSchema,
  kind: z.enum(['contract_review', 'title_review', 'assignment_basis']), request: reviewRequestSchema }).strict();
export type PendingReview = z.infer<typeof pendingReviewSchema>;
export const reviewKey = (user: string, workspace: string) => `wholesale.contract.review:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingReview(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(reviewKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 20000) throw new Error('Invalid saved review');
  const saved = pendingReviewSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Review scope changed');
  return saved;
}
export function preserveReview(storage: Storage, value: PendingReview) {
  const saved = pendingReviewSchema.parse(value), c = saved.context, key = reviewKey(c.userId, c.workspaceId);
  const current = readPendingReview(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another review awaits recovery');
  const raw = JSON.stringify(saved); if (raw.length > 20000) throw new Error('Saved review exceeds recovery limit'); storage.setItem(key, raw);
  if (storage.getItem(key) !== raw) throw new Error('Review recovery unavailable');
  return saved;
}
function clear(storage: Storage, saved: PendingReview) {
  const c = saved.context, key = reviewKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingReview(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved review changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Recovery not cleared');
}
export function clearConfirmedReview(storage: Storage, saved: PendingReview, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: z.number().int(), kind: z.string(), review_id: id,
    sequence: z.number().int(), status: z.enum(['approved', 'withdrawn']), duplicate: z.boolean(), review_recorded: z.literal(true),
    approval_current: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.kind !== saved.kind || receipt.review_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status)
    throw new Error('Review confirmation mismatch');
  clear(storage, saved);
}
export function clearRejectedReview(storage: Storage, saved: PendingReview, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('Earlier review outcome still unknown');
  clear(storage, saved);
}
