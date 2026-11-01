import { titleContext, titleScope, titleId } from './title-review';
export { titleContext as context, titleId as id } from './title-review';
export const proposal = { id: titleId(50), expected_version: 2, expected_sequence: 0, status: 'proposed' as const,
  exit_type: 'principal_acquisition' as const, note: 'Propose a principal purchase for separate review.', original_plan_id: null };
export const pending = { version: 1 as const, context: titleContext, request: proposal };
export function receipt(request = proposal) { return { ...titleScope, contract_version: request.expected_version, plan_id: request.id, sequence: request.expected_sequence + 1, status: request.status,
  exit_type: request.exit_type, original_plan_id: request.original_plan_id, duplicate: true, plan_recorded: true, disposition_approved: false, execution_authorized: false }; }
export function planState(hasPlan = false, paused = false, now = Date.now()) {
  const checked_at = new Date(now).toISOString();
  return { ...titleScope, current_version: 2, current_status: 'title_review', sequence: hasPlan ? 1 : 0, readiness: paused ? 'paused' : 'ready_for_planning',
    latest: hasPlan ? { plan_id: proposal.id, sequence: 1, status: 'proposed', exit_type: proposal.exit_type, note: proposal.note, original_plan_id: null, created_at: checked_at } : null,
    withdrawal: hasPlan ? { plan_id: proposal.id, exit_type: proposal.exit_type, expected_sequence: 1 } : null,
    checked_at, disposition_approved: false, execution_authorized: false };
}
