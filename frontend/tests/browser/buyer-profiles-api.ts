// Synthetic browser-only adapter: no hosted API, provider, or database calls.
import type { PendingBuyer } from '../../src/lib/acquisition/buyers';
export class ApiError extends Error { rejectedBuyer = false; status = 503; retryAfterSeconds?: number; }
const workspace = '00000000-0000-4000-8000-000000000002', key = 'synthetic-buyer-browser-ledger';
type Row = { request: PendingBuyer['request']; revision: number };
export function loseNextReply() { sessionStorage.setItem('synthetic-buyer-lose', 'true'); }
export async function apiFetch(path: string, init?: RequestInit) {
  if (!path.startsWith(`/api/acquisition/workspaces/${workspace}/buyers`)) throw new Error('Unexpected synthetic path');
  const ledger: Row[] = JSON.parse(sessionStorage.getItem(key) ?? '[]');
  const projection = { workspace_id: workspace, checked_at: new Date().toISOString(), can_save: true, contact_authorized: false, execution_authorized: false };
  if (init?.method === 'POST') {
    const request = JSON.parse(init.body as string) as PendingBuyer['request'];
    let row = ledger.find(r => r.request.id === request.id); const duplicate = !!row;
    if (row && JSON.stringify(row.request) !== JSON.stringify(request)) throw new Error('Synthetic retry changed');
    if (!row) { row = { request, revision: request.expected_revision + 1 }; ledger.push(row); sessionStorage.setItem(key, JSON.stringify(ledger)); }
    if (sessionStorage.getItem('synthetic-buyer-lose') === 'true') { sessionStorage.removeItem('synthetic-buyer-lose'); throw new Error('Synthetic lost response after commit'); }
    return { json: async () => ({ request_id: request.id, workspace_id: workspace, buyer_id: request.buyer_id, revision: row.revision,
      details: row.request.details, duplicate, profile_recorded: true, buyer_verified: false, contact_authorized: false, execution_authorized: false }) };
  }
  const latest = [...new Map(ledger.map(row => [row.request.buyer_id, row])).values()].sort((a, b) => a.request.buyer_id.localeCompare(b.request.buyer_id));
  const tail = path.split('/buyers')[1];
  if (tail.startsWith('/')) {
    const row = latest.find(v => v.request.buyer_id === tail.slice(1)); if (!row) throw new Error('Synthetic buyer not found');
    return { json: async () => ({ ...projection, buyer_id: row.request.buyer_id, revision: row.revision, details: row.request.details, buyer_verified: false }) };
  }
  return { json: async () => ({ ...projection, items: latest.map(row => ({ buyer_id: row.request.buyer_id, revision: row.revision,
    first_name: row.request.details.first_name, last_name: row.request.details.last_name, company: row.request.details.company,
    active: row.request.details.active, buyer_verified: false })), next_cursor: null }) };
}
