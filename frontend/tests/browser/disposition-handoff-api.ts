import { transitionChoice, transitionContext as context, transitionId } from '../fixtures/contract-transition';
const ledgerKey = 'qa.disposition-handoff.ledger';
let lose = false;
export function loseNextReply() { lose = true; }
export function hasHandoff() { return sessionStorage.getItem(ledgerKey) !== null; }
export class ApiError extends Error { rejectedTransition = false; constructor(message: string, public status: number) { super(message); } }
export async function apiFetch(path: string, init?: RequestInit) {
  if (init?.method === 'POST') {
    const request = JSON.parse(init.body as string), original = sessionStorage.getItem(ledgerKey);
    if (original && original !== JSON.stringify(request)) throw new Error('Synthetic conflicting command');
    sessionStorage.setItem(ledgerKey, JSON.stringify(request));
    if (lose) { lose = false; throw new Error('Synthetic lost reply after commit'); }
    return { json: async () => ({ workspace_id: context.workspaceId, contract_id: context.contractId,
      contract_version: request.expected_version, request_id: request.id, sequence: 4, previous_status: 'title_review',
      recorded_status: 'disposition_review', duplicate: !!original, transition_recorded: true, execution_authorized: false }) };
  }
  if (!path.includes('/transitions/candidate?')) throw new Error('Unsupported fixture path');
  const choice = transitionChoice();
  return { json: async () => hasHandoff() ? { ...choice, current_status: 'disposition_review', sequence: 4,
    status: 'disposition_review_started', candidate: null } : { ...choice, current_status: 'title_review', sequence: 3,
    candidate: { expected_version: 2, expected_sequence: 3, expected_status: 'title_review', target_status: 'disposition_review',
      disposition_review_id: transitionId(30), plan_id: transitionId(31), exit_type: 'wholesale_assignment',
      title_review_id: transitionId(32), execution_review_id: transitionId(33), expires_at: choice.candidate.expires_at } } };
}
