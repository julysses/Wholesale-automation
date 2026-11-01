import { choice, context } from '../review-renewal-fixture';
const key = 'qa.review-renewal.ledger';
let lose = false;
export function loseNextReply() { lose = true; }
export class ApiError extends Error { rejectedRenewal = false; constructor(message: string, public status: number) { super(message); } }
export async function apiFetch(path: string, init?: RequestInit) {
  if (init?.method === 'POST') {
    const request = JSON.parse(init.body as string), previous = sessionStorage.getItem(key);
    if (previous && previous !== JSON.stringify(request)) throw new Error('Synthetic conflicting request');
    sessionStorage.setItem(key, JSON.stringify(request));
    if (lose) { lose = false; throw new Error('Synthetic lost reply after commit'); }
    return { json: async () => ({ workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2,
      kind: request.kind, deadline_term: request.deadline_term, review_id: request.id, root_review_id: request.root_review_id,
      previous_review_id: request.previous_review_id, sequence: request.expected_sequence + 1, duplicate: !!previous,
      review_recorded: true, approval_current: false, execution_authorized: false }) };
  }
  const c = choice(); c.checked_at = new Date().toISOString(); c.candidate.max_expires_at = new Date(Date.now() + 300000).toISOString(); c.candidate.sources[0].expires_at = c.candidate.max_expires_at;
  if (path.endsWith('/candidate')) return { json: async () => c };
  return { json: async () => ({ workspace_id: c.workspace_id, contract_id: c.contract_id, contract_version: c.contract_version,
    checked_at: c.checked_at, execution_authorized: false, items: [{ root_review_id: c.root_review_id, kind: c.kind,
      deadline_term: c.deadline_term, status: c.status, current_review: c.current_review }] }) };
}
