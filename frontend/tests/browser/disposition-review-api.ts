import { dispositionChoice, dispositionScope as scope } from '../fixtures/disposition-review';
import { titleReference } from '../fixtures/title-review';
const ledgerKey = 'qa.disposition-review.ledger';
let lose = false;
export function loseNextReply() { lose = true; }
export class ApiError extends Error { rejectedDisposition = false; constructor(message: string, public status: number) { super(message); } }
export async function apiFetch(path: string, init?: RequestInit) {
  const journal = JSON.parse(sessionStorage.getItem(ledgerKey) ?? '[]');
  if (init?.method === 'POST') {
    const request = JSON.parse(init.body as string), existing = journal.find((item: { id: string }) => item.id === request.id);
    if (!existing) { journal.push(request); sessionStorage.setItem(ledgerKey, JSON.stringify(journal)); }
    if (lose) { lose = false; throw new Error('Synthetic lost response after commit'); }
    return { json: async () => ({ ...scope, kind: 'disposition_findings', review_id: request.id, sequence: request.expected_sequence + 1, status: request.status, duplicate: !!existing, review_recorded: true, approval_current: false, execution_authorized: false }) };
  }
  if (path.includes('/references?')) return { json: async () => ({ ...scope, purpose: new URL(path, 'http://local').searchParams.get('purpose'), items: [], next_after: null, checked_at: new Date().toISOString(), execution_authorized: false }) };
  if (path.includes('/references/')) return { json: async () => ({ ...titleReference(), source_version: 1, reference_type: 'term_source', purpose: 'purchase_contract' }) };
  const value = dispositionChoice(true), latest = journal.at(-1);
  if (!latest) return { json: async () => value };
  const sequence = journal.length;
  return { json: async () => ({ ...value, candidate: { ...value.candidate, expected_sequence: sequence }, resolution: { ...value.resolution, expected_sequence: sequence },
    current_review: { ...value.current_review, review_id: latest.id, sequence, status: latest.status === 'approved' ? 'requires_review' : latest.status },
    withdrawal: latest.status === 'withdrawn' ? null : { review_id: latest.id, plan_id: latest.plan_id, exit_type: latest.findings.exit_type, policy_id: latest.policy_id, expected_sequence: sequence, original_status: latest.status } }) };
}
