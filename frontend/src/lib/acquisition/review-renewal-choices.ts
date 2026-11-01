/** Bounded server projections for the existing contract review step. */
import { z } from 'zod';
import { id } from './mail-content';
import { purpose, type DocumentContext } from './contract-documents';
import { resolutionSchema } from './deadline-review';
import { findingsSchema } from './execution-review';
import { titleFindingsSchema } from './title-review';
import { dispositionFindingsSchema } from './disposition-review';
const timestamp = z.string().datetime({ offset: true });
const version = z.number().int().min(1).max(2147483647);
const kind = z.enum(['deadline_resolution', 'executed_contract', 'title_findings', 'disposition_findings']);
const term = z.enum(['effective', 'inspection_deadline', 'closing_deadline']).nullable();
const status = z.enum(['paused', 'contract_unavailable', 'withdrawn_or_superseded', 'history_limit_reached',
  'reviewer_policy_required', 'supporting_review_required', 'evidence_review_required', 'report_review_required',
  'purchase_path_changed', 'legal_evidence_required', 'ready_for_human_review']);
const currentShape = { review_id: id, expires_at: timestamp, approval_current: z.boolean() };
const current = z.object(currentShape).strict();
const summary = z.object({ root_review_id: id, kind, deadline_term: term, status, current_review: current.nullable() }).strict()
  .refine(v => (v.kind === 'deadline_resolution') === (v.deadline_term !== null)
    && (v.status !== 'ready_for_human_review' || v.current_review !== null));
const scope = { workspace_id: id, contract_id: id, contract_version: version, checked_at: timestamp, execution_authorized: z.literal(false) };
const index = z.object({ ...scope, items: z.array(summary).max(6) }).strict().refine(v =>
  new Set(v.items.map(i => i.root_review_id)).size === v.items.length
  && new Set(v.items.map(i => `${i.kind}:${i.deadline_term}`)).size === v.items.length);
const dependency = z.object({ ...currentShape, root_review_id: id, kind, deadline_term: term }).strict()
  .refine(v => (v.kind === 'deadline_resolution') === (v.deadline_term !== null));
const source = z.object({ artifact_id: id, source_version: version, verification_id: id,
  sha256: z.string().regex(/^[a-f0-9]{64}$/), purpose, expires_at: timestamp }).strict();
const candidate = z.object({ ...scope, root_review_id: id, kind, deadline_term: term, status,
  current_review: current.nullable(), dependencies: z.array(dependency).max(3),
  original: z.object({ created_at: timestamp, expires_at: timestamp,
    findings: z.union([resolutionSchema, findingsSchema, titleFindingsSchema, dispositionFindingsSchema]) }).strict(),
  candidate: z.object({ expected_sequence: version.max(2147483646), previous_review_id: id, policy_id: id,
    expected_snapshot_sha256: z.string().regex(/^[a-f0-9]{64}$/), max_expires_at: timestamp,
    sources: z.array(source).min(1).max(64) }).strict().nullable(),
}).strict().superRefine((v, ctx) => {
  const fail = () => ctx.addIssue({ code: 'custom', message: 'Current original review context could not be confirmed.' });
  const originalSchemas = { deadline_resolution: resolutionSchema, executed_contract: findingsSchema,
    title_findings: titleFindingsSchema, disposition_findings: dispositionFindingsSchema };
  if (!originalSchemas[v.kind].safeParse(v.original.findings).success
    || (v.kind === 'deadline_resolution') !== (v.deadline_term !== null)
    || v.kind === 'deadline_resolution' && (!('term' in v.original.findings) || v.original.findings.term !== v.deadline_term)
    || Date.parse(v.original.created_at) > Date.parse(v.checked_at)
    || Date.parse(v.original.expires_at) <= Date.parse(v.original.created_at)
    || (v.status === 'ready_for_human_review') !== (v.candidate !== null)) fail();
  const permitted = { deadline_resolution: [], executed_contract: ['deadline_resolution'], title_findings: ['executed_contract'],
    disposition_findings: ['executed_contract', 'title_findings'] } as Record<string, string[]>;
  if (new Set(v.dependencies.map(d => d.root_review_id)).size !== v.dependencies.length
    || v.dependencies.some(d => d.root_review_id === v.root_review_id || !permitted[v.kind].includes(d.kind))) fail();
  const c = v.candidate;
  if (!c) return;
  if (!v.current_review || c.previous_review_id !== v.current_review.review_id
    || v.dependencies.some(d => !d.approval_current || Date.parse(c.max_expires_at) > Date.parse(d.expires_at))
    || new Set(c.sources.map(s => s.artifact_id)).size !== c.sources.length
    || c.sources.some(s => s.source_version > v.contract_version || Date.parse(c.max_expires_at) > Date.parse(s.expires_at))) fail();
  const dates = v.kind === 'executed_contract' ? findingsSchema.parse(v.original.findings).deadline_reviews ?? [] : [];
  const expected = v.kind === 'deadline_resolution' ? 0 : v.kind === 'executed_contract' ? dates.length : v.kind === 'title_findings' ? 1 : 2;
  if (v.dependencies.length !== expected
    || v.kind === 'disposition_findings' && new Set(v.dependencies.map(d => d.kind)).size !== 2
    || dates.some(d => !v.dependencies.some(s => s.root_review_id === d.review_id && s.deadline_term === d.term))) fail();
});
export type RenewalChoice = z.infer<typeof candidate>;
export type RenewalIndex = z.infer<typeof index>;
function validateContext(v: z.infer<typeof index> | RenewalChoice, context: DocumentContext, now: number) {
  const checked = Date.parse(v.checked_at);
  if (!Number.isFinite(now) || v.workspace_id !== context.workspaceId || v.contract_id !== context.contractId
    || v.contract_version !== context.contractVersion || checked < now - 30000 || checked > now + 5000)
    throw new Error('Refresh the current contract review choices.');
}
function validateCurrent(v: z.infer<typeof current> | null, at: number) {
  if (v?.approval_current && Date.parse(v.expires_at) <= at) throw new Error('Refresh the expired review choices.');
}
export function parseRenewalIndex(raw: unknown, context: DocumentContext, now = Date.now()) {
  const value = index.parse(raw); validateContext(value, context, now);
  value.items.forEach(i => validateCurrent(i.current_review, Math.max(now, Date.parse(value.checked_at)))); return value;
}
export function parseRenewalChoice(raw: unknown, context: DocumentContext, root: string, now = Date.now()) {
  const value = candidate.parse(raw); validateContext(value, context, now);
  if (value.root_review_id !== root) throw new Error('The original review changed.');
  const at = Math.max(now, Date.parse(value.checked_at));
  validateCurrent(value.current_review, at); value.dependencies.forEach(d => validateCurrent(d, at));
  if (value.candidate && Date.parse(value.candidate.max_expires_at) <= at) throw new Error('Refresh the expired review choices.');
  return value;
}
