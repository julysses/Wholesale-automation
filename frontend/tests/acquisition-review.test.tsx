import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AcquisitionReview } from '../src/pages/AcquisitionReview';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), failOnce: false, revoked: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 409; } }));
const offer = { offer_id: 'o', workspace_id: 'w', lead_id: 'l', property_id: 'p', analysis_id: 'a', analysis_revision: 1,
  latest_analysis_revision: 1, case: 'base', amount: 140000, ceiling: 150000, proposal_note: 'Independent review', historical_status: 'proposed',
  sequence: 1, amount_approval_current: false, amount_review_blockers: ['AMOUNT_NOT_APPROVED'], available_review_actions: ['amount_approved', 'withdrawn'], checked_at: '2026-10-26T04:00:00Z' };
beforeEach(() => {
  mock.failOnce = false; mock.revoked = false; mock.fetch.mockReset();
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') { if (mock.failOnce) { mock.failOnce = false; throw new Error('network'); } return { json: async () => ({ status: 'amount_approved' }) }; }
    const value = path.endsWith('/workspaces') ? [{ id: 'w', name: 'Hilltop' }, { id: 'z', name: 'Other workspace' }] :
      path.endsWith('/summary') ? { id: 'l', property_id: 'p', property_address: '123 Fixture St', city: 'Dallas' } :
      path.includes('/underwriting/') ? [{ id: 'a', acquisition_inputs: { source: 'Fixture' }, acquisition_outputs: { mao: '150000' }, calculation_version: 'v1' }] :
      path.includes('/state') ? { ...offer, available_review_actions: mock.revoked ? [] : offer.available_review_actions } :
      path.includes('/reviews') ? [] : { items: path.includes('/z/') ? [] : [offer], next_after: null };
    return { json: async () => value };
  });
});
async function open() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AcquisitionReview userId="user-a" /></QueryClientProvider>);
  fireEvent.change(await screen.findByLabelText('Workspace'), { target: { value: 'w' } });
  fireEvent.click(await screen.findByText('Open review'));
  await screen.findByText(/Underwriting inputs, provenance/);
}
async function completeApproval() {
  fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'amount_approved' } });
  fireEvent.change(screen.getByLabelText('Decision note'), { target: { value: 'Reviewed exact scenario' } });
  for (const key of ['title', 'liens', 'occupancy', 'valuation', 'repairs', 'financing', 'downside']) fireEvent.change(screen.getByLabelText(`${key} review`), { target: { value: 'Documented diligence' } });
  fireEvent.click(screen.getByRole('checkbox'));
}
it('requires deliberate evidence review and sends exact sequence without actor override', async () => {
  await open(); expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
  await completeApproval(); fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
  await screen.findByText(/Decision recorded/);
  const posts = mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST'); expect(posts).toHaveLength(1);
  const body = JSON.parse(posts[0][1].body); expect(body.expected_sequence).toBe(1); expect(body.status).toBe('amount_approved'); expect(body.actor_id).toBeUndefined(); expect(Object.keys(body.review_notes)).toHaveLength(7);
});
it('retains one mutation reference and payload when the result is unknown', async () => {
  await open(); await completeApproval(); mock.failOnce = true;
  fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Retry same decision' }));
  await screen.findByText(/Decision recorded/);
  const posts = mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST'); expect(posts).toHaveLength(2); expect(posts[0][1].body).toBe(posts[1][1].body);
});
it('rechecks permissions immediately before recording and removes prior workspace detail', async () => {
  await open(); await completeApproval(); mock.revoked = true;
  fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
  await screen.findByText(/This proposal changed/); expect(mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST')).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('Workspace'), { target: { value: 'z' } });
  await waitFor(() => expect(screen.queryByLabelText('Selected offer review')).toBeNull());
  await screen.findByText('No proposals on this page.');
});
