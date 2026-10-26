import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IntakeReview } from '../src/components/acquisition/IntakeReview';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), role: 'owner', sequence: 0, changed: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 409; } }));
const state = { sequence: 0, preparation_hash: 'a'.repeat(64), target_hash: 'b'.repeat(64), target_snapshot: { parcel_id: 'parcel-42', county: 'Dallas' }, latest_review: null, link_current: false };
beforeEach(() => {
  mock.fetch.mockReset(); mock.post.mockReset(); mock.role = 'owner'; mock.sequence = 0; mock.changed = false;
  mock.post.mockImplementation(async (init: RequestInit) => { const body = JSON.parse(init.body as string); return { review_id: body.id, sequence: body.expected_sequence + 1, duplicate: false, outreach_authorized: false }; });
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => ({ json: async () => {
    if (init?.method === 'POST') return mock.post(init);
    if (path.includes('/intakes?')) return { items: [{ id: 'intake', lead_id: 'source', classification: 'incomplete', created_at: '2026-10-26' }], next_after: null };
    if (path.endsWith('/memberships')) return [{ user_id: 'user', workspace_id: 'w', status: 'active', role: mock.role }];
    if (path.includes('/candidates?')) return { items: [{ lead_id: 'canonical', property_id: 'property', property_address: '1 Fixture St', city: 'Dallas', state: 'TX', county: 'Dallas', parcel_id: 'parcel-42', county_unit: null, match_basis: 'CONTACT_ONLY' }], truncated: false };
    if (path.includes('/identity-state')) return { ...state, sequence: mock.sequence, latest_review: mock.sequence ? { id: 'prior', sequence: mock.sequence, action: 'link_property', review_note: 'Previous documented review', created_at: '2026-10-26' } : null, target_hash: mock.changed ? 'c'.repeat(64) : path.includes('?target=') ? state.target_hash : null };
    if (path.includes('/identity-reviews?')) return [];
    return { id: 'intake', classification: 'incomplete', prepared_answers: { answers: { property_address: 'Seller asserted address' }, missing_fields: ['condition'], reason_codes: ['MISSING_REQUIRED_ANSWERS'] }, normalization_notes: [] };
  } }));
});
function view(workspace = 'w', client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return { client, node: <QueryClientProvider client={client}><IntakeReview userId="user" workspace={workspace} /></QueryClientProvider> };
}
async function open() {
  render(view().node); fireEvent.click(screen.getByRole('button', { name: 'Seller intake identity review' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Review intake' }));
  await screen.findByText('Seller asserted address');
  fireEvent.click(await screen.findByRole('button', { name: 'Select property' }));
  await waitFor(() => expect(screen.getByLabelText('Identity decision')).toBeEnabled());
}
function fill() {
  fireEvent.change(screen.getByLabelText('Property evidence basis'), { target: { value: 'parcel_document' } });
  fireEvent.change(screen.getByLabelText('Property evidence reference'), { target: { value: 'parcel-review-document-42' } });
  fireEvent.change(screen.getByLabelText('Identity review note'), { target: { value: 'Reviewer checked independent parcel documentation.' } });
  fireEvent.click(screen.getByRole('checkbox'));
}
it('labels contact-only evidence and requires independent evidence before saving', async () => {
  await open(); expect(screen.getByText(/Contact-only match/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Record identity review' })).toBeDisabled(); fill();
  fireEvent.click(screen.getByRole('button', { name: 'Record identity review' }));
  await screen.findByText(/Identity review recorded/);
  const body = JSON.parse(mock.post.mock.calls[0][0].body);
  expect(body.target_lead_id).toBe('canonical'); expect(body.target_hash).toBe(state.target_hash);
  expect(body.action).toBe('link_property'); expect(body.seller_evidence_ref).toBeNull();
});
it('requires separate seller evidence for repeat inquiry', async () => {
  await open(); fireEvent.change(screen.getByLabelText('Identity decision'), { target: { value: 'repeat_inquiry' } }); fill();
  expect(screen.getByRole('button', { name: 'Record identity review' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Seller identity evidence reference'), { target: { value: 'seller-independent-document-42' } });
  expect(screen.getByRole('button', { name: 'Record identity review' })).toBeEnabled();
});
it('refuses stale target evidence without a mutation', async () => {
  await open(); fill(); mock.changed = true;
  fireEvent.click(screen.getByRole('button', { name: 'Record identity review' }));
  await screen.findByText(/Review unavailable or changed/); expect(mock.post).not.toHaveBeenCalled();
});
it('retains exact body and freezes controls for unknown outcomes across queue refresh', async () => {
  mock.post.mockRejectedValueOnce(new Error('lost response')); await open(); fill();
  fireEvent.click(screen.getByRole('button', { name: 'Record identity review' }));
  await screen.findByRole('button', { name: 'Retry exact identity request' });
  expect(screen.getByLabelText('Identity review note')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Close intake review' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Refresh intakes' }));
  mock.sequence = 9; fireEvent.click(screen.getByRole('button', { name: 'Retry exact identity request' }));
  await screen.findByText(/Identity review recorded/); expect(mock.post.mock.calls[0][0].body).toBe(mock.post.mock.calls[1][0].body);
});
it('operators can inspect evidence but cannot record decisions', async () => {
  mock.role = 'operator'; render(view().node);
  fireEvent.click(screen.getByRole('button', { name: 'Seller intake identity review' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Review intake' }));
  await screen.findByText('Seller asserted address'); expect(screen.getByLabelText('Identity decision')).toBeDisabled();
});
it('workspace changes discard previous selected evidence', async () => {
  const initial = view(); const result = render(initial.node);
  fireEvent.click(screen.getByRole('button', { name: 'Seller intake identity review' })); fireEvent.click(await screen.findByRole('button', { name: 'Review intake' }));
  await screen.findByText('Seller asserted address'); result.rerender(view('other', initial.client).node);
  await waitFor(() => expect(screen.queryByText('Seller asserted address')).not.toBeInTheDocument());
});

it('records revocation without carrying a target or new identity evidence', async () => {
  mock.sequence = 1; await open();
  fireEvent.change(screen.getByLabelText('Identity decision'), { target: { value: 'revoke' } });
  await waitFor(() => expect(screen.getByLabelText('Identity review note')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Identity review note'), { target: { value: 'Correcting the prior reviewed property association.' } });
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: 'Record identity review' }));
  await screen.findByText(/Identity review recorded/);
  const body = JSON.parse(mock.post.mock.calls[0][0].body);
  expect(body.action).toBe('revoke'); expect(body.target_lead_id).toBeNull(); expect(body.property_evidence_ref).toBeNull(); expect(body.expected_sequence).toBe(1);
});
it('locks intake editing and closing while campaign review reconciliation is pending', async () => {
  const key='campaign-link-review:v1:user:w:intake';
  sessionStorage.setItem(key,JSON.stringify({id:'50000000-0000-4000-8000-000000000001',expected_sequence:0,preparation_hash:'a'.repeat(64),action:'link',campaign_id:'40000000-0000-4000-8000-000000000001',ad_account_id:'999',evidence_ref:'Reviewed ownership file',review_note:'Reviewed account ownership and campaign identity.'}));
  await open(); fireEvent.click(screen.getByRole('button',{name:'Review campaign attribution'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Close intake review'})).toBeDisabled());
  expect(screen.getByLabelText('Identity decision')).toBeDisabled(); expect(screen.getByRole('button',{name:'Retry exact campaign review'})).toBeEnabled();
  sessionStorage.removeItem(key);
});
