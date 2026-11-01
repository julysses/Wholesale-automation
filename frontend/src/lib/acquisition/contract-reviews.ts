import { z } from 'zod';
import { id } from './mail-content';
import type { DocumentContext } from './contract-documents';
export const reviewKinds = { contract_review: 'Purchase contract', title_review: 'Title review', assignment_basis: 'Assignment basis' } as const;
export type ReviewKind = keyof typeof reviewKinds;
export const reviewLabels = { not_reviewed: 'Review not recorded', approved: 'Review current', withdrawn: 'Review withdrawn', requires_review: 'Review needs attention' } as const;
const stamp = z.string().datetime({ offset: true });
const schema = z.object({ workspace_id: id, contract_id: id, contract_version: z.number().int().min(1).max(2147483647),
  kind: z.enum(['contract_review', 'title_review', 'assignment_basis']), sequence: z.number().int().min(0).max(2147483647), review_id: id.nullable(),
  status: z.enum(['not_reviewed', 'approved', 'withdrawn', 'requires_review']), approval_current: z.boolean(),
  expires_at: stamp.nullable(), checked_at: stamp, execution_authorized: z.literal(false) }).strict();
export function parseContractReview(raw: unknown, context: DocumentContext, kind: ReviewKind, now = Date.now()) {
  const value = schema.parse(raw);
  if (value.workspace_id !== context.workspaceId || value.contract_id !== context.contractId || value.contract_version !== context.contractVersion || value.kind !== kind
    || !Number.isFinite(now) || now - Date.parse(value.checked_at) > 30000 || Date.parse(value.checked_at) - now > 5000)
    throw new Error('Current contract review scope required');
  if (value.status === 'not_reviewed' ? value.review_id !== null || value.sequence !== 0 : value.review_id === null || value.sequence === 0)
    throw new Error('Consistent review identity required');
  if (value.approval_current !== (value.status === 'approved')
    || (value.approval_current ? value.expires_at === null || Date.parse(value.expires_at) <= Math.max(now, Date.parse(value.checked_at)) : value.expires_at !== null))
    throw new Error('Consistent review authority required');
  return value;
}
export function reviewIsFresh(value: ReturnType<typeof parseContractReview>, now: number) {
  return now - Date.parse(value.checked_at) <= 30000 && now - Date.parse(value.checked_at) >= -5000
    && (!value.approval_current || value.expires_at !== null && Date.parse(value.expires_at) > now);
}
