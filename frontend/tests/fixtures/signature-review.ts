export const sigId = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const sigContext = { userId: sigId(1), workspaceId: sigId(2), contractId: sigId(3), contractVersion: 2, leadId: sigId(4), propertyId: sigId(5), offerId: sigId(6) };
export function signatureChoice(withdrawal = false, held = false) {
  const checked = new Date().toISOString(), expires = new Date(Date.now() + 300000).toISOString();
  return { workspace_id: sigId(2), contract_id: sigId(3), contract_version: 2, status: held ? 'paused' : 'ready_for_human_review',
    candidate: held ? null : { basis_review_id: sigId(8), artifact_id: sigId(9), source_version: 1, sha256: 'a'.repeat(64), reviewed_at: '2020-01-01T00:00:00Z', policy_id: sigId(10), expected_sequence: withdrawal ? 1 : 0, max_expires_at: expires },
    withdrawal: withdrawal ? { review_id: sigId(11), basis_review_id: sigId(12), policy_id: sigId(13), expected_sequence: 1 } : null,
    current_review: { workspace_id: sigId(2), contract_id: sigId(3), contract_version: 2, review_id: withdrawal ? sigId(11) : null, basis_review_id: withdrawal ? sigId(12) : null,
      sequence: withdrawal ? 1 : 0, status: withdrawal ? 'requires_review' : 'not_reviewed', approval_current: false, expires_at: null, checked_at: checked, execution_authorized: false },
    checked_at: checked, execution_authorized: false };
}
