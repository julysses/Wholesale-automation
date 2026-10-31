const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const ids = { user: id(1), workspace: id(2) };
export const selected = { offer_id: id(6), lead_id: id(3), property_id: id(4) };
export class ApiError extends Error { rejectedContract = false; }
let lose = false;
export function loseNextReply() { lose = true; }
const ledgerKey = 'contract-draft-local-qa-ledger';
export async function apiFetch(path: string, init?: RequestInit) {
  const ledger = JSON.parse(sessionStorage.getItem(ledgerKey) ?? 'null');
  let value: unknown;
  if (init?.method === 'POST' && path.endsWith('/contracts/drafts')) {
    const request = JSON.parse(init.body as string);
    if (ledger && JSON.stringify(ledger.request) !== JSON.stringify(request)) throw new Error('Conflicting fixture request');
    const row = { id: request.id, workspace_id: ids.workspace, lead_id: id(3), deal_name: request.name, acquisition_status: 'draft', acquisition_version: 1,
      acquisition_property_id: id(4), acquisition_owner_relationship_id: id(7), acquisition_offer_id: id(6), acquisition_offer_sequence: 2, created_by: ids.user, created_at: new Date().toISOString() };
    if (!ledger) sessionStorage.setItem(ledgerKey, JSON.stringify({ request, row }));
    if (lose) { lose = false; throw new Error('Synthetic lost reply after commit'); }
    value = { deal_id: request.id, version: 1, status: 'draft', duplicate: !!ledger, execution_authorized: false };
  } else if (path.endsWith('/state')) value = { ...selected, workspace_id: ids.workspace, sequence: 2, amount_approval_current: true, amount: 140000 };
  else if (path.endsWith('/summary')) value = { id: id(3), property_id: id(4), property_address: '123 Fixture Street', city: 'Dallas' };
  else if (path.includes('/contracts/drafts/sellers?')) value = { items: [{ id: id(7), workspace_id: ids.workspace, lead_id: id(3), property_id: id(4), owner_id: id(8), relationship: 'reported_owner', verification_status: 'unverified', seller: { display_name: 'Synthetic Seller' } }], next_after: null, ownership_verified: false, execution_authorized: false };
  else if (path.includes('/contracts/drafts?')) value = { items: ledger ? [ledger.row] : [], next_after: null, execution_authorized: false };
  else throw new Error('Unhandled fixture path');
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
}
