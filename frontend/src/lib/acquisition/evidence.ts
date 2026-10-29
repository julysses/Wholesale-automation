import { z } from 'zod';
import { date, id, scoped } from './mail-content';
export const MAX_BYTES = 10 * 1024 * 1024;
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const media = z.enum(['application/pdf', 'image/png', 'image/jpeg', 'text/plain']);
const scope = { workspace_id: id, campaign_id: id };
export const registration = z.object({ id, purpose: z.literal('mail_content'), expected_sha256: hash,
  expected_byte_size: z.number().int().min(1).max(MAX_BYTES), media_type: media, retention_policy_id: id,
  provenance_note: z.string().max(2000).refine(v => v.trim().length >= 20 && !v.includes('\0')) }).strict();
export const pendingSchema = z.object({ user_id: id, ...scope, stage: z.enum(['register', 'upload']), registration }).strict();
export type PendingEvidence = z.infer<typeof pendingSchema>;
export type FileChoice = { file: File; hash: string; media: z.infer<typeof media> };
const item = z.object({ ...scope, artifact_id: id, purpose: z.literal('mail_content'), expected_sha256: hash,
  expected_byte_size: z.number().int().min(1).max(MAX_BYTES), media_type: media, retention_policy_id: id,
  created_at: date, retain_until: date, revoked_at: date.nullable(), checked_at: date,
  status: z.enum(['pending_verification', 'revoked', 'expired', 'policy_review_required']),
  bytes_verified: z.literal(false), content_approved: z.literal(false), execution_authorized: z.literal(false) }).strict().refine(v => {
    const checked = Date.parse(v.checked_at), expiry = Date.parse(v.retain_until), created = Date.parse(v.created_at);
    return checked >= created && expiry > created && (v.status === 'revoked'
      ? v.revoked_at !== null && Date.parse(v.revoked_at) >= created && Date.parse(v.revoked_at) <= checked
      : v.revoked_at === null && (v.status === 'expired' ? expiry <= checked : expiry > checked));
  });
const policy = z.object({ id, workspace_id: id, purpose: z.literal('mail_content'), version: z.number().int().min(1).max(1e9),
  retention_seconds: z.number().int().min(1).max(2147483647), valid_from: date, valid_until: date }).strict();
const candidates = z.object({ ...scope, purpose: z.literal('mail_content'), current_policy: policy.nullable(), items: z.array(item).max(20),
  next_after: id.nullable(), checked_at: date, execution_authorized: z.literal(false), upload_enabled: z.boolean() }).strict();
function fresh(value: string) { const age = Date.now() - Date.parse(value); if (age < -5000 || age > 30000) throw new Error('Stale evidence'); }
export function parseCandidates(raw: unknown, workspace: string, campaign: string, after: string | null) {
  const p = scoped(candidates.parse(raw), workspace, campaign); fresh(p.checked_at);
  if (p.current_policy && (p.current_policy.workspace_id !== workspace || Date.parse(p.current_policy.valid_from) > Date.parse(p.checked_at)
    || Date.parse(p.current_policy.valid_until) <= Math.max(Date.now(), Date.parse(p.checked_at)))) throw new Error('Unavailable policy');
  let previous = after;
  p.items.forEach(row => { scoped(row, workspace, campaign); if (row.checked_at !== p.checked_at || previous && row.artifact_id <= previous) throw new Error('Invalid evidence page'); previous = row.artifact_id; });
  if (p.next_after && (p.items.length !== 20 || p.next_after !== previous)) throw new Error('Invalid evidence cursor');
  return p;
}
export async function chooseFile(file: File): Promise<FileChoice> {
  if (file.size < 1 || file.size > MAX_BYTES) throw new Error('Choose a file between 1 byte and 10 MiB.');
  const kind = media.safeParse(file.type);
  if (!kind.success) throw new Error('Choose a PDF, PNG, JPEG or plain-text file.');
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength !== file.size) throw new Error('The file changed. Choose the original file again.');
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return { file, media: kind.data, hash: Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('') };
}
export function matchesFile(choice: FileChoice, pending: PendingEvidence) {
  const r = pending.registration;
  return choice.hash === r.expected_sha256 && choice.file.size === r.expected_byte_size && choice.media === r.media_type;
}
export function checkRegistration(raw: unknown, pending: PendingEvidence) {
  const r = z.object({ artifact_id: id, workspace_id: id, retain_until: date, duplicate: z.boolean(), bytes_verified: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  if (r.artifact_id !== pending.registration.id || r.workspace_id !== pending.workspace_id) throw new Error('Registration mismatch');
  return r; // Historical exact retries may return expired original retention.
}
const upload = z.object({ ...scope, evidence_ref: id, purpose: z.literal('mail_content'), sha256: hash, byte_size: z.number().int().min(1).max(MAX_BYTES), media_type: media,
  checked_at: date, registry_checked_at: date, retain_until: date, retention_policy_id: id,
  status: z.literal('stored_unverified'), verifier_version: z.literal('acquisition-evidence-bytes-v1'), registry_verifier_version: z.literal('acquisition-evidence-registry-v1'),
  upload_version: z.literal('acquisition-evidence-upload-v1'), write_outcome: z.literal('stored_or_existing'), scan_status: z.literal('not_scanned'),
  byte_match_observed: z.literal(true), verification_persisted: z.literal(false), content_approved: z.literal(false), execution_authorized: z.literal(false) }).strict();
export function checkUpload(raw: unknown, pending: PendingEvidence) {
  const r = scoped(upload.parse(raw), pending.workspace_id, pending.campaign_id), expected = pending.registration;
  fresh(r.checked_at); fresh(r.registry_checked_at);
  if (r.evidence_ref !== expected.id || r.sha256 !== expected.expected_sha256 || r.byte_size !== expected.expected_byte_size
    || r.media_type !== expected.media_type || r.retention_policy_id !== expected.retention_policy_id
    || Date.parse(r.retain_until) <= Math.max(Date.now(), Date.parse(r.checked_at), Date.parse(r.registry_checked_at))
    || Date.parse(r.checked_at) - Date.parse(r.registry_checked_at) > 5000) throw new Error('Unconfirmed upload');
  return r;
}
export function retentionLabel(seconds: number) {
  if (seconds % 86400 === 0) return `${seconds / 86400} day${seconds === 86400 ? '' : 's'}`;
  if (seconds % 3600 === 0) return `${seconds / 3600} hour${seconds === 3600 ? '' : 's'}`;
  return `${seconds.toLocaleString()} seconds`;
}
