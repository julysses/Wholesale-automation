import { emptyTerms } from '../../src/lib/acquisition/contract-terms';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const ids = { user: id(1), workspace: id(2) };
export const selected = { offer_id: id(6), lead_id: id(3), property_id: id(4) };
export class ApiError extends Error { rejectedContract = false; }
let lose = false;
export function loseNextReply() { lose = true; }
const ledgerKey = 'contract-draft-local-qa-ledger';
// Explicit local presentation fixture; no production imports or network calls.
const linkFixture = new URLSearchParams(location.search).get('linkFixture') === 'true';
const referenceFixture = new URLSearchParams(location.search).get('referenceFixture') === 'true';
if ((linkFixture || referenceFixture || new URLSearchParams(location.search).get('scanFixture') === 'true') && !sessionStorage.getItem(ledgerKey)) {
  sessionStorage.setItem(ledgerKey, JSON.stringify({ request: {}, row: { id: id(10), workspace_id: ids.workspace,
    lead_id: id(3), deal_name: 'Synthetic document review', acquisition_status: 'draft', acquisition_version: referenceFixture || linkFixture ? 2 : 1,
    acquisition_property_id: id(4), acquisition_owner_relationship_id: id(7), acquisition_offer_id: id(6),
    acquisition_offer_sequence: 2, created_by: ids.user, created_at: new Date().toISOString() } }));
  sessionStorage.setItem('contract-document-local-qa-ledger', JSON.stringify({ sourceVersion: 1, created: new Date().toISOString(), request: {
    id: id(11), purpose: 'purchase_contract', expected_sha256: 'a'.repeat(64), expected_byte_size: 123,
    media_type: 'text/plain', retention_policy_id: id(8), provenance_note: 'Synthetic file metadata for status presentation QA.' } }));
}
export async function apiFetch(path: string, init?: RequestInit) {
  const ledger = JSON.parse(sessionStorage.getItem(ledgerKey) ?? 'null');
  const requestedVersion = Number(path.match(/\/versions\/(\d+)/)?.[1] ?? 1);
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
  else if (path.endsWith('/terms') || path.includes('/versions?')) {
    if (!ledger) throw new Error('Save the synthetic draft first');
    const key = 'contract-terms-local-qa-ledger';
    const entries = JSON.parse(sessionStorage.getItem(key) ?? '[]') as { request: Record<string, unknown>; created: string }[];
    if (init?.method === 'POST') {
      const request = JSON.parse(init.body as string);
      const prior = entries.find(entry => entry.request.id === request.id);
      if (prior && JSON.stringify(prior.request) !== JSON.stringify(request)) throw new Error('Synthetic terms retry changed');
      if (!prior) {
        if (request.expected_version !== ledger.row.acquisition_version) throw new Error('Synthetic contract version changed');
        entries.push({ request, created: new Date().toISOString() }); sessionStorage.setItem(key, JSON.stringify(entries));
        ledger.row.acquisition_version += 1; sessionStorage.setItem(ledgerKey, JSON.stringify(ledger));
      }
      if (lose) { lose = false; throw new Error('Synthetic terms reply lost after commit'); }
      value = { request_id: request.id, workspace_id: ids.workspace, contract_id: ledger.row.id, version: request.expected_version + 1,
        status: 'draft', duplicate: !!prior, execution_authorized: false };
    } else {
      const params = new URL(path, 'http://localhost').searchParams;
      const requested = Number(params.get('after') ?? 0) + 1, limit = Number(params.get('limit') ?? 20);
      const last = Math.min(ledger.row.acquisition_version, requested + limit - 1);
      value = { workspace_id: ids.workspace, contract_id: ledger.row.id, execution_authorized: false,
        next_after: last < ledger.row.acquisition_version ? last : null,
        items: Array.from({ length: Math.max(0, last - requested + 1) }, (_, index) => {
          const version = requested + index, entry = entries.find(row => Number(row.request.expected_version) + 1 === version);
          return { id: id(100 + version), workspace_id: ids.workspace, deal_id: ledger.row.id,
            version, status: 'draft', previous_version: version > 1 ? version - 1 : null,
            terms: version === 1 ? null : entry?.request.terms ?? { ...emptyTerms(), note: 'Synthetic initial terms retained for browser preview.' },
            actor_id: ids.user, created_at: entry?.created ?? ledger.row.created_at };
        }) };

    }
  }
  else if (path.includes('/document-links')) {
    if (!ledger || init?.method !== 'POST') throw new Error('Synthetic link write required');
    const key = 'contract-link-local-qa-ledger';
    const entries = JSON.parse(sessionStorage.getItem(key) ?? '[]') as { target: number; request: Record<string, unknown>; withdrawal?: Record<string, unknown> }[];
    const request = JSON.parse(init.body as string);
    const scope = { workspace_id: ids.workspace, contract_id: ledger.row.id, contract_version: requestedVersion };
    if (path.endsWith('/withdrawals')) {
      const linkId = path.split('/document-links/')[1].split('/')[0];
      const linked = entries.find(row => row.target === requestedVersion && row.request.id === linkId);
      if (!linked || linked.withdrawal && JSON.stringify(linked.withdrawal) !== JSON.stringify(request)) throw new Error('Synthetic link withdrawal conflict');
      const duplicate = !!linked.withdrawal; linked.withdrawal = request; sessionStorage.setItem(key, JSON.stringify(entries));
      value = { ...scope, link_id: linkId, revocation_id: request.id, duplicate, execution_authorized: false };
    } else {
      const prior = entries.find(row => row.request.id === request.id);
      if (prior && (prior.target !== requestedVersion || JSON.stringify(prior.request) !== JSON.stringify(request))) throw new Error('Synthetic link retry conflict');
      if (!prior) {
        if (requestedVersion !== ledger.row.acquisition_version || entries.some(row => row.target === requestedVersion && row.request.artifact_id === request.artifact_id)) throw new Error('Synthetic link target conflict');
        entries.push({ target: requestedVersion, request }); sessionStorage.setItem(key, JSON.stringify(entries));
      }
      value = { ...scope, link_id: request.id, source_version: request.source_version, artifact_id: request.artifact_id, duplicate: !!prior, review_approved: false, execution_authorized: false };
    }
    if (lose) { lose = false; throw new Error('Synthetic reference reply lost after commit'); }
  }
  else if (path.includes('/reviews/')) {
    if (!ledger) throw new Error('Save the synthetic draft first');
    const kind = path.split('/reviews/')[1].split('/')[0];
    if (!['contract_review', 'title_review', 'assignment_basis'].includes(kind)) throw new Error('Unknown review kind');
    const scope = { workspace_id: ids.workspace, contract_id: ledger.row.id, contract_version: requestedVersion, kind };
    const key = 'contract-review-local-qa-ledger:'+requestedVersion+':'+kind;
    const entries = JSON.parse(sessionStorage.getItem(key) ?? '[]') as { request: Record<string, unknown>; receipt: Record<string, unknown> }[];
    const last = entries.at(-1), checked = new Date().toISOString();
    const current = last?.request.status === 'approved' && Date.parse(String(last.request.expires_at)) > Date.now();
    const state = { ...scope, sequence: entries.length, review_id: last?.request.id ?? null,
      status: !last ? 'not_reviewed' : last.request.status === 'withdrawn' ? 'withdrawn' : current ? 'approved' : 'requires_review',
      approval_current: current, expires_at: current ? last!.request.expires_at : null, checked_at: checked, execution_authorized: false };
    if (init?.method === 'POST') {
      const request = JSON.parse(init.body as string);
      const prior = entries.find(entry => entry.request.id === request.id);
      if (prior && JSON.stringify(prior.request) !== JSON.stringify(request)) throw new Error('Conflicting synthetic review retry');
      if (!prior && request.expected_sequence !== entries.length) throw new Error('Synthetic review sequence changed');
      const receipt = prior?.receipt ?? { ...scope, review_id: request.id, sequence: entries.length + 1, status: request.status,
        duplicate: false, review_recorded: true, approval_current: false, execution_authorized: false };
      if (!prior) { entries.push({ request, receipt }); sessionStorage.setItem(key, JSON.stringify(entries)); }
      if (lose) { lose = false; throw new Error('Synthetic review reply lost after commit'); }
      value = { ...receipt, duplicate: !!prior };
    } else if (path.endsWith('/candidate')) {
      const artifact = path.split('/documents/')[1]?.split('/')[0];
      const document = JSON.parse(sessionStorage.getItem('contract-document-local-qa-ledger') ?? 'null');
      if (!document || artifact !== document.request.id) throw new Error('Exact synthetic document required');
      value = { ...scope, artifact_id: artifact, purpose: kind === 'title_review' ? 'title_report' : 'purchase_contract',
        status: 'ready_for_human_review', candidate: { artifact_id: artifact, verification_id: id(9), sha256: document.request.expected_sha256,
          policy_id: id(13), expected_sequence: entries.length, max_expires_at: new Date(Date.now()+300000).toISOString() },
        withdrawal: last?.request.status === 'approved' ? { review_id: last.request.id, artifact_id: artifact,
          verification_id: last.request.verification_id, policy_id: last.request.policy_id, expected_sequence: entries.length } : null,
        current_review: state, checked_at: checked, execution_authorized: false };
    } else value = state;
  }
  else if (path.includes('/references')) {
    if (!ledger) throw new Error('Save the synthetic draft first');
    const saved = JSON.parse(sessionStorage.getItem('contract-document-local-qa-ledger') ?? 'null');
    const purpose = new URL(path, 'http://localhost').searchParams.get('purpose');
    const checked = new Date().toISOString();
    const scope = { workspace_id: ids.workspace, contract_id: ledger.row.id, contract_version: requestedVersion };
    const sourceVersion = saved?.sourceVersion ?? 1;
    const links = JSON.parse(sessionStorage.getItem('contract-link-local-qa-ledger') ?? '[]') as { target: number; request: Record<string, unknown>; withdrawal?: unknown }[];
    const linked = links.find(row => row.target === requestedVersion && row.request.artifact_id === saved?.request.id);
    const terms = JSON.parse(sessionStorage.getItem('contract-terms-local-qa-ledger') ?? '[]') as { request: { expected_version: number; terms: { sources: { artifact_id: string }[] } } }[];
    const termSource = referenceFixture || terms.some(row => row.request.expected_version + 1 === requestedVersion && row.request.terms.sources.some(source => source.artifact_id === saved?.request.id));
    value = { ...scope, purpose, checked_at: checked, next_after: null, execution_authorized: false,
      items: saved && saved.request.purpose === purpose && sourceVersion <= requestedVersion && (sourceVersion === requestedVersion || termSource || linked) ? [{ ...scope,
        artifact_id: saved.request.id, source_version: sourceVersion,
        reference_type: sourceVersion === requestedVersion ? 'native' : termSource ? 'term_source' : 'linked', link_id: linked?.request.id ?? null,
        status: linked?.withdrawal ? 'reference_withdrawn' : 'available_for_review', purpose, sha256: saved.request.expected_sha256, verification_id: linked?.withdrawal ? null : id(9),
        source_created_at: saved.created, checked_at: checked, review_approved: false, execution_authorized: false }] : [] };
  }
  else if (path.includes('/documents')) {
    if (!ledger) throw new Error('Save the synthetic draft first');
    const scope = { workspace_id: ids.workspace, contract_id: ledger.row.id, contract_version: requestedVersion };
    const documentsKey = 'contract-document-local-qa-ledger';
    const saved = JSON.parse(sessionStorage.getItem(documentsKey) ?? 'null');
    const now = new Date().toISOString();
    if (init?.method === 'POST' && path.endsWith('/documents')) {
      const request = JSON.parse(init.body as string);
      if (saved && JSON.stringify(saved.request) !== JSON.stringify(request)) throw new Error('Conflicting synthetic document');
      sessionStorage.setItem(documentsKey, JSON.stringify({ request, sourceVersion: requestedVersion, created: saved?.created ?? now }));
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
        items: r && r.purpose === purpose && (saved.sourceVersion ?? 1) === requestedVersion ? [{ ...scope, artifact_id: r.id, purpose, expected_sha256: r.expected_sha256, expected_byte_size: r.expected_byte_size,
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
