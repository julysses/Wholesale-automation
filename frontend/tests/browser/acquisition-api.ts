// Isolated browser API fixture. No fetch, credentials or provider transport.
// The real campaign UI uses tab session storage for pending-request recovery.
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
const campaigns: { id: string; workspace_id: string; name: string; status: string; acquisition_channel: string; acquisition_budget_cents: number; acquisition_currency: string }[] = [];
const campaignLinks: { id: string; workspace_id: string; integration_id: string; external_campaign_id: string; sequence: number; action: string; campaign_id: string | null; ad_account_id: string | null; evidence_ref: string; review_note: string; created_at: string }[] = [];
const sourceCaptures: { id: string; workspace_id: string; source_id: string; link_review_id: string; campaign_id: string; preparation_hash: string; created_at: string }[] = [];
const campaignLinkState = () => {
  const latest = campaignLinks.at(-1) ?? null;
  return { workspace_id: 'fixture-workspace', intake_id: 'fixture-intake', integration_id: '30000000-0000-4000-8000-000000000001', page_id: '100', external_campaign_id: '300', preparation_hash: 'a'.repeat(64),
    sequence: latest?.sequence ?? 0, latest_review: latest, link_current: latest?.action === 'link', internal_campaign_id: latest?.action === 'link' ? latest.campaign_id : null, execution_authorized: false };
};
const held = { receipt_id: 'fixture-receipt', provider: 'facebook', state: 'review', attempts: 1, reason_code: 'CREDENTIALS_INVALID', blockers: ['CREDENTIALS_INVALID'], updated_at: '2026-10-26T12:00:00.123456+00:00', guidance: 'Ask the integration administrator to verify the Page credential.', next_attempt_at: null, lease_expires_at: null };
const recoveries: unknown[] = [];
const intake = { id: 'fixture-intake', lead_id: 'fixture-source', classification: 'incomplete', created_at: '2026-10-26T12:00:00Z',
  prepared_answers: { answers: { property_address: '123 Fixture Lane', city: 'Dallas', state: 'TX', authority: 'yes', phone: '2145550101' }, missing_fields: ['condition', 'timeline'], reason_codes: ['MISSING_REQUIRED_ANSWERS'] }, normalization_notes: [] };
const identityEvents: { id: string; sequence: number; action: string; review_note: string; created_at: string }[] = [];
const candidate = { lead_id: 'fixture-lead', property_id: 'fixture-property', property_address: '123 Fixture Lane', city: 'Dallas', state: 'TX', county: 'Dallas', parcel_id: 'fixture-parcel', county_unit: null, match_basis: 'EXACT_ADDRESS_TEXT' };
const qualifiedFixture = new URLSearchParams(window.location.search).has('qualified');
if (qualifiedFixture) {
  Object.assign(intake.prepared_answers.answers, { condition: 'Needs repairs', timeline: 'Within 90 days', asking_price: '175000' });
  intake.prepared_answers.missing_fields = []; intake.prepared_answers.reason_codes = [];
  candidate.lead_id = '20000000-0000-0000-0000-000000000001';
  identityEvents.push({ id: 'fixture-reviewed-link', sequence: 1, action: 'link_property', review_note: 'Synthetic independently reviewed canonical property', created_at: '2026-10-26T12:30:00Z' });
}
function screening() {
  if (qualifiedFixture) return { classification: 'qualified', policy_version: 'intake-qualification-v1', reason_codes: ['COMPLETE_INTAKE_WITH_REVIEWED_IN_TERRITORY_PROPERTY'], missing_fields: [], canonical_county: 'Dallas', canonical_state: 'TX', identity_link_current: true, target_lead_id: '20000000-0000-0000-0000-000000000001', ownership_verified: false, outreach_authorized: false, binding_offer: false, contact_permission_granted: false };
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
  if (init?.method === 'POST' && path.endsWith('/intakes/fixture-intake/underwriting/scenarios')) {
    const body = JSON.parse(String(init.body));
    if (replies.has(body.id)) value = replies.get(body.id);
    else {
      if (!qualifiedFixture || body.evidence_hash !== assessmentHash()) throw new ApiError('Qualification changed');
      assessmentEvents.push({ id: body.id, sequence: assessmentEvents.length + 1, classification: 'qualified', evidence_hash: body.evidence_hash, assessment: screening(), created_at: new Date().toISOString() });
      value = { binding_offer: false, analysis: { id: body.id, acquisition_revision: 1, acquisition_status: 'incomplete', acquisition_strategy: 'fix_and_flip', acquisition_inputs: body.inputs, acquisition_outputs: null }, calculation: { status: 'incomplete' },
        intake_context: { analysis_id: body.id, intake_id: 'fixture-intake', assessment_id: body.id, has_intake: true, qualification_current: true } }; replies.set(body.id, value);
    }
  } else if (init?.method === 'POST' && path.endsWith('/assessments')) {
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
  } else if (init?.method === 'POST' && path.endsWith('/campaign-link-reviews')) {
    const body = JSON.parse(String(init.body)); const existing = campaignLinks.find(row => row.id === body.id);
    if (!existing) {
      if (body.expected_sequence !== campaignLinks.length || (body.action === 'link' && !campaigns.some(row => row.id === body.campaign_id))) throw new ApiError('Fixture review changed');
      campaignLinks.push({ ...body, workspace_id: 'fixture-workspace', integration_id: '30000000-0000-4000-8000-000000000001', external_campaign_id: '300', sequence: campaignLinks.length + 1, created_at: new Date().toISOString() });
    }
    value = { review_id: body.id, sequence: existing?.sequence ?? campaignLinks.length, duplicate: !!existing, execution_authorized: false };
  } else if (init?.method === 'POST' && path.endsWith('/source-campaign-reviews')) {
    const body = JSON.parse(String(init.body)); const existing = sourceCaptures.find(row => row.id === body.id); const state = campaignLinkState();
    if (!existing) {
      if (!state.link_current || state.latest_review?.id !== body.link_review_id || !state.internal_campaign_id) throw new ApiError('Fixture attribution changed');
      sourceCaptures.push({ id: body.id, workspace_id: 'fixture-workspace', source_id: 'fixture-intake', link_review_id: body.link_review_id, campaign_id: state.internal_campaign_id, preparation_hash: state.preparation_hash, created_at: new Date().toISOString() });
    }
    value = { ...(existing ?? sourceCaptures.at(-1)), duplicate: !!existing, execution_authorized: false };
  } else if (init?.method === 'POST' && path.endsWith('/campaigns')) {
    const body = JSON.parse(String(init.body));
    const saved = campaigns.find(row => row.id === body.id);
    if (saved && (saved.name !== body.name || saved.acquisition_channel !== body.channel || saved.acquisition_budget_cents !== body.budget_cents || saved.acquisition_currency !== body.currency)) throw new ApiError('Conflicting fixture request');
    if (!saved) campaigns.push({ id: body.id, workspace_id: 'fixture-workspace', name: body.name, status: 'draft', acquisition_channel: body.channel, acquisition_budget_cents: body.budget_cents, acquisition_currency: body.currency });
    value = { ...body, workspace_id: 'fixture-workspace', status: 'draft', duplicate: !!saved, execution_authorized: false };
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
  else if (path.endsWith('/campaign-link-state')) value = campaignLinkState();
  else if (path.includes('/campaign-link-reviews?')) {
    const before = Number(new URL(path, 'http://fixture.invalid').searchParams.get('before'));
    value = [...campaignLinks].reverse().filter(row => !before || row.sequence < before).slice(0, 20);
  }
  else if (path.includes('/source-campaign-reviews?')) {
    const state = campaignLinkState(); const current = state.link_current ? state.latest_review!.id : null;
    const after = new URL(path, 'http://fixture.invalid').searchParams.get('after');
    const all = sourceCaptures.map(row => ({ ...row, attribution_current: row.link_review_id === current }));
    const rows = all.filter(row => !after || row.id > after).sort((a, b) => a.id.localeCompare(b.id));
    value = { workspace_id: 'fixture-workspace', source_id: 'fixture-intake', preparation_hash: state.preparation_hash, current_link_review_id: current, current_campaign_id: state.internal_campaign_id,
      current_capture: all.find(row => row.attribution_current) ?? null, items: rows.slice(0, 20), next_after: rows.length > 20 ? rows[19].id : null, execution_authorized: false };
  }
  else if (path.includes('/campaigns?')) {
    const after = new URL(path, 'http://fixture.invalid').searchParams.get('after');
    const rows = campaigns.filter(row => !after || row.id > after).sort((a, b) => a.id.localeCompare(b.id));
    value = { items: rows.slice(0, 20), next_after: rows.length > 20 ? rows[19].id : null };
  }
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
  else if (path.includes('/leads?')) value = [{ lead_id: '20000000-0000-4000-8000-000000000001', property_id: '30000000-0000-4000-8000-000000000001', property_address: '123 Fixture Lane', city: 'Dallas' }];
  else if (path.includes('/source-touches?')) {
    const after = new URL(path, 'http://fixture.invalid').searchParams.get('after');
    value = { workspace_id: 'fixture-workspace', canonical_lead_id: '20000000-0000-4000-8000-000000000001', property_id: '30000000-0000-4000-8000-000000000001',
      items: after ? [{ source_id: '50000000-0000-4000-8000-000000000001', original_lead_id: '60000000-0000-4000-8000-000000000001', association: 'reviewed_repeat_inquiry', identity_review_id: '70000000-0000-4000-8000-000000000001',
        attribution_status: 'campaign_review_not_current', attribution_current: false, current_campaign_id: null,
        captured_attribution: { id: '80000000-0000-4000-8000-000000000001', campaign_id: '90000000-0000-4000-8000-000000000001', link_review_id: 'a0000000-0000-4000-8000-000000000001', created_at: '2026-10-26T12:00:00Z' } }] : [],
      next_after: after ? null : '40000000-0000-4000-8000-000000000001', scanned_count: after ? 1 : 20, excluded_count: after ? 0 : 20,
      checked_at: new Date().toISOString(), count_scope: 'bounded_candidate_page', totals_available: false, ownership_verified: false, contact_permission_granted: false, execution_authorized: false };
  }
  else if (path.includes('/underwriting/scenarios?')) value = [];
  else if (path.includes('/underwriting/')) value = [{ id: offer.analysis_id, calculation_version: 'acquisition-underwriting-v1',
    acquisition_inputs: { source: 'Synthetic browser fixture; not market data', asking_price: { value: '175000', basis: 'estimate', confidence: 'low' } },
    acquisition_outputs: { cases: Object.fromEntries(['downside', 'base', 'upside'].map((name, i) => [name, { mao: [125000, 150000, 175000][i],
      metrics: { profit: [15000, 40000, 65000][i], profit_on_project_cost: ['0.06', '0.16', '0.26'][i], equity: null }, warnings: ['REPAIR_ESTIMATE_REQUIRES_VERIFICATION'] }])) } }];
  else if (path.includes('/reviews')) value = events;
  else if (path.includes('/offers?')) value = { items: [offer], next_after: null };
  else throw new Error(`Unhandled local fixture route: ${path}`);
  return new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
}
