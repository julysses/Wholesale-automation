const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const ids = { user: id(1), workspace: id(2) };
export const selected = { offer_id: id(6), lead_id: id(3), property_id: id(4) };
export class ApiError extends Error { rejectedContract = false; }
let lose = false;
export function loseNextReply() { lose = true; }
const ledgerKey = 'contract-draft-local-qa-ledger';
// Explicit local presentation fixture; no production imports or network calls.
if (new URLSearchParams(location.search).get('scanFixture') === 'true' && !sessionStorage.getItem(ledgerKey)) {
  sessionStorage.setItem(ledgerKey, JSON.stringify({ request: {}, row: { id: id(10), workspace_id: ids.workspace,
    lead_id: id(3), deal_name: 'Synthetic document review', acquisition_status: 'draft', acquisition_version: 1,
    acquisition_property_id: id(4), acquisition_owner_relationship_id: id(7), acquisition_offer_id: id(6),
    acquisition_offer_sequence: 2, created_by: ids.user, created_at: new Date().toISOString() } }));
  sessionStorage.setItem('contract-document-local-qa-ledger', JSON.stringify({ created: new Date().toISOString(), request: {
    id: id(11), purpose: 'purchase_contract', expected_sha256: 'a'.repeat(64), expected_byte_size: 123,
    media_type: 'text/plain', retention_policy_id: id(8), provenance_note: 'Synthetic file metadata for status presentation QA.' } }));
}
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
  } else if (path.endsWith('/memberships')) value = [{ workspace_id: ids.workspace, user_id: ids.user, status: 'active', role: 'owner' }];
  else if (path.includes('/reviews/')) {
    if (!ledger || init?.method === 'POST') throw new Error('Read-only synthetic review fixture');
    const kind = path.split('/').at(-1);
    if (!['contract_review', 'title_review', 'assignment_basis'].includes(kind ?? '')) throw new Error('Unknown review kind');
    const approved = kind === 'contract_review';
    value = { workspace_id: ids.workspace, contract_id: ledger.row.id, contract_version: 1, kind,
      sequence: approved ? 1 : 0, review_id: approved ? id(12) : null, status: approved ? 'approved' : 'not_reviewed',
      approval_current: approved, expires_at: approved ? new Date(Date.now() + 60000).toISOString() : null,
      checked_at: new Date().toISOString(), execution_authorized: false };
  }
  else if (path.includes('/documents')) {
    if (!ledger) throw new Error('Save the synthetic draft first');
    const scope = { workspace_id: ids.workspace, contract_id: ledger.row.id, contract_version: 1 };
    const documentsKey = 'contract-document-local-qa-ledger';
    const saved = JSON.parse(sessionStorage.getItem(documentsKey) ?? 'null');
    const now = new Date().toISOString();
    if (init?.method === 'POST' && path.endsWith('/documents')) {
      const request = JSON.parse(init.body as string);
      if (saved && JSON.stringify(saved.request) !== JSON.stringify(request)) throw new Error('Conflicting synthetic document');
      sessionStorage.setItem(documentsKey, JSON.stringify({ request, created: saved?.created ?? now }));
      if (lose) { lose = false; throw new Error('Synthetic document reply lost after commit'); }
      value = { ...scope, artifact_id: request.id, retain_until: '2099-01-01T00:00:00Z', duplicate: !!saved, bytes_verified: false, execution_authorized: false };
    } else if (init?.method === 'POST' && path.includes('/bytes?')) {
      if (!saved || !(init.body instanceof File)) throw new Error('Original synthetic file required');
      const r = saved.request;
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await init.body.arrayBuffer())), b => b.toString(16).padStart(2, '0')).join('');
      if (digest !== r.expected_sha256 || init.body.size !== r.expected_byte_size) throw new Error('Synthetic file changed');
      value = { ...scope, artifact_id: r.id, purpose: r.purpose, sha256: digest, byte_size: r.expected_byte_size, media_type: r.media_type,
        retention_policy_id: r.retention_policy_id, checked_at: now, registry_checked_at: now, retain_until: '2099-01-01T00:00:00Z', status: 'stored_unverified',
        verifier_version: 'acquisition-contract-document-bytes-v1', registry_verifier_version: 'acquisition-contract-document-registry-v1', upload_version: 'acquisition-contract-document-upload-v1',
        write_outcome: 'stored_or_existing', scan_status: 'not_scanned', byte_match_observed: true, verification_persisted: false, legal_review_approved: false, execution_authorized: false };
    } else if (path.includes('/scan-state?')) {
      if (!saved || !path.includes('/'+saved.request.id+'/scan-state?')) throw new Error('Unknown synthetic document');
      value = { ...scope, artifact_id: saved.request.id, purpose: saved.request.purpose, status: 'no_detection_observed',
        quarantined: false, observation_id: id(9), checked_at: now, preview_authorized: false, legal_review_approved: false, execution_authorized: false };
    } else {
      const purpose = new URL(path, 'http://localhost').searchParams.get('purpose');
      const r = saved?.request;
      value = { ...scope, purpose, current_policy: { id: id(8), workspace_id: ids.workspace, purpose, version: 1, retention_seconds: 86400,
        valid_from: '2026-01-01T00:00:00Z', valid_until: '2099-01-01T00:00:00Z' }, checked_at: now, next_after: null, upload_enabled: true, execution_authorized: false,
        items: r && r.purpose === purpose ? [{ ...scope, artifact_id: r.id, purpose, expected_sha256: r.expected_sha256, expected_byte_size: r.expected_byte_size,
          media_type: r.media_type, retention_policy_id: r.retention_policy_id, created_at: saved.created, retain_until: '2099-01-01T00:00:00Z', revoked_at: null,
          checked_at: now, status: 'pending_verification', bytes_verified: false, legal_review_approved: false, execution_authorized: false }] : [] };
    }
  } else if (path.endsWith('/state')) value = { ...selected, workspace_id: ids.workspace, sequence: 2, amount_approval_current: true, amount: 140000 };
  else if (path.endsWith('/summary')) value = { id: id(3), property_id: id(4), property_address: '123 Fixture Street', city: 'Dallas' };
  else if (path.includes('/contracts/drafts/sellers?')) value = { items: [{ id: id(7), workspace_id: ids.workspace, lead_id: id(3), property_id: id(4), owner_id: id(8), relationship: 'reported_owner', verification_status: 'unverified', seller: { display_name: 'Synthetic Seller' } }], next_after: null, ownership_verified: false, execution_authorized: false };
  else if (path.includes('/contracts/drafts?')) value = { items: ledger ? [ledger.row] : [], next_after: null, execution_authorized: false };
  else throw new Error('Unhandled fixture path');
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
}
