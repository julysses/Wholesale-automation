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
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let value: unknown;
  if (init?.method === 'POST') {
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
  else if (path.includes('/inquiries/health')) value = { summary: { requires_review: 0, retrying: 0, expired_leases: 0, awaiting_worker: 0, leased: 0, completed: 0 }, items: [], next_after: null, checked_at: new Date().toISOString() };
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
