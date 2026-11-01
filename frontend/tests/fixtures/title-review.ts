import { titleFindingNames, type TitleFindings } from '../../src/lib/acquisition/title-review';
export const titleId = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const titleContext = { userId: titleId(1), workspaceId: titleId(2), leadId: titleId(3), propertyId: titleId(4), offerId: titleId(5), contractId: titleId(6), contractVersion: 2 };
export const titleScope = { workspace_id: titleId(2), contract_id: titleId(6), contract_version: 2 };
export function titleFindings(now = Date.now()): TitleFindings {
  const source = { artifact_id: titleId(8), artifact_version: 2, sha256: 'a'.repeat(64), locator: 'Page 1 of the original report' };
  return { report_as_of: { precision: 'instant', calendar_date: null, instant: new Date(now - 60000).toISOString() }, report_as_of_source: source, report_note: 'Synthetic original report with disclosed limitations.',
    ...Object.fromEntries(titleFindingNames.map(name => [name, { finding: 'satisfactory', note: 'Personally reviewed this synthetic original source.', required_action: null, sources: [source] }])) } as TitleFindings;
}
export function titleChoice(artifact: string | null = titleId(8), now = Date.now()) {
  const stamp = new Date(now).toISOString();
  const resolution = { artifact_id: titleId(8), source_version: 2, verification_id: titleId(9), sha256: 'a'.repeat(64), policy_id: titleId(10), expected_sequence: 0, available_until: new Date(now + 3600000).toISOString() };
  return { ...titleScope, artifact_id: artifact, status: artifact ? 'ready_for_human_review' : 'document_required', resolution: artifact ? resolution : null,
    candidate: artifact ? { ...resolution, max_expires_at: new Date(now + 300000).toISOString(), report_policy: { max_age_seconds: 3600, max_age_days: 0, timezone: 'America/Chicago' } } : null,
    withdrawal: null, current_review: { ...titleScope, kind: 'title_findings', review_id: null, sequence: 0, status: 'not_reviewed', approval_current: false, expires_at: null, checked_at: stamp, execution_authorized: false }, checked_at: stamp, execution_authorized: false };
}
export function titleReference(now = Date.now()) { return { ...titleScope, artifact_id: titleId(8), source_version: 2, reference_type: 'native', link_id: null, status: 'available_for_review', purpose: 'title_report', sha256: 'a'.repeat(64), verification_id: titleId(9), source_created_at: new Date(now - 10000).toISOString(), checked_at: new Date(now).toISOString(), review_approved: false, execution_authorized: false }; }
export function titleHistoryRecord(sequence = 1, status: 'approved' | 'requires_resolution' | 'withdrawn' = 'approved') {
  const now = Date.now(), findings = titleFindings(now - 86400000);
  if (status === 'requires_resolution') findings.ownership = { finding: 'unknown', note: 'The original deed has not been confirmed by counsel.', required_action: 'Obtain the missing original deed from title counsel.', sources: [] };
  return { id: titleId(100 + sequence), ...titleScope, kind: 'title_findings', sequence, status, artifact_id: titleId(8), source_version: 2, actor_id: titleId(1),
    note: 'Original synthetic title decision retained in history.', expires_at: status === 'approved' ? new Date(now - 3600000).toISOString() : null, created_at: new Date(now - 86400000).toISOString(),
    title_original_review_id: status === 'withdrawn' ? titleId(100 + sequence - 1) : null, title_original_status: status === 'withdrawn' ? 'requires_resolution' : null,
    verification_id: titleId(9), sha256: 'a'.repeat(64), personally_reviewed: status !== 'withdrawn', title_findings: status === 'withdrawn' ? null : findings,
    title_sources: status === 'withdrawn' ? null : [{ artifact_id: titleId(8), source_version: 2, verification_id: titleId(9), sha256: 'a'.repeat(64), purpose: 'title_report', expires_at: new Date(now - 3600000).toISOString() }], title_execution_transition_id: titleId(20) };
}
export function titleHistorySummary(sequence = 1, status: 'approved' | 'requires_resolution' | 'withdrawn' = 'approved') {
  const { verification_id, sha256, personally_reviewed, title_findings, title_sources, title_execution_transition_id, ...summary } = titleHistoryRecord(sequence, status);
  void verification_id; void sha256; void personally_reviewed; void title_findings; void title_sources; void title_execution_transition_id;
  return summary;
}
export const titleHistoryEnvelope = { ...titleScope, history_only: true, approval_current: false, execution_authorized: false };
