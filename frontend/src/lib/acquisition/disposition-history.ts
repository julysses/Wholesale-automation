import { z } from 'zod';
import { id } from './mail-content';
import { purpose, type DocumentContext } from './contract-documents';
import { dispositionFindingsSchema, dispositionEntries, dispositionSources } from './disposition-review';
const integer = z.number().int().min(1).max(2147483647);
const timestamp = z.string().datetime({ offset: true });
const summaryShape = { id, workspace_id: id, contract_id: id, contract_version: integer, kind: z.literal('disposition_findings'), sequence: integer,
  status: z.enum(['approved', 'requires_resolution', 'withdrawn']), artifact_id: id, source_version: integer, actor_id: id,
  note: z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0')), expires_at: timestamp.nullable(), created_at: timestamp,
  disposition_plan_id: id, disposition_exit_type: z.enum(['principal_acquisition', 'wholesale_assignment']),
  disposition_original_review_id: id.nullable(), disposition_original_status: z.enum(['approved', 'requires_resolution']).nullable() };
const summary = z.object(summaryShape).strict().refine(row => row.source_version <= row.contract_version
  && (row.status === 'approved' ? row.expires_at !== null && Date.parse(row.expires_at) > Date.parse(row.created_at) : row.expires_at === null)
  && (row.status === 'withdrawn' ? row.disposition_original_review_id !== null && row.disposition_original_review_id !== row.id && row.disposition_original_status !== null && row.sequence > 1 : row.disposition_original_review_id === null && row.disposition_original_status === null));
const source = z.object({ artifact_id: id, source_version: integer, verification_id: id, sha256: z.string().regex(/^[a-f0-9]{64}$/), purpose, expires_at: timestamp }).strict();
const detail = z.object({ ...summaryShape, verification_id: id, sha256: z.string().regex(/^[a-f0-9]{64}$/), personally_reviewed: z.boolean(),
  disposition_findings: dispositionFindingsSchema.nullable(), disposition_sources: z.array(source).max(22).nullable(), disposition_execution_id: id, disposition_title_entry_id: id, disposition_title_review_id: id, disposition_title_status: z.enum(['approved', 'requires_resolution']) }).strict().refine(row => {
  if (!summary.safeParse(Object.fromEntries(Object.keys(summaryShape).map(k => [k, row[k as keyof typeof row]]))).success) return false;
  if (row.status === 'withdrawn') return !row.personally_reviewed && row.disposition_findings === null && row.disposition_sources === null;
  if (!row.personally_reviewed || !row.disposition_findings || !row.disposition_sources?.length) return false;
  if (row.disposition_findings.exit_type !== row.disposition_exit_type) return false;
  const originals = new Map(row.disposition_sources.map(s => [s.artifact_id, s])), contract = originals.get(row.artifact_id);
  if (originals.size !== row.disposition_sources.length || row.disposition_sources.some(s => s.source_version > row.contract_version)
    || !contract || contract.source_version !== row.source_version || contract.verification_id !== row.verification_id || contract.sha256 !== row.sha256 || contract.purpose !== 'purchase_contract') return false;
  if (dispositionSources(row.disposition_findings).some(s => originals.get(s.artifact_id)?.source_version !== s.artifact_version || originals.get(s.artifact_id)?.sha256 !== s.sha256)) return false;
  for (const finding of [row.disposition_findings.contractual_interest, row.disposition_findings.assignment?.assignment_provisions]) {
    if (finding?.finding === 'satisfactory' && !finding.sources.some(s => s.artifact_id === row.artifact_id)) return false;
  }
  return row.status !== 'approved' || row.disposition_title_status === 'approved'
    && dispositionEntries(row.disposition_findings).every(i => i.finding.finding === 'satisfactory')
    && row.disposition_sources.every(s => Date.parse(s.expires_at) >= Date.parse(row.expires_at!));
});
const envelope = { workspace_id: id, contract_id: id, contract_version: integer, history_only: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false) };
const page = z.object({ ...envelope, items: z.array(summary).max(20), next_before: integer.nullable() }).strict();
const single = z.object({ ...envelope, record: detail }).strict();
function scope(value: { workspace_id: string; contract_id: string; contract_version: number }, c: DocumentContext) {
  if (value.workspace_id !== c.workspaceId || value.contract_id !== c.contractId || value.contract_version !== c.contractVersion) throw new Error('Exact original disposition history required');
}
export function parseDispositionHistory(raw: unknown, context: DocumentContext, before: number | null = null, now = Date.now()) {
  const value = page.parse(raw); scope(value, context); let previous = before;
  if (!Number.isFinite(now)) throw new Error('Valid history timestamp required');
  const seen = new Set<string>();
  for (const row of value.items) { scope(row, context);
    if (!Number.isFinite(now) || Date.parse(row.created_at) > now || previous !== null && row.sequence >= previous || seen.has(row.id)) throw new Error('Ordered original disposition decisions required');
    previous = row.sequence; seen.add(row.id);
  }
  if (value.next_before !== null && (value.items.length !== 20 || value.next_before !== previous)) throw new Error('Disposition history cursor changed');
  return value;
}
export function parseDispositionHistoryDetail(raw: unknown, context: DocumentContext, reviewId: string, now = Date.now()) {
  const value = single.parse(raw); scope(value, context); scope(value.record, context);
  if (!Number.isFinite(now) || value.record.id !== reviewId || Date.parse(value.record.created_at) > now) throw new Error('Exact original disposition decision required');
  return value;
}
export type DispositionHistoryRecord = z.infer<typeof detail>;
