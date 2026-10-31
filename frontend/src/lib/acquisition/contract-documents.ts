import { z } from 'zod';
import { date, id } from './mail-content';
import { MAX_BYTES } from './evidence';
export const purposes = { purchase_contract: 'Purchase contract', title_report: 'Title report', seller_disclosure: 'Seller disclosure',
  assignment_agreement: 'Assignment agreement', assignee_disclosure: 'Assignee disclosure', closing_statement: 'Closing statement', supporting_document: 'Other supporting document' } as const;
export const purpose = z.enum(['purchase_contract', 'title_report', 'seller_disclosure', 'assignment_agreement', 'assignee_disclosure', 'closing_statement', 'supporting_document']);
const version = z.number().int().min(1).max(2147483647), hash = z.string().regex(/^[a-f0-9]{64}$/);
const media = z.enum(['application/pdf', 'image/png', 'image/jpeg', 'text/plain']);
const scope = { workspace_id: id, contract_id: id, contract_version: version };
export const contextSchema = z.object({ userId: id, workspaceId: id, leadId: id, propertyId: id, offerId: id, contractId: id, contractVersion: version }).strict();
export type DocumentContext = z.infer<typeof contextSchema>;
const registration = z.object({ id, purpose, expected_sha256: hash, expected_byte_size: z.number().int().min(1).max(MAX_BYTES), media_type: media,
  retention_policy_id: id, provenance_note: z.string().max(2000).refine(v => v.trim().length >= 20 && !v.includes('\0')) }).strict();
export const pendingSchema = z.object({ version: z.literal(1), context: contextSchema, stage: z.enum(['register', 'upload']), registration }).strict();
export type PendingDocument = z.infer<typeof pendingSchema>;
export const documentKey = (user: string, workspace: string) => `wholesale.contract.document:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingDocument(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(documentKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 12000) throw new Error('Saved document is invalid');
  const saved = pendingSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved document scope changed');
  return saved;
}
export function savePendingDocument(storage: Storage, value: PendingDocument, previous: PendingDocument | null) {
  const next = pendingSchema.parse(value), c = next.context, key = documentKey(c.userId, c.workspaceId);
  const current = readPendingDocument(storage, c.userId, c.workspaceId);
  if (JSON.stringify(current) !== JSON.stringify(previous)) throw new Error('Saved request changed');
  const raw = JSON.stringify(next); storage.setItem(key, raw);
  if (storage.getItem(key) !== raw) throw new Error('Saved request unavailable');
  return next;
}
export function clearPendingDocument(storage: Storage, expected: PendingDocument) {
  const c = expected.context, key = documentKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingDocument(storage, c.userId, c.workspaceId)) !== JSON.stringify(expected)) throw new Error('Saved request changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Recovery could not be cleared');
}
function scoped<T extends { workspace_id: string; contract_id: string; contract_version: number }>(value: T, context: DocumentContext): T {
  if (value.workspace_id !== context.workspaceId || value.contract_id !== context.contractId || value.contract_version !== context.contractVersion) throw new Error('Document scope changed');
  return value;
}
function fresh(value: string) { const age = Date.now() - Date.parse(value); if (age < -5000 || age > 30000) throw new Error('Document state is stale'); }
const item = z.object({ ...scope, artifact_id: id, purpose, expected_sha256: hash, expected_byte_size: z.number().int().min(1).max(MAX_BYTES), media_type: media,
  retention_policy_id: id, created_at: date, retain_until: date, revoked_at: date.nullable(), checked_at: date,
  status: z.enum(['pending_verification', 'revoked', 'expired', 'policy_review_required']), bytes_verified: z.literal(false), legal_review_approved: z.literal(false), execution_authorized: z.literal(false) }).strict().refine(v => {
    const created = Date.parse(v.created_at), checked = Date.parse(v.checked_at), expiry = Date.parse(v.retain_until);
    return checked >= created && expiry > created && (v.status === 'revoked' ? v.revoked_at !== null && Date.parse(v.revoked_at) >= created && Date.parse(v.revoked_at) <= checked
      : v.revoked_at === null && (v.status === 'expired' ? expiry <= checked : expiry > checked));
  });
const policy = z.object({ id, workspace_id: id, purpose, version: z.number().int().min(1).max(1e9), retention_seconds: z.number().int().min(1).max(2147483647), valid_from: date, valid_until: date }).strict();
const page = z.object({ ...scope, purpose, current_policy: policy.nullable(), items: z.array(item).max(20), next_after: id.nullable(), checked_at: date,
  execution_authorized: z.literal(false), upload_enabled: z.boolean() }).strict();
export function parseDocuments(raw: unknown, context: DocumentContext, kind: z.infer<typeof purpose>, after: string | null) {
  const value = scoped(page.parse(raw), context); fresh(value.checked_at);
  if (value.purpose !== kind) throw new Error('Document purpose changed');
  const selected = value.current_policy;
  if (selected && (selected.workspace_id !== context.workspaceId || selected.purpose !== kind || Date.parse(selected.valid_from) > Date.parse(value.checked_at)
    || Date.parse(selected.valid_until) <= Math.max(Date.now(), Date.parse(value.checked_at)))) throw new Error('Current retention choice required');
  let previous = after;
  value.items.forEach(row => { scoped(row, context); if (row.purpose !== kind || row.checked_at !== value.checked_at || previous !== null && row.artifact_id <= previous) throw new Error('Invalid document page'); previous = row.artifact_id; });
  if (value.next_after && (value.items.length !== 20 || value.next_after !== previous)) throw new Error('Invalid document cursor');
  return value;
}
export function checkDocumentRegistration(raw: unknown, saved: PendingDocument) {
  const result = scoped(z.object({ ...scope, artifact_id: id, retain_until: date, duplicate: z.boolean(), bytes_verified: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw), saved.context);
  if (result.artifact_id !== saved.registration.id) throw new Error('Registration identity changed');
  return result;
}
const upload = z.object({ ...scope, artifact_id: id, purpose, sha256: hash, byte_size: z.number().int().min(1).max(MAX_BYTES), media_type: media,
  retention_policy_id: id, checked_at: date, registry_checked_at: date, retain_until: date, status: z.literal('stored_unverified'),
  verifier_version: z.literal('acquisition-contract-document-bytes-v1'), registry_verifier_version: z.literal('acquisition-contract-document-registry-v1'),
  upload_version: z.literal('acquisition-contract-document-upload-v1'), write_outcome: z.literal('stored_or_existing'), scan_status: z.literal('not_scanned'),
  byte_match_observed: z.literal(true), verification_persisted: z.literal(false), legal_review_approved: z.literal(false), execution_authorized: z.literal(false) }).strict();
export function checkDocumentUpload(raw: unknown, saved: PendingDocument) {
  const result = scoped(upload.parse(raw), saved.context), r = saved.registration;
  fresh(result.checked_at); fresh(result.registry_checked_at);
  if (result.artifact_id !== r.id || result.purpose !== r.purpose || result.sha256 !== r.expected_sha256 || result.byte_size !== r.expected_byte_size
    || result.media_type !== r.media_type || result.retention_policy_id !== r.retention_policy_id
    || Date.parse(result.retain_until) <= Math.max(Date.now(), Date.parse(result.checked_at), Date.parse(result.registry_checked_at))
    || Date.parse(result.checked_at) - Date.parse(result.registry_checked_at) > 5000) throw new Error('Unconfirmed document upload');
  return result;
}
