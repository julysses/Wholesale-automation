// Isolated browser fixture. No fetch, credentials, storage or provider transport.
export class ApiError extends Error { status = 409; }
const offer = {
  offer_id: 'c0000000-0000-4000-8000-000000000001', workspace_id: 'fixture-workspace', lead_id: 'fixture-lead', property_id: 'fixture-property',
  analysis_id: 'fixture-analysis', analysis_revision: 1, latest_analysis_revision: 1, case: 'base', amount: 140000, ceiling: 150000,
  proposal_note: 'Synthetic fixture: repairs need contractor confirmation. Price assumes vacant possession; title and liens remain subject to review.',
  historical_status: 'proposed', sequence: 1, amount_approval_current: false, amount_review_blockers: ['AMOUNT_NOT_APPROVED'],
  available_review_actions: ['amount_approved', 'rejected', 'withdrawn'], checked_at: new Date().toISOString(),
};
const events: { id: string; sequence: number; status: string; note: string; review_notes: Record<string, string> }[] = [];
const replies = new Map<string, unknown>();
const held = { receipt_id: 'fixture-receipt', provider: 'facebook', state: 'review', attempts: 1, reason_code: 'CREDENTIALS_INVALID', blockers: ['CREDENTIALS_INVALID'], updated_at: '2026-10-26T12:00:00.123456+00:00', guidance: 'Ask the integration administrator to verify the Page credential.', next_attempt_at: null, lease_expires_at: null };
const recoveries: unknown[] = [];
const intake = { id: 'fixture-intake', lead_id: 'fixture-source', classification: 'incomplete', created_at: '2026-10-26T12:00:00Z',
  prepared_answers: { answers: { property_address: '123 Fixture Lane', city: 'Dallas', state: 'TX', authority: 'yes', phone: '2145550101' }, missing_fields: ['condition', 'timeline'], reason_codes: ['MISSING_REQUIRED_ANSWERS'] }, normalization_notes: [] };
const identityEvents: { id: string; sequence: number; action: string; review_note: string; created_at: string }[] = [];
const candidate = { lead_id: 'fixture-lead', property_id: 'fixture-property', property_address: '123 Fixture Lane', city: 'Dallas', state: 'TX', county: 'Dallas', parcel_id: 'fixture-parcel', county_unit: null, match_basis: 'EXACT_ADDRESS_TEXT' };
function screening() {
  const repeat = identityEvents.at(-1)?.action === 'repeat_inquiry';
  return { classification: repeat ? 'duplicate' : 'incomplete', policy_version: 'intake-qualification-v1',
    reason_codes: [repeat ? 'REVIEWED_REPEAT_INQUIRY' : 'MISSING_REQUIRED_ANSWERS'], missing_fields: ['condition', 'timeline'],
    canonical_county: identityEvents.length ? 'dallas' : null, canonical_state: identityEvents.length ? 'tx' : null,
    identity_link_current: !!identityEvents.length && identityEvents.at(-1)?.action !== 'revoke',
    ownership_verified: false, outreach_authorized: false, binding_offer: false, contact_permission_granted: false };
}
const assessmentHash = () => identityEvents.length.toString(16).padStart(64, '0');
const assessmentEvents: { id: string; sequence: number; classification: string; evidence_hash: string; assessment: ReturnType<typeof screening>; created_at: string }[] = [];
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let value: unknown;
  if (init?.method === 'POST' && path.endsWith('/assessments')) {
    const body = JSON.parse(String(init.body));
    if (replies.has(body.id)) value = replies.get(body.id);
    else {
      if (body.expected_sequence !== assessmentEvents.length || body.evidence_hash !== assessmentHash()) throw new ApiError('Assessment changed');
      const assessment = screening();
      assessmentEvents.push({ id: body.id, sequence: assessmentEvents.length + 1, classification: assessment.classification, evidence_hash: body.evidence_hash, assessment, created_at: new Date().toISOString() });
      value = { assessment_id: body.id, sequence: assessmentEvents.length, classification: assessment.classification, duplicate: false, outreach_authorized: false }; replies.set(body.id, value);
    }
  } else if (init?.method === 'POST' && path.endsWith('/identity-reviews')) {
    const body = JSON.parse(String(init.body));
    if (replies.has(body.id)) value = replies.get(body.id);
    else {
      if (body.expected_sequence !== identityEvents.length) throw new ApiError('Review changed');
      identityEvents.push({ ...body, sequence: identityEvents.length + 1, created_at: new Date().toISOString() });
      value = { review_id: body.id, sequence: identityEvents.length, duplicate: false, outreach_authorized: false }; replies.set(body.id, value);
    }
  } else if (init?.method === 'POST' && path.endsWith('/recoveries')) {
    const body = JSON.parse(String(init.body));
    if (replies.has(body.id)) value = replies.get(body.id);
    else {
      if (held.state !== 'review' || body.expected_updated_at !== held.updated_at) throw new ApiError('Hold changed');
      recoveries.push({ ...body, cycle: 1, reason_code: held.reason_code, created_at: new Date().toISOString() });
      held.state = 'ready'; held.reason_code = ''; held.blockers = []; held.guidance = 'Awaiting the configured worker; runtime is not independently verified.';
      value = { recovery_id: body.id, receipt_id: held.receipt_id, cycle: 1, duplicate: false, outreach_authorized: false }; replies.set(body.id, value);
    }
  } else if (init?.method === 'POST') {
    if (!path.endsWith('/reviews')) throw new Error('Unexpected fixture mutation');
    const body = JSON.parse(String(init.body));
    if (replies.has(body.id)) value = replies.get(body.id);
    else {
      if (body.expected_sequence !== offer.sequence || !offer.available_review_actions.includes(body.status)) throw new ApiError('Fixture state changed');
      offer.sequence += 1; offer.historical_status = body.status; offer.amount_approval_current = body.status === 'amount_approved';
      offer.amount_review_blockers = offer.amount_approval_current ? [] : ['AMOUNT_NOT_APPROVED'];
      offer.available_review_actions = offer.amount_approval_current ? ['approval_revoked'] : [];
      events.push({ ...body, sequence: offer.sequence }); value = { status: body.status }; replies.set(body.id, value);
    }
  } else if (path.endsWith('/workspaces')) value = [{ id: 'fixture-workspace', name: 'Hilltop — local QA' }];
  else if (path.endsWith('/memberships')) value = [{ workspace_id: 'fixture-workspace', user_id: 'fixture-reviewer', role: 'owner', status: 'active' }];
  else if (path.endsWith('/recoveries')) value = recoveries;
  else if (path.includes('/inquiries/health')) value = { summary: { requires_review: held.state === 'review' ? 1 : 0, retrying: 0, expired_leases: 0, awaiting_worker: held.state === 'ready' ? 1 : 0, leased: 0, completed: 0 }, items: [{ ...held }], next_after: null, checked_at: new Date().toISOString() };
  else if (path.includes('/intakes?')) value = { items: [intake], next_after: null };
  else if (path.endsWith('/qualification-state')) value = { assessment: screening(), evidence_hash: assessmentHash(), sequence: assessmentEvents.length,
    latest_assessment: assessmentEvents.at(-1) ?? null, assessment_current: assessmentEvents.at(-1)?.evidence_hash === assessmentHash() };
  else if (path.includes('/assessments?')) value = [...assessmentEvents].reverse();
  else if (path.includes('/identity-state')) value = { sequence: identityEvents.length, preparation_hash: 'a'.repeat(64),
    target_hash: path.includes('?target=') ? 'b'.repeat(64) : null, target_snapshot: path.includes('?target=') ? candidate : null,
    latest_review: identityEvents.at(-1) ?? null, link_current: !!identityEvents.length && identityEvents.at(-1)?.action !== 'revoke' };
  else if (path.includes('/identity-reviews?')) value = [...identityEvents].reverse();
  else if (path.includes('/candidates?')) value = { items: [candidate], truncated: false };
  else if (path.endsWith('/intakes/fixture-intake')) value = intake;
  else if (path.endsWith('/state')) value = offer;
  else if (path.endsWith('/summary')) value = { id: offer.lead_id, property_id: offer.property_id, property_address: '123 Fixture Lane', city: 'Dallas' };
  else if (path.includes('/leads?')) value = []; // Review-only fixture; scenario entry has separate component tests.
  else if (path.includes('/underwriting/')) value = [{ id: offer.analysis_id, calculation_version: 'acquisition-underwriting-v1',
    acquisition_inputs: { source: 'Synthetic browser fixture; not market data', asking_price: { value: '175000', basis: 'estimate', confidence: 'low' } },
    acquisition_outputs: { cases: Object.fromEntries(['downside', 'base', 'upside'].map((name, i) => [name, { mao: [125000, 150000, 175000][i],
      metrics: { profit: [15000, 40000, 65000][i], profit_on_project_cost: ['0.06', '0.16', '0.26'][i], equity: null }, warnings: ['REPAIR_ESTIMATE_REQUIRES_VERIFICATION'] }])) } }];
  else if (path.includes('/reviews')) value = events;
  else if (path.includes('/offers?')) value = { items: [offer], next_after: null };
  else throw new Error(`Unhandled local fixture route: ${path}`);
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
}
