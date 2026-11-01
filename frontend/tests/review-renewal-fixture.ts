export const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
export const now = Date.parse('2026-11-01T12:00:00Z');
const expiry = '2026-11-01T12:02:00Z';
export function choice() {
  return { workspace_id: id(2), contract_id: id(6), contract_version: 2, checked_at: new Date(now).toISOString(), execution_authorized: false,
    root_review_id: id(7), kind: 'deadline_resolution', deadline_term: 'closing_deadline', status: 'ready_for_human_review',
    current_review: { review_id: id(7), expires_at: '2026-11-01T11:00:00Z', approval_current: false }, dependencies: [],
    original: { created_at: '2026-11-01T10:00:00Z', expires_at: '2026-11-01T11:00:00Z', findings: {
      term: 'closing_deadline', calendar_date: '2026-11-20', local_time: '17:00:00', time_zone: 'America/Chicago', resolved_instant: '2026-11-20T17:00:00-06:00',
      basis: 'explicit_document_time', source: { term: 'closing_deadline', artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64), locator: 'Closing clause' },
      rationale: 'The signed agreement gives an explicit local closing time.' } },
    candidate: { expected_sequence: 1, previous_review_id: id(7), policy_id: id(10), expected_snapshot_sha256: 'a'.repeat(64), max_expires_at: expiry,
      sources: [{ artifact_id: id(8), source_version: 1, verification_id: id(9), sha256: 'a'.repeat(64), purpose: 'purchase_contract', expires_at: expiry }] } };
}
export function index() {
  const c = choice();
  return { workspace_id: c.workspace_id, contract_id: c.contract_id, contract_version: c.contract_version, checked_at: c.checked_at,
    execution_authorized: false, items: [{ root_review_id: c.root_review_id, kind: c.kind, deadline_term: c.deadline_term, status: c.status, current_review: c.current_review }] };
}
