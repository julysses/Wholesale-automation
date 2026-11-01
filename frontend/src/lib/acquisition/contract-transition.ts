import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
const version = z.number().int().min(1).max(2147483647);
const sequence = z.number().int().min(0).max(2147483646);
const timestamp = z.string().datetime({ offset: true });
const choiceSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, current_version: version,
  current_status: z.enum(['draft', 'pending_signature']), sequence: sequence.max(2147483647),
  status: z.enum(['version_changed', 'paused', 'awaiting_signature', 'history_requires_review', 'signature_review_required', 'ready_for_human_review']),
  candidate: z.object({ expected_version: version, expected_sequence: sequence, expected_status: z.literal('draft'),
    target_status: z.literal('pending_signature'), signature_review_id: id, expires_at: timestamp }).strict().nullable(),
  checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
export function parseTransitionChoice(raw: unknown, context: DocumentContext, now = Date.now()) {
  const value = choiceSchema.parse(raw), c = value.candidate;
  if (value.workspace_id !== context.workspaceId || value.contract_id !== context.contractId || value.contract_version !== context.contractVersion
    || !Number.isFinite(now) || now - Date.parse(value.checked_at) > 30000 || Date.parse(value.checked_at) - now > 5000
    || value.current_version < value.contract_version || (value.status === 'version_changed') !== (value.current_version !== value.contract_version)
    || (value.status === 'ready_for_human_review') !== (c !== null)
    || value.status === 'awaiting_signature' && (value.current_status !== 'pending_signature' || value.sequence !== 1)
    || c && (c.expected_version !== value.contract_version || c.expected_sequence !== value.sequence || value.sequence !== 0
      || c.expected_status !== value.current_status || Date.parse(c.expires_at) <= Math.max(now, Date.parse(value.checked_at))))
    throw new Error('Fresh exact contract status choice required');
  return value;
}
export const transitionRequestSchema = z.object({ id, expected_version: version, expected_sequence: sequence,
  expected_status: z.literal('draft'), target_status: z.literal('pending_signature'),
  reason: z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0')) }).strict();
export const pendingTransitionSchema = z.object({ version: z.literal(1), context: contextSchema,
  request: transitionRequestSchema }).strict().refine(v => v.request.expected_version === v.context.contractVersion);
export type PendingTransition = z.infer<typeof pendingTransitionSchema>;
export const transitionKey = (user: string, workspace: string) => `wholesale.contract.transition:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingTransition(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(transitionKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 20000) throw new Error('Invalid saved transition');
  const saved = pendingTransitionSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Transition scope changed');
  return saved;
}
export function preserveTransition(storage: Storage, value: PendingTransition) {
  const saved = pendingTransitionSchema.parse(value), c = saved.context, key = transitionKey(c.userId, c.workspaceId);
  const current = readPendingTransition(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another status change awaits recovery');
  const raw = JSON.stringify(saved); if (raw.length > 20000) throw new Error('Saved transition exceeds recovery limit');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Transition recovery unavailable');
  return saved;
}
function clear(storage: Storage, saved: PendingTransition) {
  const c = saved.context, key = transitionKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingTransition(storage, c.userId, c.workspaceId)) !== JSON.stringify(pendingTransitionSchema.parse(saved))) throw new Error('Saved transition changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Recovery not cleared');
}
export function clearConfirmedTransition(storage: Storage, saved: PendingTransition, raw: unknown) {
  const r = z.object({ workspace_id: id, contract_id: id, contract_version: version, request_id: id,
    sequence: z.number().int().min(1).max(2147483647), previous_status: z.literal('draft'), recorded_status: z.literal('pending_signature'),
    duplicate: z.boolean(), transition_recorded: z.literal(true), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, request = saved.request;
  if (r.workspace_id !== c.workspaceId || r.contract_id !== c.contractId || r.contract_version !== c.contractVersion
    || r.request_id !== request.id || r.sequence !== request.expected_sequence + 1
    || r.previous_status !== request.expected_status || r.recorded_status !== request.target_status) throw new Error('Transition confirmation mismatch');
  clear(storage, saved);
}
export function clearRejectedTransition(storage: Storage, saved: PendingTransition, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('Earlier status change remains uncertain');
  clear(storage, saved);
}
