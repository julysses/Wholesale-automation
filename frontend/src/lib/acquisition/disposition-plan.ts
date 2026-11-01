import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
const version = z.number().int().min(1).max(2147483647);
const sequence = z.number().int().min(0).max(2147483647);
const timestamp = z.string().datetime({ offset: true });
const note = z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'));
export const exitLabels = { principal_acquisition: 'Hilltop purchases the property', wholesale_assignment: 'Propose an assignment' };
const exitType = z.enum(['principal_acquisition', 'wholesale_assignment']);
const status = z.enum(['proposed', 'withdrawn']);
export const planRequestSchema = z.object({ id, expected_version: version, expected_sequence: sequence.max(2147483646),
  status, exit_type: exitType, note, original_plan_id: id.nullable() }).strict().refine(v => v.status === 'proposed'
  ? v.original_plan_id === null : v.original_plan_id !== null && v.original_plan_id !== v.id && v.expected_sequence > 0);
export const pendingPlanSchema = z.object({ version: z.literal(1), context: contextSchema, request: planRequestSchema }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version);
export type PendingPlan = z.infer<typeof pendingPlanSchema>;
export const planKey = (user: string, workspace: string) => `wholesale.contract.purchase-path:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingPlan(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(planKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 30000) throw new Error('Purchase-path recovery exceeds limits');
  const saved = pendingPlanSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Purchase-path recovery scope changed');
  return saved;
}
export function preservePlan(storage: Storage, value: PendingPlan) {
  const saved = pendingPlanSchema.parse(value), c = saved.context, key = planKey(c.userId, c.workspaceId);
  const current = readPendingPlan(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another proposal needs recovery');
  const raw = JSON.stringify(saved); if (raw.length > 30000) throw new Error('Purchase-path recovery exceeds limits');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Purchase-path recovery unavailable'); return saved;
}
function clear(storage: Storage, value: PendingPlan) {
  const saved = pendingPlanSchema.parse(value), c = saved.context, key = planKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingPlan(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved proposal changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Proposal recovery not cleared');
}
export function clearConfirmedPlan(storage: Storage, saved: PendingPlan, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: version, plan_id: id, sequence: sequence.min(1),
    status, exit_type: exitType, original_plan_id: id.nullable(), duplicate: z.boolean(), plan_recorded: z.literal(true),
    disposition_approved: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.plan_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status
    || receipt.exit_type !== r.exit_type || receipt.original_plan_id !== r.original_plan_id) throw new Error('Proposal receipt mismatch');
  clear(storage, saved);
}
export function clearRejectedPlan(storage: Storage, saved: PendingPlan, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier proposal outcome is still unknown'); clear(storage, saved);
}
const latest = z.object({ plan_id: id, sequence: sequence.min(1), status, exit_type: exitType, note,
  original_plan_id: id.nullable(), created_at: timestamp }).strict().refine(v => v.status === 'proposed'
  ? v.original_plan_id === null : v.original_plan_id !== null && v.original_plan_id !== v.plan_id && v.sequence > 1);
const stateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, current_version: version,
  current_status: z.enum(['draft', 'pending_signature', 'executed', 'title_review', 'disposition_review', 'assigned_or_direct_close', 'closed', 'cancelled', 'expired', 'disputed']),
  sequence, readiness: z.enum(['ready_for_planning', 'paused', 'contract_unavailable', 'history_limit_reached']), latest: latest.nullable(),
  withdrawal: z.object({ plan_id: id, exit_type: exitType, expected_sequence: sequence.min(1).max(2147483646) }).strict().nullable(),
  checked_at: timestamp, disposition_approved: z.literal(false), execution_authorized: z.literal(false) }).strict();
export function parsePlanState(raw: unknown, context: DocumentContext, now = Date.now()) {
  const v = stateSchema.parse(raw), w = v.withdrawal, l = v.latest;
  if (v.workspace_id !== context.workspaceId || v.contract_id !== context.contractId || v.contract_version !== context.contractVersion
    || v.current_version < v.contract_version || !Number.isFinite(now) || now - Date.parse(v.checked_at) > 30000 || Date.parse(v.checked_at) - now > 5000
    || (l?.sequence ?? 0) !== v.sequence || l && Date.parse(l.created_at) > Date.parse(v.checked_at)
    || (v.readiness === 'history_limit_reached') !== (v.sequence === 2147483647)
    || v.readiness === 'ready_for_planning' && (v.current_version !== v.contract_version || v.current_status !== 'title_review')
    || w && (!l || l.status !== 'proposed' || w.plan_id !== l.plan_id || w.exit_type !== l.exit_type || w.expected_sequence !== v.sequence)) throw new Error('Fresh, consistent purchase-path state required');
  return v;
}
