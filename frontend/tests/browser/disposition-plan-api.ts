import { planState, receipt } from '../fixtures/disposition-plan';
const ledgerKey = 'qa.purchase-path.ledger';
let lose = false, paused = false;
export function loseNextReply() { lose = true; }
export function pause() { paused = true; }
export class ApiError extends Error { rejectedPlan = false; constructor(message: string, public status: number) { super(message); } }
export async function apiFetch(_path: string, init?: RequestInit) {
  const journal = JSON.parse(sessionStorage.getItem(ledgerKey) ?? '[]');
  if (init?.method === 'POST') {
    const request = JSON.parse(init.body as string), existing = journal.find((item: { id: string }) => item.id === request.id);
    if (!existing) { journal.push(request); sessionStorage.setItem(ledgerKey, JSON.stringify(journal)); }
    if (lose) { lose = false; throw new Error('Synthetic lost response after commit'); }
    return { json: async () => ({ ...receipt(request), duplicate: !!existing }) };
  }
  const state = planState(false, paused), latest = journal.at(-1);
  return { json: async () => latest ? { ...state, sequence: journal.length,
    latest: { plan_id: latest.id, sequence: journal.length, status: latest.status, exit_type: latest.exit_type, note: latest.note, original_plan_id: latest.original_plan_id, created_at: state.checked_at },
    withdrawal: latest.status === 'proposed' ? { plan_id: latest.id, exit_type: latest.exit_type, expected_sequence: journal.length } : null } : state };
}
