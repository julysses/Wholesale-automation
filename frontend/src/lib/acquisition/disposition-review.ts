import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, purpose, type DocumentContext } from './contract-documents';
import { titleSourceSchema } from './title-review';
const timestamp = z.string().datetime({ offset: true });
const version = z.number().int().min(1).max(2147483647), sequence = z.number().int().min(0).max(2147483647);
const note = z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'));
const exit = z.enum(['principal_acquisition', 'wholesale_assignment']);
export const dispositionCommonNames = ['contractual_interest', 'closing_structure', 'remaining_obligations'] as const;
export const dispositionAssignmentNames = ['assignment_provisions', 'legal_basis', 'seller_disclosure_requirements', 'assignee_disclosure_requirements'] as const;
export const dispositionLabels = { contractual_interest: 'Contractual interest', closing_structure: 'Closing structure', remaining_obligations: 'Remaining obligations',
  assignment_provisions: 'Assignment provisions', legal_basis: 'Reviewed legal basis', seller_disclosure_requirements: 'Seller disclosure requirements', assignee_disclosure_requirements: 'Assignee disclosure requirements' };
export const dispositionFindingSchema = z.object({ finding: z.enum(['satisfactory', 'requires_resolution', 'unknown']), note,
  required_action: note.nullable(), sources: z.array(titleSourceSchema).max(3) }).strict().refine(v =>
  (v.finding === 'satisfactory' ? v.sources.length > 0 && v.required_action === null : v.required_action !== null)
  && new Set(v.sources.map(s => JSON.stringify(s))).size === v.sources.length);
const findingsShape = z.object({ exit_type: exit, contractual_interest: dispositionFindingSchema, closing_structure: dispositionFindingSchema,
  remaining_obligations: dispositionFindingSchema, assignment: z.object({ assignment_provisions: dispositionFindingSchema,
    legal_basis: dispositionFindingSchema, seller_disclosure_requirements: dispositionFindingSchema, assignee_disclosure_requirements: dispositionFindingSchema }).strict().nullable() }).strict();
export type DispositionFindings = z.infer<typeof findingsShape>;
export type DispositionFinding = z.infer<typeof dispositionFindingSchema>;
export function dispositionEntries(v: DispositionFindings) {
  return [...dispositionCommonNames.map(name => ({ name, finding: v[name] })),
    ...(v.assignment ? dispositionAssignmentNames.map(name => ({ name, finding: v.assignment![name] })) : [])];
}
export const dispositionSources = (v: DispositionFindings) => dispositionEntries(v).flatMap(item => item.finding.sources);
export const dispositionFindingsSchema = findingsShape.superRefine((v, ctx) => {
  if ((v.exit_type === 'wholesale_assignment') !== (v.assignment !== null)) ctx.addIssue({ code: 'custom', message: 'Findings must match the proposed exit.' });
  const originals = new Map<string, string>();
  for (const source of dispositionSources(v)) {
    const identity = `${source.artifact_version}:${source.sha256}`;
    if (originals.has(source.artifact_id) && originals.get(source.artifact_id) !== identity) ctx.addIssue({ code: 'custom', message: 'Original source identities conflict.' });
    originals.set(source.artifact_id, identity);
  }
});
export const dispositionRequestSchema = z.object({ id, expected_version: version, expected_sequence: sequence.max(2147483646),
  status: z.enum(['approved', 'requires_resolution', 'withdrawn']), plan_id: id, original_review_id: id.nullable(), policy_id: id,
  expires_at: timestamp.nullable(), personally_reviewed: z.boolean(), note, findings: dispositionFindingsSchema.nullable() }).strict().refine(v => {
    if (v.status === 'withdrawn') return v.expected_sequence > 0 && v.original_review_id !== null && v.original_review_id !== v.id
      && !v.personally_reviewed && v.expires_at === null && v.findings === null;
    if (v.original_review_id !== null || !v.personally_reviewed || !v.findings || dispositionSources(v.findings).some(s => s.artifact_version > v.expected_version)) return false;
    return v.status === 'approved' ? v.expires_at !== null && dispositionEntries(v.findings).every(i => i.finding.finding === 'satisfactory') : v.expires_at === null;
  });
export const pendingDispositionSchema = z.object({ version: z.literal(1), context: contextSchema, request: dispositionRequestSchema }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version);
export type PendingDisposition = z.infer<typeof pendingDispositionSchema>;
export const dispositionKey = (user: string, workspace: string) => `wholesale.contract.disposition:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingDisposition(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(dispositionKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 100000) throw new Error('Saved disposition review exceeds recovery limits');
  const saved = pendingDispositionSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved disposition review scope changed');
  return saved;
}
export function preserveDisposition(storage: Storage, value: PendingDisposition) {
  const saved = pendingDispositionSchema.parse(value), c = saved.context, key = dispositionKey(c.userId, c.workspaceId);
  const current = readPendingDisposition(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another disposition review needs recovery');
  const raw = JSON.stringify(saved); if (raw.length > 100000) throw new Error('Saved disposition review exceeds recovery limits');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Disposition recovery unavailable'); return saved;
}
function clear(storage: Storage, value: PendingDisposition) {
  const saved = pendingDispositionSchema.parse(value), c = saved.context, key = dispositionKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingDisposition(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved disposition review changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Disposition recovery not cleared');
}
export function clearConfirmedDisposition(storage: Storage, saved: PendingDisposition, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('disposition_findings'),
    review_id: id, sequence: sequence.min(1), status: z.enum(['approved', 'requires_resolution', 'withdrawn']), duplicate: z.boolean(),
    review_recorded: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.review_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status) throw new Error('Disposition receipt mismatch');
  clear(storage, saved);
}
export function clearRejectedDisposition(storage: Storage, saved: PendingDisposition, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier disposition outcome is still unknown'); clear(storage, saved);
}
const stateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('disposition_findings'),
  review_id: id.nullable(), sequence, status: z.enum(['not_reviewed', 'approved', 'requires_resolution', 'withdrawn', 'requires_review']),
  approval_current: z.boolean(), expires_at: timestamp.nullable(), checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
const source = z.object({ artifact_id: id, source_version: version, verification_id: id, sha256: z.string().regex(/^[0-9a-f]{64}$/), purpose, expires_at: timestamp }).strict();
const resolutionChoice = z.object({ plan_id: id, exit_type: exit, policy_id: id, execution_transition_id: id, title_entry_id: id,
  title_review_id: id, title_status: z.enum(['approved', 'requires_resolution']), expected_sequence: sequence.max(2147483646),
  available_until: timestamp, executed_source: source, legal_source: source.nullable() }).strict();
const candidateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version,
  status: z.enum(['paused', 'contract_unavailable', 'history_limit_reached', 'proposal_required', 'title_findings_required', 'reviewer_policy_required',
    'evidence_review_required', 'execution_review_required', 'title_review_required', 'legal_evidence_required', 'ready_for_human_review']),
  candidate: resolutionChoice.extend({ max_expires_at: timestamp }).strict().nullable(), resolution: resolutionChoice.nullable(),
  withdrawal: z.object({ review_id: id, plan_id: id, exit_type: exit, policy_id: id, expected_sequence: sequence.min(1).max(2147483646),
    original_status: z.enum(['approved', 'requires_resolution']) }).strict().nullable(), current_review: stateSchema, checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
export function parseDispositionCandidate(raw: unknown, context: DocumentContext, now = Date.now()) {
  const value = candidateSchema.parse(raw), current = value.current_review;
  for (const item of [value, current]) if (item.workspace_id !== context.workspaceId || item.contract_id !== context.contractId || item.contract_version !== context.contractVersion
    || !Number.isFinite(now) || now - Date.parse(item.checked_at) > 30000 || Date.parse(item.checked_at) - now > 5000) throw new Error('Fresh disposition context required');
  const checked = Date.parse(value.checked_at), fresh = Math.max(now, checked);
  if (value.checked_at !== current.checked_at
    || (current.status === 'not_reviewed' ? current.review_id !== null || current.sequence !== 0 : current.review_id === null || current.sequence === 0)
    || current.approval_current !== (current.status === 'approved')
    || (current.approval_current ? current.expires_at === null || Date.parse(current.expires_at) <= fresh : current.expires_at !== null)) throw new Error('Consistent disposition state required');
  const choice = value.candidate, resolution = value.resolution, withdrawal = value.withdrawal;
  if ((value.status === 'ready_for_human_review') !== (choice !== null)
    || ['ready_for_human_review', 'execution_review_required', 'title_review_required', 'legal_evidence_required'].includes(value.status) !== (resolution !== null)) throw new Error('Consistent disposition choices required');
  if (value.status === 'history_limit_reached' && (current.sequence !== 2147483647 || withdrawal !== null)) throw new Error('Full history cannot add another decision');
  if (value.status === 'legal_evidence_required' && (!resolution || resolution.exit_type !== 'wholesale_assignment' || resolution.legal_source !== null)) throw new Error('Consistent assignment evidence hold required');
  if (resolution) {
    const until = Date.parse(resolution.available_until), root = resolution.executed_source, legal = resolution.legal_source;
    if (resolution.expected_sequence !== current.sequence || until <= fresh || until - checked > 86400000 || root.purpose !== 'purchase_contract'
      || until > Date.parse(root.expires_at) || resolution.exit_type === 'principal_acquisition' && legal !== null) throw new Error('Bounded original disposition choice required');
    for (const s of [root, legal]) if (s && (s.source_version > context.contractVersion || Date.parse(s.expires_at) <= fresh)) throw new Error('Current original source required');
    if (legal && legal.artifact_id === root.artifact_id && JSON.stringify(legal) !== JSON.stringify(root)) throw new Error('Original source identity changed');
  }
  if (choice && (!resolution || Object.entries(resolution).some(([key, v]) => JSON.stringify(choice[key as keyof typeof resolution]) !== JSON.stringify(v))
    || choice.title_status !== 'approved' || Date.parse(choice.max_expires_at) <= fresh || Date.parse(choice.max_expires_at) > Date.parse(choice.available_until)
    || choice.exit_type === 'wholesale_assignment' && (!choice.legal_source || Date.parse(choice.max_expires_at) > Date.parse(choice.legal_source.expires_at)))) throw new Error('Approval context or expiry changed');
  if (withdrawal && (withdrawal.review_id !== current.review_id || withdrawal.expected_sequence !== current.sequence
    || !['approved', 'requires_review', 'requires_resolution'].includes(current.status)
    || withdrawal.original_status !== (current.status === 'requires_resolution' ? 'requires_resolution' : 'approved'))) throw new Error('Original disposition withdrawal required');
  return value;
}
export type DispositionChoices = ReturnType<typeof parseDispositionCandidate>;
