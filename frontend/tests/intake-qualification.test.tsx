import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IntakeQualification } from '../src/components/acquisition/IntakeQualification';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), hash: 'a'.repeat(64), fail: false, saved: false, classification: 'qualified', historical: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 409; } }));
const assessment = { classification: 'qualified', reason_codes: ['COMPLETE_INTAKE_WITH_REVIEWED_IN_TERRITORY_PROPERTY'], missing_fields: [], policy_version: 'intake-qualification-v1', canonical_county: 'dallas', canonical_state: 'tx', identity_link_current: true, target_lead_id: '20000000-0000-0000-0000-000000000001', ownership_verified: false, outreach_authorized: false, binding_offer: false, contact_permission_granted: false };
const saved = { id: 'saved', sequence: 1, classification: 'qualified', created_at: '2026-10-26', assessment };
beforeEach(() => {
  mock.fetch.mockReset(); mock.post.mockReset(); mock.hash = 'a'.repeat(64); mock.fail = false; mock.saved = false; mock.classification = 'qualified'; mock.historical = false;
  mock.post.mockImplementation(async (init: RequestInit) => { const body = JSON.parse(init.body as string); mock.saved = true; return { assessment_id: body.id, sequence: body.expected_sequence+1, classification: 'qualified', duplicate: false, outreach_authorized: false }; });
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (mock.fail) throw new Error('private detail');
    return { json: async () => init?.method === 'POST' ? mock.post(init) : path.includes('/assessments?') ? mock.historical ? [saved] : []
      : { assessment: { ...assessment, classification: mock.classification }, evidence_hash: mock.hash, sequence: mock.saved ? 1 : 0, latest_assessment: mock.saved || mock.historical ? saved : null, assessment_current: mock.saved } };
  });
});
function view(revision = 0, locked = false, client = new QueryClient({ defaultOptions: { queries: { retry: false } } }), onPending = vi.fn()) {
  return { client, onPending, node: <QueryClientProvider client={client}><IntakeQualification userId="user" workspace="w" intake="intake" revision={revision} locked={locked} onPending={onPending} /></QueryClientProvider> };
}
it('distinguishes current screening from stale qualified history', async () => {
  mock.classification = 'requires_human_review'; mock.historical = true; render(view().node);
  expect(await screen.findByText('requires human review')).toBeVisible();
  expect(screen.getByText(/Saved assessment is stale/)).toBeVisible(); expect(screen.getByText(/Version 1 · qualified/)).toBeVisible();
});
it('saves only the server evidence hash and sequence and then refreshes validity', async () => {
  render(view().node); await screen.findByText('qualified'); fireEvent.click(screen.getByRole('button', { name: 'Save assessment snapshot' }));
  await screen.findByText(/Assessment snapshot saved/); expect(JSON.parse(mock.post.mock.calls[0][0].body)).toEqual({ id: expect.any(String), expected_sequence: 0, evidence_hash: 'a'.repeat(64) });
  await screen.findByText('Latest saved assessment matches current evidence.'); expect(screen.getByRole('button', { name: 'Save assessment snapshot' })).toBeDisabled();
});
it('rejects fresh hash changes before writing', async () => {
  render(view().node); await screen.findByText('qualified'); mock.hash = 'b'.repeat(64);
  fireEvent.click(screen.getByRole('button', { name: 'Save assessment snapshot' })); await screen.findByText(/Assessment changed or access/); expect(mock.post).not.toHaveBeenCalled();
});
it('retains the exact unknown request and signals that the parent review must remain open', async () => {
  mock.post.mockRejectedValueOnce(new Error('reply lost')); const initial = view(); render(initial.node); await screen.findByText('qualified');
  fireEvent.click(screen.getByRole('button', { name: 'Save assessment snapshot' })); await screen.findByRole('button', { name: 'Retry exact assessment request' });
  await waitFor(() => expect(initial.onPending).toHaveBeenLastCalledWith(true)); mock.hash = 'c'.repeat(64);
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact assessment request' })); await screen.findByText(/Assessment snapshot saved/);
  expect(mock.post.mock.calls[0][0].body).toBe(mock.post.mock.calls[1][0].body); await waitFor(() => expect(initial.onPending).toHaveBeenLastCalledWith(false));
});
it('hides stale current results after access failure', async () => {
  render(view().node); await screen.findByText('qualified'); mock.fail = true; fireEvent.click(screen.getByRole('button', { name: 'Refresh qualification' }));
  await screen.findByText(/Current qualification unavailable/); expect(screen.queryByText('qualified')).not.toBeInTheDocument(); expect(screen.queryByText('private detail')).not.toBeInTheDocument();
});
it('refreshes after identity revision and blocks writes while identity is pending', async () => {
  const initial = view(); const result = render(initial.node); await screen.findByText('qualified'); mock.classification = 'incomplete';
  result.rerender(view(1, true, initial.client, initial.onPending).node); await screen.findByText('incomplete');
  expect(screen.getByRole('button', { name: 'Save assessment snapshot' })).toBeDisabled();
});

it('fails closed on a response that incorrectly authorizes outreach', async () => {
  mock.fetch.mockImplementation(async (path: string) => ({ json: async () => path.includes('/assessments?') ? [] : {
    assessment: { ...assessment, outreach_authorized: true }, evidence_hash: 'a'.repeat(64), sequence: 0, latest_assessment: null, assessment_current: false,
  } }));
  render(view().node); await screen.findByText(/Current qualification unavailable/);
  expect(screen.getByRole('button', { name: 'Save assessment snapshot' })).toBeDisabled();
});

it('preserves an unresolved underwriting request across qualification refresh and blocks snapshot changes', async () => {
  const initial = view(); const result=render(initial.node); await screen.findByText('qualified');
  fireEvent.click(screen.getByRole('button',{name:'Underwrite qualified intake'})); fireEvent.click(screen.getByText('New underwriting scenario'));
  mock.post.mockRejectedValueOnce(new Error('lost scenario reply')); fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));
  await screen.findByText(/Save outcome unconfirmed/); await waitFor(()=>expect(initial.onPending).toHaveBeenLastCalledWith(true));
  expect(screen.getByRole('button',{name:'Save assessment snapshot'})).toBeDisabled();expect(screen.getByRole('button',{name:'Close underwriting draft'})).toBeDisabled();
  mock.classification='incomplete';result.rerender(view(1,false,initial.client,initial.onPending).node);await screen.findByText('incomplete');
  expect(screen.getByRole('button',{name:'Retry same scenario'})).toBeEnabled();
  expect(screen.getByRole('button',{name:'Close underwriting draft'})).toBeDisabled();
});
it('keeps the underwriting launch unavailable for incomplete screening',async()=>{
  mock.classification='incomplete';render(view().node);await screen.findByText('incomplete');
  expect(screen.getByRole('button',{name:'Underwrite qualified intake'})).toBeDisabled();
});
