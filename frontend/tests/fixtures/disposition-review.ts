import { dispositionCommonNames, dispositionAssignmentNames, type DispositionFindings } from '../../src/lib/acquisition/disposition-review';
export { titleId as dispositionId, titleContext as dispositionContext, titleScope as dispositionScope } from './title-review';
import { titleId as id, titleScope as scope } from './title-review';
export function dispositionFindings(assignment = true): DispositionFindings {
  const finding = () => ({ finding: 'satisfactory' as const, note: 'Personally reviewed this original contract and its requirements.', required_action: null,
    sources: [{ artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64), locator: 'Original executed contract clause 14' }] });
  return { exit_type: assignment ? 'wholesale_assignment' : 'principal_acquisition', ...Object.fromEntries(dispositionCommonNames.map(name => [name, finding()])),
    assignment: assignment ? Object.fromEntries(dispositionAssignmentNames.map(name => [name, finding()])) : null } as DispositionFindings;
}
export function dispositionChoice(assignment = true, now = Date.now()) {
  const stamp = new Date(now).toISOString(), expiry = new Date(now + 300000).toISOString();
  const source = { artifact_id: id(8), source_version: 1, verification_id: id(9), sha256: 'a'.repeat(64), purpose: 'purchase_contract', expires_at: expiry };
  const resolution = { plan_id: id(11), exit_type: assignment ? 'wholesale_assignment' : 'principal_acquisition', policy_id: id(10), execution_transition_id: id(12),
    title_entry_id: id(13), title_review_id: id(14), title_status: 'approved', expected_sequence: 0, available_until: expiry, executed_source: source, legal_source: assignment ? { ...source } : null };
  return { ...scope, status: 'ready_for_human_review', candidate: { ...structuredClone(resolution), max_expires_at: expiry }, resolution,
    withdrawal: null, current_review: { ...scope, kind: 'disposition_findings', review_id: null, sequence: 0, status: 'not_reviewed', approval_current: false, expires_at: null, checked_at: stamp, execution_authorized: false }, checked_at: stamp, execution_authorized: false };
}
export function dispositionHistoryRecord(sequence = 1, status: 'approved' | 'requires_resolution' | 'withdrawn' = 'approved', assignment = true) {
  const now = Date.now(), findings = dispositionFindings(assignment);
  if (status === 'requires_resolution') findings.contractual_interest = { finding: 'unknown', note: 'The original contractual interest needs confirmation.', required_action: 'Obtain counsel review of the original contractual interest.', sources: [] };
  return { id: id(100 + sequence), ...scope, kind: 'disposition_findings', sequence, status, artifact_id: id(8), source_version: 1, actor_id: id(1),
    disposition_plan_id: id(11), disposition_exit_type: findings.exit_type,
    note: 'Original synthetic disposition decision retained in history.', expires_at: status === 'approved' ? new Date(now - 3600000).toISOString() : null, created_at: new Date(now - 86400000).toISOString(),
    disposition_original_review_id: status === 'withdrawn' ? id(100 + sequence - 1) : null, disposition_original_status: status === 'withdrawn' ? 'requires_resolution' : null,
    verification_id: id(9), sha256: 'a'.repeat(64), personally_reviewed: status !== 'withdrawn', disposition_findings: status === 'withdrawn' ? null : findings,
    disposition_sources: status === 'withdrawn' ? null : [{ artifact_id: id(8), source_version: 1, verification_id: id(9), sha256: 'a'.repeat(64), purpose: 'purchase_contract', expires_at: new Date(now - 3600000).toISOString() }],
    disposition_execution_id: id(12), disposition_title_entry_id: id(13), disposition_title_review_id: id(14), disposition_title_status: 'approved' };
}
export function dispositionHistorySummary(sequence = 1, status: 'approved' | 'requires_resolution' | 'withdrawn' = 'approved') {
  const { verification_id, sha256, personally_reviewed, disposition_findings, disposition_sources, disposition_execution_id, disposition_title_entry_id, disposition_title_review_id, disposition_title_status, ...summary } = dispositionHistoryRecord(sequence, status);
  void verification_id; void sha256; void personally_reviewed; void disposition_findings; void disposition_sources; void disposition_execution_id; void disposition_title_entry_id; void disposition_title_review_id; void disposition_title_status;
  return summary;
}
export const dispositionHistoryEnvelope = { ...scope, history_only: true, approval_current: false, execution_authorized: false };
