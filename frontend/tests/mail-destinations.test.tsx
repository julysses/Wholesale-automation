import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MailDestinations } from '../src/components/acquisition/MailDestinations';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), role: 'owner', page: {} as unknown, state: {} as unknown }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const workspace = '11111111-1111-4111-8111-111111111111', campaign = '22222222-2222-4222-8222-222222222222', destination = '33333333-3333-4333-8333-333333333333';
const evidence = { mode: 'phone', value: '+12145550100', verification_ref: campaign, verification_hash: 'a'.repeat(64), verified_at: '2026-01-01T00:00:00Z', expires_at: '2099-01-01T00:00:00Z' };
const review = { id: campaign, expected_version: 0, action: 'approved', note: 'Verified controlled destination and routing.', ...evidence };
const pending = { destination_id: destination, review }, key = `acquisition-destination-request:v1:user:${workspace}:${campaign}`;
const history = { id: campaign, workspace_id: workspace, campaign_id: campaign, destination_id: destination, version: 1, action: 'approved', ...evidence };
const state = { workspace_id: workspace, campaign_id: campaign, destination_id: destination, version: 1, status: 'approved', review_current: true, execution_authorized: false, checked_at: '2026-10-28T12:00:00Z', latest_review: history };
function receipt(path: string, init: RequestInit) { const r = JSON.parse(init.body as string); return { review_id: r.id, workspace_id: workspace, destination_id: path.split('/').at(-2), version: r.expected_version + 1, duplicate: false, execution_authorized: false }; }
beforeEach(() => {
  sessionStorage.clear(); mock.role = 'owner'; mock.page = { items: [], next_after: null }; mock.state = state; mock.fetch.mockReset(); mock.post.mockReset(); mock.post.mockImplementation(async (path: string, init: RequestInit) => receipt(path, init));
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return { json: () => mock.post(path, init) };
    return { json: async () => path.endsWith('/memberships') ? [{ workspace_id: workspace, user_id: 'user', role: mock.role, status: 'active' }] : path.includes('?') ? mock.page : mock.state };
  });
});
function view(userId = 'user') { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MailDestinations userId={userId} workspace={workspace} campaign={campaign}/></QueryClientProvider>); }
async function open() { fireEvent.click(screen.getByRole('button', { name: 'Review mail destinations' })); await screen.findByLabelText('Phone number or HTTPS address'); }
async function fill() {
  await open(); await waitFor(() => expect(screen.getByLabelText('Phone number or HTTPS address')).toBeEnabled());
  for (const [label, value] of [['Phone number or HTTPS address', evidence.value], ['Verification evidence reference', campaign], ['Evidence SHA-256 digest', evidence.verification_hash], ['Verified at (ISO date with time zone)', evidence.verified_at], ['Verification expires at (ISO date with time zone)', evidence.expires_at], ['Review or withdrawal reason', review.note]]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByLabelText('I reviewed destination control and routing evidence.'));
}
async function inspect() { mock.page = { items: [history], next_after: null }; view(); await open(); fireEvent.click(await screen.findByRole('button', { name: `Inspect destination ${destination}` })); await screen.findByText('Current status: approved · Version 1'); }
it('requires attestation and sends no client authority fields', async () => {
  view(); await fill(); fireEvent.click(screen.getByLabelText('I reviewed destination control and routing evidence.')); expect(screen.getByRole('button', { name: 'Record destination approval' })).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I reviewed destination control and routing evidence.')); fireEvent.click(screen.getByRole('button', { name: 'Record destination approval' })); await screen.findByText(/Destination review recorded/);
  const sent = JSON.parse(mock.post.mock.calls[0][1].body); expect(sent.action).toBe('approved'); expect(sent.expected_version).toBe(0); expect(sent.actor_id).toBeUndefined(); expect(sent.workspace_id).toBeUndefined(); expect(sessionStorage.getItem(key)).toBeNull();
});
it('preserves exact approval through lost response and remount', async () => {
  mock.post.mockRejectedValueOnce(new Error('timeout')); const first = view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record destination approval' })); await screen.findByText(/Review is unconfirmed/);
  const body = mock.post.mock.calls[0][1].body, path = mock.post.mock.calls[0][0]; expect(sessionStorage.getItem(key)).not.toBeNull(); expect(screen.getByLabelText('Phone number or HTTPS address')).toBeDisabled(); first.unmount(); view();
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact destination review' })); await screen.findByText(/Destination review recorded/); expect(mock.post.mock.calls[1][0]).toBe(path); expect(mock.post.mock.calls[1][1].body).toBe(body);
});
it('retains uncertain withdrawal after a forbidden retry', async () => {
  const request = { destination_id: destination, review: { id: campaign, expected_version: 1, action: 'withdrawn', note: review.note } }; sessionStorage.setItem(key, JSON.stringify(request)); mock.post.mockRejectedValue(new ApiError('revoked', 403)); view();
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact destination review' })); await screen.findByText(/Review is unconfirmed/); expect(sessionStorage.getItem(key)).toBe(JSON.stringify(request)); expect(JSON.parse(mock.post.mock.calls[0][1].body).value).toBeUndefined();
});
it('clears only a first definite rejection', async () => {
  mock.post.mockRejectedValue(new ApiError('revoked', 403)); view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record destination approval' })); await screen.findByText(/Review rejected/); expect(sessionStorage.getItem(key)).toBeNull();
});
it('requires explicit current details before selected approval', async () => {
  await inspect(); expect(screen.getByLabelText('Phone number or HTTPS address')).toBeDisabled(); fireEvent.click(screen.getByRole('button', { name: 'Load current destination details' })); expect(screen.getByLabelText('Phone number or HTTPS address')).toHaveValue(evidence.value);
  fireEvent.change(screen.getByLabelText('Review or withdrawal reason'), { target: { value: review.note } }); fireEvent.click(screen.getByLabelText('I reviewed destination control and routing evidence.')); fireEvent.click(screen.getByRole('button', { name: 'Record destination approval' })); await screen.findByText(/Destination review recorded/); expect(JSON.parse(mock.post.mock.calls[0][1].body).expected_version).toBe(1);
});
it('withdraws without supplying replacement destination evidence', async () => {
  await inspect(); fireEvent.change(screen.getByLabelText('Review or withdrawal reason'), { target: { value: 'Withdraw because routing is no longer verified.' } }); fireEvent.click(screen.getByRole('button', { name: 'Withdraw destination approval' })); await screen.findByText(/Destination review recorded/); expect(Object.keys(JSON.parse(mock.post.mock.calls[0][1].body)).sort()).toEqual(['action', 'expected_version', 'id', 'note']);
});
it('does not advance an editing form to a newer current version', async () => {
  await inspect(); fireEvent.click(screen.getByRole('button', { name: 'Load current destination details' })); mock.state = { ...state, version: 2, latest_review: { ...history, version: 2 } }; fireEvent.click(screen.getByRole('button', { name: 'Refresh destinations' })); await screen.findByText('Current status: approved · Version 2'); expect(screen.getByLabelText('Phone number or HTTPS address')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Record destination approval' })).toBeDisabled();
});
it.each(['operator', 'acquisition_caller', 'agency_manager'])('prevents %s from reviewing', async role => { mock.role = role; await inspect(); expect(screen.getByRole('button', { name: 'Record destination approval' })).toBeDisabled(); expect(screen.getByRole('button', { name: 'Withdraw destination approval' })).toBeDisabled(); });
it('hides cross-workspace history', async () => { mock.page = { items: [{ ...history, workspace_id: 'other', value: 'Private destination' }], next_after: null }; view(); await open(); expect(await screen.findByRole('alert')).toHaveTextContent('Destination history could not be verified'); expect(screen.queryByText(/Private destination/)).toBeNull(); });
it('renders markup as literal historical text', async () => { mock.page = { items: [{ ...history, value: '<img src=x>' }], next_after: null }; const result = view(); await open(); await screen.findByText(/<img src=x>/); expect(result.container.querySelector('img')).toBeNull(); });
it.each([{ workspace_id: 'other' }, { review_current: true, status: 'withdrawn' }, { execution_authorized: true }, { version: true }, { checked_at: 'invalid' }, { latest_review: { ...history, expires_at: '2026-10-01T00:00:00Z' } }])('holds inconsistent state %j', async override => { mock.page = { items: [history], next_after: null }; mock.state = { ...state, ...override }; view(); await open(); fireEvent.click(await screen.findByRole('button', { name: `Inspect destination ${destination}` })); await screen.findByText('Current destination could not be verified.'); expect(screen.getByRole('button', { name: 'Withdraw destination approval' })).toBeDisabled(); });
it.each([{ version: true }, { execution_authorized: true }, { duplicate: 'false' }, { workspace_id: 'other' }])('retains pending on inconsistent receipt %j', async override => { mock.post.mockImplementation(async (path: string, init: RequestInit) => ({ ...receipt(path, init), ...override })); view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record destination approval' })); await screen.findByText(/Review is unconfirmed/); expect(sessionStorage.getItem(key)).not.toBeNull(); });
it('blocks corrupt pending storage and isolates another identity', async () => { sessionStorage.setItem(key, JSON.stringify({ ...pending, extra: true })); const first = view(); expect(screen.getByRole('alert')).toHaveTextContent('Saved destination request cannot be read'); first.unmount(); view('other'); expect(screen.getByRole('button', { name: 'Review mail destinations' })).toBeEnabled(); });
it('sends nothing if storage fails', async () => { view(); await fill(); const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('unavailable'); }); fireEvent.click(screen.getByRole('button', { name: 'Record destination approval' })); await screen.findByText(/No review was sent/); expect(mock.post).not.toHaveBeenCalled(); fail.mockRestore(); });
