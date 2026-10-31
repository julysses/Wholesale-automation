export const ids = { user: 'synthetic-user', workspace: '11111111-1111-4111-8111-111111111111', campaign: '22222222-2222-4222-8222-222222222222' };
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
let lose = false;
export function loseNextReply() { lose = true; }
export async function apiFetch(path: string, init?: RequestInit) {
  if (!path.startsWith(`/api/acquisition/workspaces/${ids.workspace}`)) throw new Error('Unknown synthetic scope');
  if (path.endsWith('/memberships')) return Response.json([{ workspace_id: ids.workspace, user_id: ids.user, status: 'active', role: 'owner' }]);
  if (path.includes('/offer-forms')) {
    const rows = JSON.parse(sessionStorage.getItem('synthetic-offer-versions') ?? '[]');
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); const existing = rows.find((row: { id: string }) => row.id === body.id);
      if (!existing) { rows.push({ id: body.id, workspace_id: ids.workspace, campaign_id: ids.campaign, acquisition_form_key: body.definition.form_key, acquisition_form_revision: body.expected_revision + 1, acquisition_form_version: body.definition.version, acquisition_form_definition: body.definition, acquisition_definition_hash: 'a'.repeat(64), created_at: new Date().toISOString(), active: false, send_confirmation_sms: false, send_confirmation_email: false }); sessionStorage.setItem('synthetic-offer-versions', JSON.stringify(rows)); }
      if (lose) { lose = false; throw new Error('Synthetic response lost after save'); }
      return Response.json({ id: body.id, workspace_id: ids.workspace, campaign_id: ids.campaign, form_key: body.definition.form_key, revision: body.expected_revision + 1, version: body.definition.version, definition_hash: 'a'.repeat(64), status: 'draft', duplicate: !!existing, public_enabled: false, execution_authorized: false });
    }
    return Response.json({ items: rows.sort((a: { id: string }, b: { id: string }) => a.id.localeCompare(b.id)), next_after: null });
  }
  if (path.includes('/campaigns?')) return Response.json({ items: [{ id: ids.campaign, workspace_id: ids.workspace, name: 'Dallas seller offer requests', status: 'draft', acquisition_channel: 'online_offer', acquisition_budget_cents: 0, acquisition_currency: 'USD' }], next_after: null });
  throw new Error('Unimplemented synthetic route');
}
