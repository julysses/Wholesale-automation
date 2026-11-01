import { termNames, type ContractTerms } from '../../src/lib/acquisition/contract-terms';
import type { DocumentContext } from '../../src/lib/acquisition/contract-documents';
export const executionId = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export function executionTerms(artifact: string, now = Date.now()): ContractTerms {
  const instant = (offset: number) => ({ precision: 'instant' as const, calendar_date: null, instant: new Date(now + offset).toISOString() });
  return { purchase_price_cents: 14000000, earnest_money_cents: 100000, assignment_allowed: false,
    assignment_provisions: 'Synthetic assignment prohibition for UI testing only.', effective: instant(-86400000), inspection_deadline: instant(86400000), closing_deadline: instant(864000000),
    sources: termNames.map(term => ({ term, artifact_id: artifact, artifact_version: 1, sha256: 'a'.repeat(64), locator: `Synthetic ${term} clause` })), note: 'Synthetic prepared terms. No actual agreement or legal finding.' };
}
export function executionChoice(context: DocumentContext, artifact: string, terms: ContractTerms, prior?: { id: string; artifact_id: string; verification_id: string; policy_id: string; status: string; expires_at: string | null }, sequence = 0) {
  const checked = new Date().toISOString(), scope = { workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: context.contractVersion };
  const approved = prior?.status === 'approved', current = approved && Date.parse(prior.expires_at ?? '') > Date.now();
  return { ...scope, artifact_id: artifact, status: 'ready_for_human_review', candidate: { artifact_id: artifact, source_version: 1, verification_id: executionId(9), sha256: 'a'.repeat(64), policy_id: executionId(12), expected_sequence: sequence, max_expires_at: new Date(Date.now() + 300000).toISOString() },
    withdrawal: approved ? { review_id: prior.id, artifact_id: prior.artifact_id, source_version: 1, verification_id: prior.verification_id, policy_id: prior.policy_id, expected_sequence: sequence } : null,
    prepared_terms: terms, current_review: { ...scope, kind: 'executed_contract', review_id: prior?.id ?? null, sequence, status: !prior ? 'not_reviewed' : current ? 'approved' : approved ? 'requires_review' : 'withdrawn', approval_current: !!current, expires_at: current ? prior.expires_at : null, checked_at: checked, execution_authorized: false }, checked_at: checked, execution_authorized: false };
}
