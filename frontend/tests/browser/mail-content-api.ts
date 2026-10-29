// Synthetic QA adapter only: no network, credentials, database or providers.
import { ids, scope, templateRow, destinationRow, prepared, reviewRow, currentState, internalProof, leadRow } from '../fixtures/mail-content';
export { ids };
export class ApiError extends Error { constructor(message: string, public status = 409) { super(message); } }
let fault = 'none', role = 'owner';
export function setFault(value: string) { fault = value; }
export function setRole(value: string) { role = value; }
type Entry = { content: string; body: Record<string, string | number>; row: ReturnType<typeof reviewRow> };
const key = 'synthetic-content-ledger:v1';
function ledger(): Entry[] { const raw = sessionStorage.getItem(key); return raw ? JSON.parse(raw) : [{ content: ids.content, body: {}, row: reviewRow() }]; }
export function count() { return ledger().length; }
export async function apiFetch(path: string, init?: RequestInit) {
  const base = `/api/acquisition/workspaces/${ids.workspace}/campaigns/${ids.campaign}`, root = `${base}/mail-content`;
  if (path.endsWith('/memberships')) return { json: async () => [{ workspace_id: ids.workspace, user_id: ids.user, status: 'active', role }] };
  if (path.startsWith(`${base}/mail-templates?`)) return { json: async () => ({ items: [templateRow], next_after: null }) };
  if (path.startsWith(`${base}/mail-destinations?`)) return { json: async () => ({ items: [destinationRow], next_after: null }) };
  if (path.includes('/leads?')) return { json: async () => [leadRow] };
  if (path === `${root}/prepare` && init?.method === 'POST') { const body = JSON.parse(String(init.body)); return { json: async () => ({ ...prepared(), snapshot: { ...prepared().snapshot, company_name: body.company_name } }) }; }
  if (path.startsWith(root) && path.endsWith('/reviews') && init?.method === 'POST') {
    if (role !== 'owner') throw new ApiError('Synthetic role denied', 403);
    const body = JSON.parse(String(init.body)), content = path.split('/').at(-2)!, rows = ledger(), old = rows.find(r => r.row.id === body.id);
    if (old && (old.content !== content || JSON.stringify(old.body) !== JSON.stringify(body))) throw new ApiError('Synthetic replay mismatch');
    if (!old) {
      if (fault === 'reject') { fault = 'none'; throw new ApiError('Synthetic rejection'); }
      const latest = rows.filter(r => r.content === content).at(-1)?.row;
      if ((latest?.version ?? 0) !== body.expected_version) throw new ApiError('Synthetic version conflict');
      const row = { ...(latest ?? reviewRow()), ...body, ...scope, content_id: content, version: body.expected_version + 1, created_at: new Date().toISOString() };
      rows.push({ content, body, row }); sessionStorage.setItem(key, JSON.stringify(rows));
      if (fault === 'lost') { fault = 'none'; throw new Error('Synthetic saved response lost'); }
    }
    return { json: async () => ({ review_id: body.id, workspace_id: ids.workspace, content_id: content, version: body.expected_version + 1, duplicate: !!old, execution_authorized: false }) };
  }
  if (path.startsWith(`${root}?`)) return { json: async () => ({ items: ledger().map(r => r.row), next_after: null }) };
  if (path.startsWith(`${root}/`)) {
    const content = path.slice(root.length + 1).split('/')[0], latest = ledger().filter(r => r.content === content).at(-1)?.row;
    if (!latest) throw new ApiError('Synthetic content missing', 404);
    if (path.endsWith('/proof') && init?.method === 'POST') {
      if (latest.action !== 'approved') throw new ApiError('Synthetic approval withdrawn');
      return { json: async () => ({ ...internalProof(), content_id: content, content_version: latest.version, review_id: latest.id, preparation_hash: latest.preparation_hash, text: `Hello from ${latest.company_name}. We are interested in 123 Test Street, Dallas TX. Call +12125550100.`, content_valid_until: latest.expires_at }) };
    }
    const current = currentState(); current.content_id = content; current.version = latest.version; current.latest_review = latest; current.status = latest.action === 'approved' ? 'approved' : 'withdrawn'; current.review_current = latest.action === 'approved'; current.preparation.snapshot.company_name = latest.company_name;
    return { json: async () => ({ ...current, preparation: current.review_current ? current.preparation : null }) };
  }
  throw new ApiError('Unknown synthetic route', 404);
}
