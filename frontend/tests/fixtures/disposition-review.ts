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
