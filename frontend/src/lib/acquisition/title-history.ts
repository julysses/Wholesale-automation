import { z } from 'zod';
import { id } from './mail-content';
import { purpose, type DocumentContext } from './contract-documents';
import { titleFindingsSchema, titleFindingNames, titleSources } from './title-review';
const integer = z.number().int().min(1).max(2147483647);
const timestamp = z.string().datetime({ offset: true });
const summaryShape = { id, workspace_id: id, contract_id: id, contract_version: integer, kind: z.literal('title_findings'), sequence: integer,
  status: z.enum(['approved', 'requires_resolution', 'withdrawn']), artifact_id: id, source_version: integer, actor_id: id,
  note: z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0')), expires_at: timestamp.nullable(), created_at: timestamp,
  title_original_review_id: id.nullable(), title_original_status: z.enum(['approved', 'requires_resolution']).nullable() };
const summary = z.object(summaryShape).strict().refine(row => row.source_version <= row.contract_version
  && (row.status === 'approved' ? row.expires_at !== null && Date.parse(row.expires_at) > Date.parse(row.created_at) : row.expires_at === null)
  && (row.status === 'withdrawn' ? row.title_original_review_id !== null && row.title_original_review_id !== row.id && row.title_original_status !== null && row.sequence > 1 : row.title_original_review_id === null && row.title_original_status === null));
const source = z.object({ artifact_id: id, source_version: integer, verification_id: id, sha256: z.string().regex(/^[a-f0-9]{64}$/), purpose, expires_at: timestamp }).strict();
const detail = z.object({ ...summaryShape, verification_id: id, sha256: z.string().regex(/^[a-f0-9]{64}$/), personally_reviewed: z.boolean(),
  title_findings: titleFindingsSchema.nullable(), title_sources: z.array(source).max(16).nullable(), title_execution_transition_id: id }).strict().refine(row => {
  if (!summary.safeParse(Object.fromEntries(Object.keys(summaryShape).map(k => [k, row[k as keyof typeof row]]))).success) return false;
  if (row.status === 'withdrawn') return !row.personally_reviewed && row.title_findings === null && row.title_sources === null;
  if (!row.personally_reviewed || !row.title_findings || !row.title_sources?.length) return false;
  const originals = new Map(row.title_sources.map(s => [s.artifact_id, s])), report = originals.get(row.artifact_id);
  if (originals.size !== row.title_sources.length || row.title_sources.some(s => s.source_version > row.contract_version)
    || !report || report.source_version !== row.source_version || report.verification_id !== row.verification_id || report.sha256 !== row.sha256 || report.purpose !== 'title_report') return false;
  if (titleSources(row.title_findings).some(s => originals.get(s.artifact_id)?.source_version !== s.artifact_version || originals.get(s.artifact_id)?.sha256 !== s.sha256)
    || row.title_findings.report_as_of_source && row.title_findings.report_as_of_source.artifact_id !== row.artifact_id) return false;
  return row.status !== 'approved' || row.title_findings.report_as_of.precision !== 'unknown' && titleFindingNames.every(n => row.title_findings![n].finding === 'satisfactory');
});
const envelope = { workspace_id: id, contract_id: id, contract_version: integer, history_only: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false) };
const page = z.object({ ...envelope, items: z.array(summary).max(20), next_before: integer.nullable() }).strict();
const single = z.object({ ...envelope, record: detail }).strict();
function scope(value: { workspace_id: string; contract_id: string; contract_version: number }, c: DocumentContext) {
  if (value.workspace_id !== c.workspaceId || value.contract_id !== c.contractId || value.contract_version !== c.contractVersion) throw new Error('Exact original title history required');
}
export function parseTitleHistory(raw: unknown, context: DocumentContext, before: number | null = null, now = Date.now()) {
  const value = page.parse(raw); scope(value, context); let previous = before;
  const seen = new Set<string>();
  for (const row of value.items) { scope(row, context);
    if (!Number.isFinite(now) || Date.parse(row.created_at) > now || previous !== null && row.sequence >= previous || seen.has(row.id)) throw new Error('Ordered original title decisions required');
    previous = row.sequence; seen.add(row.id);
  }
  if (value.next_before !== null && (value.items.length !== 20 || value.next_before !== previous)) throw new Error('Title history cursor changed');
  return value;
}
export function parseTitleHistoryDetail(raw: unknown, context: DocumentContext, reviewId: string, now = Date.now()) {
  const value = single.parse(raw); scope(value, context); scope(value.record, context);
  if (!Number.isFinite(now) || value.record.id !== reviewId || Date.parse(value.record.created_at) > now) throw new Error('Exact original title decision required');
  return value;
}
export type TitleHistoryRecord = z.infer<typeof detail>;
