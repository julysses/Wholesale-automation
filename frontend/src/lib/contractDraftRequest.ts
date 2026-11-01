import { z } from 'zod';

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const name = z.string().min(1).max(500).refine(value => value === value.trim() && [...value].every(char => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127));
export const contractDraftRequestSchema = z.object({
  id: uuid, offer_id: uuid, offer_sequence: z.number().int().min(1).max(2147483647),
  owner_relationship_id: uuid, name,
}).strict();
const contextSchema = z.object({ userId: uuid, workspaceId: uuid, leadId: uuid, propertyId: uuid }).strict();
const pendingSchema = z.object({
  version: z.literal(1), context: contextSchema, savedAt: z.string().datetime({ offset: true }),
  request: contractDraftRequestSchema,
}).strict();
const receiptSchema = z.object({ deal_id: uuid, version: z.literal(1), status: z.literal('draft'),
  duplicate: z.boolean(), execution_authorized: z.literal(false) }).strict();
export const sellerChoiceSchema = z.object({
  id: uuid, workspace_id: uuid, lead_id: uuid, property_id: uuid, owner_id: uuid,
  relationship: z.enum(['reported_owner', 'reported_representative']), verification_status: z.literal('unverified'),
  seller: z.object({ display_name: z.string().min(1).max(320).refine(value => !!value.trim()) }).strict(),
}).strict();
const sellersPage = z.object({ items: z.array(sellerChoiceSchema).max(50), next_after: uuid.nullable(),
  ownership_verified: z.literal(false), execution_authorized: z.literal(false) }).strict();
export type ContractDraftRequest = z.infer<typeof contractDraftRequestSchema>;
export type PendingContractDraft = z.infer<typeof pendingSchema>;
export type ContractContext = z.infer<typeof contextSchema>;
export type ContractSellerChoice = z.infer<typeof sellerChoiceSchema>;
const key = (userId: string, workspaceId: string) => `wholesale.contract.pending:${uuid.parse(userId)}:${uuid.parse(workspaceId)}`;

export function readContractDraft(storage: Pick<Storage, 'getItem'>, userId: string, workspaceId: string): PendingContractDraft | null {
  const raw = storage.getItem(key(userId, workspaceId));
  if (raw === null) return null;
  if (raw.length > 10000) throw new Error('Saved draft request is invalid.');
  const pending = pendingSchema.parse(JSON.parse(raw));
  if (pending.context.userId !== userId || pending.context.workspaceId !== workspaceId) throw new Error('Saved draft scope changed.');
  return pending;
}

export function preserveContractDraft(storage: Storage, value: PendingContractDraft): PendingContractDraft {
  const pending = pendingSchema.parse(value);
  const storageKey = key(pending.context.userId, pending.context.workspaceId);
  if (storage.getItem(storageKey) !== null) throw new Error('Resolve the existing draft request first.');
  const raw = JSON.stringify(pending);
  storage.setItem(storageKey, raw);
  if (storage.getItem(storageKey) !== raw) throw new Error('Draft request could not be saved in this tab.');
  return pending;
}

export function clearConfirmedContractDraft(storage: Storage, pending: PendingContractDraft, rawReceipt: unknown) {
  const receipt = receiptSchema.parse(rawReceipt);
  const original = pendingSchema.parse(pending);
  if (receipt.deal_id !== original.request.id) throw new Error('Draft receipt does not match the saved request.');
  const stored = readContractDraft(storage, original.context.userId, original.context.workspaceId);
  if (JSON.stringify(stored) !== JSON.stringify(original)) throw new Error('Saved draft changed before confirmation.');
  const storageKey = key(original.context.userId, original.context.workspaceId);
  storage.removeItem(storageKey);
  if (storage.getItem(storageKey) !== null) throw new Error('Draft is saved, but browser recovery could not be cleared.');
  return receipt;
}

export function readContractSellers(raw: unknown, context: ContractContext, after: string | null = null) {
  const page = sellersPage.parse(raw);
  let previous = after;
  for (const row of page.items) {
    if (row.workspace_id !== context.workspaceId || row.lead_id !== context.leadId || row.property_id !== context.propertyId
        || (previous !== null && row.id.toLowerCase() <= previous.toLowerCase())) throw new Error('Seller choices changed scope or order.');
    previous = row.id;
  }
  if (page.next_after !== null && (page.items.length === 0 || page.next_after !== page.items.at(-1)?.id)) throw new Error('Seller page cannot be continued safely.');
  return page;
}

/** Only an explicit rejection of the first attempt settles a never-uncertain request. */
export function clearRejectedContractDraft(storage: Storage, pending: PendingContractDraft, firstAttempt: boolean, rejected: boolean) {
  if (!firstAttempt || !rejected) throw new Error('Uncertain draft must retain its original request.');
  const original = pendingSchema.parse(pending);
  const stored = readContractDraft(storage, original.context.userId, original.context.workspaceId);
  if (JSON.stringify(stored) !== JSON.stringify(original)) throw new Error('Saved draft changed before rejection.');
  const storageKey = key(original.context.userId, original.context.workspaceId);
  storage.removeItem(storageKey);
  if (storage.getItem(storageKey) !== null) throw new Error('Rejected request could not be cleared.');
}

const draftRecord = z.object({
  id: uuid, workspace_id: uuid, lead_id: uuid, deal_name: name,
  acquisition_status: z.enum(['draft', 'pending_signature', 'executed', 'title_review']), acquisition_version: z.number().int().min(1).max(2147483647),
  acquisition_property_id: uuid, acquisition_owner_relationship_id: uuid,
  acquisition_offer_id: uuid, acquisition_offer_sequence: z.number().int().positive(),
  created_by: uuid, created_at: z.string().datetime({ offset: true }),
}).strict();
export function readExistingContractDrafts(raw: unknown, context: ContractContext) {
  const page = z.object({ items: z.array(draftRecord).max(50), next_after: uuid.nullable(), execution_authorized: z.literal(false) }).strict().parse(raw);
  let previous: string | null = null;
  for (const row of page.items) {
    if (row.workspace_id !== context.workspaceId || row.lead_id !== context.leadId
        || row.acquisition_property_id !== context.propertyId || (previous !== null && row.id.toLowerCase() <= previous.toLowerCase())) throw new Error('Draft history changed scope or order.');
    previous = row.id;
  }
  if (page.next_after !== null && (page.items.length === 0 || page.next_after !== previous)) throw new Error('Invalid draft history page.');
  return page;
}
