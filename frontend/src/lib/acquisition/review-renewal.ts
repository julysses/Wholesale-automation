/** Exact personal-review recovery; saved requests and receipts grant no authority. */
import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema } from './contract-documents';
const kind = z.enum(['deadline_resolution', 'executed_contract', 'title_findings', 'disposition_findings']);
const term = z.enum(['effective', 'inspection_deadline', 'closing_deadline']).nullable();
const version = z.number().int().min(1).max(2147483647);
export const renewalLabels = { deadline_resolution: 'Review contract dates', executed_contract: 'Review the signed agreement',
  title_findings: 'Review title findings', disposition_findings: 'Review the purchase path' } as const;
export const renewalRequestSchema = z.object({ id, expected_version: version,
  expected_sequence: z.number().int().min(1).max(2147483646), kind, deadline_term: term,
  root_review_id: id, previous_review_id: id, policy_id: id, expected_snapshot_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  expires_at: z.string().datetime({ offset: true }), personally_reviewed: z.literal(true),
  note: z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0')),
}).strict().refine(v => v.id !== v.root_review_id && v.id !== v.previous_review_id
  && (v.kind === 'deadline_resolution') === (v.deadline_term !== null));
export const pendingRenewalSchema = z.object({ version: z.literal(1), context: contextSchema, request: renewalRequestSchema }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version);
export type PendingRenewal = z.infer<typeof pendingRenewalSchema>;
export type RenewalRequest = z.infer<typeof renewalRequestSchema>;
export const renewalReceiptSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind, deadline_term: term,
  review_id: id, root_review_id: id, previous_review_id: id, sequence: z.number().int().min(2).max(2147483647), duplicate: z.boolean(),
  review_recorded: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false),
}).strict().refine(v => v.review_id !== v.root_review_id && v.review_id !== v.previous_review_id
  && (v.kind === 'deadline_resolution') === (v.deadline_term !== null));
const MAX_RECOVERY_LENGTH = 20000;
export const renewalKey = (user: string, workspace: string) => `wholesale.contract.renewal:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingRenewal(storage: Pick<Storage, 'getItem'>, user: string, workspace: string): PendingRenewal | null {
  const raw = storage.getItem(renewalKey(user, workspace)); if (raw === null) return null;
  if (raw.length > MAX_RECOVERY_LENGTH) throw new Error('Saved renewal exceeds recovery limits');
  const saved = pendingRenewalSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved renewal scope changed');
  // Expired requests may already have committed. Retain them for exact recovery.
  return saved;
}
export function preserveRenewal(storage: Storage, value: PendingRenewal): PendingRenewal {
  const saved = pendingRenewalSchema.parse(value), c = saved.context, current = readPendingRenewal(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another renewal needs recovery');
  const raw = JSON.stringify(saved), key = renewalKey(c.userId, c.workspaceId);
  if (raw.length > MAX_RECOVERY_LENGTH) throw new Error('Saved renewal exceeds recovery limits');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Renewal recovery unavailable'); return saved;
}
function clear(storage: Storage, value: PendingRenewal) {
  const saved = pendingRenewalSchema.parse(value), c = saved.context, key = renewalKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingRenewal(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved renewal changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Renewal recovery not cleared');
}
export function clearConfirmedRenewal(storage: Storage, value: PendingRenewal, raw: unknown) {
  const saved = pendingRenewalSchema.parse(value), receipt = renewalReceiptSchema.parse(raw), c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.review_id !== r.id || receipt.kind !== r.kind || receipt.deadline_term !== r.deadline_term
    || receipt.root_review_id !== r.root_review_id || receipt.previous_review_id !== r.previous_review_id
    || receipt.sequence !== r.expected_sequence + 1) throw new Error('Renewal receipt mismatch');
  clear(storage, saved);
}
export function clearRejectedRenewal(storage: Storage, saved: PendingRenewal, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier renewal outcome is still unknown'); clear(storage, saved);
}
