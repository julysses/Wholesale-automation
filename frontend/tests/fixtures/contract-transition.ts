import { sigContext, sigId } from './signature-review';
export { sigContext as transitionContext, sigId as transitionId };
export function transitionChoice() {
  return { workspace_id: sigContext.workspaceId, contract_id: sigContext.contractId, contract_version: 2, current_version: 2,
    current_status: 'draft', sequence: 0, status: 'ready_for_human_review',
    candidate: { expected_version: 2, expected_sequence: 0, expected_status: 'draft', target_status: 'pending_signature', signature_review_id: sigId(8), expires_at: new Date(Date.now() + 300000).toISOString() },
    checked_at: new Date().toISOString(), execution_authorized: false };
}
