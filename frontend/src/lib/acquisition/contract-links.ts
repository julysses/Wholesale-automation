import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema } from './contract-documents';
const note = z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'));
export const linkRequest = z.object({ id, source_version: z.number().int().min(1).max(2147483646), artifact_id: id,
  verification_id: id, sha256: z.string().regex(/^[a-f0-9]{64}$/), note }).strict();
export const withdrawalRequest = z.object({ id, reason: note }).strict();
export const pendingLinkSchema = z.discriminatedUnion('kind', [
  z.object({ version: z.literal(1), kind: z.literal('link'), context: contextSchema, request: linkRequest }).strict(),
  z.object({ version: z.literal(1), kind: z.literal('withdraw'), context: contextSchema, linkId: id, request: withdrawalRequest }).strict(),
]).refine(v => v.context.contractVersion > 1 && (v.kind !== 'link' || v.request.source_version < v.context.contractVersion));
export type PendingLink = z.infer<typeof pendingLinkSchema>;
export const linkKey = (user: string, workspace: string) => `wholesale.contract.link:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingLink(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(linkKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 12000) throw new Error('Saved reference exceeds recovery limits.');
  const saved = pendingLinkSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved reference scope changed.');
  return saved;
}
export function preserveLink(storage: Storage, value: PendingLink) {
  const saved = pendingLinkSchema.parse(value), c = saved.context, key = linkKey(c.userId, c.workspaceId);
  const previous = readPendingLink(storage, c.userId, c.workspaceId);
  if (previous && JSON.stringify(previous) !== JSON.stringify(saved)) throw new Error('Another document reference needs recovery.');
  const raw = JSON.stringify(saved); if (raw.length > 12000) throw new Error('Saved reference exceeds recovery limits.');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Reference recovery storage unavailable.'); return saved;
}
function clear(storage: Storage, saved: PendingLink) {
  const c = saved.context, key = linkKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingLink(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved reference changed.');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Reference recovery was not cleared.');
}
export function clearConfirmedLink(storage: Storage, saved: PendingLink, raw: unknown) {
  const common = { workspace_id: id, contract_id: id, contract_version: z.number().int().min(2).max(2147483647), link_id: id,
    duplicate: z.boolean(), execution_authorized: z.literal(false) };
  const c = saved.context;
  if (saved.kind === 'link') {
    const receipt = z.object({ ...common, source_version: z.number().int().min(1), artifact_id: id, review_approved: z.literal(false) }).strict().parse(raw);
    if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion || receipt.link_id !== saved.request.id
      || receipt.source_version !== saved.request.source_version || receipt.artifact_id !== saved.request.artifact_id) throw new Error('Reference confirmation changed.');
  } else {
    const receipt = z.object({ ...common, revocation_id: id }).strict().parse(raw);
    if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion || receipt.link_id !== saved.linkId
      || receipt.revocation_id !== saved.request.id) throw new Error('Withdrawal confirmation changed.');
  }
  clear(storage, saved);
}
export function clearRejectedLink(storage: Storage, saved: PendingLink, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier reference outcome is still unknown.'); clear(storage, saved);
}
