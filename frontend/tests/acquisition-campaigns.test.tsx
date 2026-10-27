import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CampaignDrafts } from '../src/components/acquisition/CampaignDrafts';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), role: 'owner', page: {} as unknown }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const workspace = '11111111-1111-4111-8111-111111111111';
const campaign = '22222222-2222-4222-8222-222222222222';
const key = `acquisition-campaign-request:v1:user:${workspace}`;
const draft = { id: campaign, name: 'Dallas seller inquiries', channel: 'facebook', budget_cents: 12345, currency: 'USD' };
const row = { id: campaign, name: draft.name, workspace_id: workspace, status: 'draft', acquisition_channel: 'facebook', acquisition_budget_cents: 12345, acquisition_currency: 'USD' };
beforeEach(() => {
  sessionStorage.clear(); mock.role = 'owner'; mock.page = { items: [row], next_after: null }; mock.fetch.mockReset(); mock.post.mockReset();
  mock.post.mockImplementation(async (init: RequestInit) => ({ ...JSON.parse(init.body as string), workspace_id: workspace, status: 'draft', execution_authorized: false, duplicate: false }));
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return { json: () => mock.post(init) };
    return { json: async () => path.endsWith('/memberships') ? [{ workspace_id: workspace, user_id: 'user', role: mock.role, status: 'active' }] : mock.page };
  });
});
function view(userId = 'user', onPending = vi.fn()) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CampaignDrafts userId={userId} workspace={workspace} onPending={onPending} /></QueryClientProvider>);
}
async function fill(budget = '123.45') {
  await waitFor(() => expect(screen.getByLabelText('Campaign name')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Campaign name'), { target: { value: draft.name } });
  fireEvent.change(screen.getByLabelText('Planned budget (USD)'), { target: { value: budget } });
}
it('saves exact cents with no authority fields and separates planned budget from reviewed costs', async () => {
  view(); await fill(); expect(await screen.findByText('Actual spend requires reviewed cost evidence.')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Save campaign draft' })); await screen.findByText(/Campaign draft saved/);
  const body = JSON.parse(mock.post.mock.calls[0][0].body);
  expect(body.budget_cents).toBe(12345); expect(body.currency).toBe('USD'); expect(body.workspace_id).toBeUndefined(); expect(body.execution_authorized).toBeUndefined(); expect(sessionStorage.getItem(key)).toBeNull();
});
it.each(['1.001', '-1', '1e2', '1000000000.01', 'NaN', ''])('rejects invalid budget %s', async value => {
  view(); await fill(value); expect(screen.getByRole('button', { name: 'Save campaign draft' })).toBeDisabled(); expect(mock.post).not.toHaveBeenCalled();
});
it('preserves exact request across lost reply, refresh and reload', async () => {
  const pending = vi.fn(); mock.post.mockRejectedValueOnce(new Error('lost reply')); const original = view('user', pending); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Save campaign draft' })); await screen.findByText(/result is unconfirmed/);
  expect(pending).toHaveBeenLastCalledWith(true); const first = mock.post.mock.calls[0][0].body; expect(sessionStorage.getItem(key)).toBe(first);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh campaigns' })); expect(screen.getByLabelText('Campaign name')).toBeDisabled(); original.unmount();
  view(); fireEvent.click(await screen.findByRole('button', { name: 'Retry exact draft request' })); await screen.findByText(/Campaign draft saved/);
  expect(mock.post.mock.calls[1][0].body).toBe(first); expect(sessionStorage.getItem(key)).toBeNull();
});
it('keeps the original uncertain request when retry authority is rejected', async () => {
  sessionStorage.setItem(key, JSON.stringify(draft)); mock.post.mockRejectedValue(new ApiError('Access revoked', 403)); view();
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact draft request' })); await screen.findByText(/result is unconfirmed/);
  expect(sessionStorage.getItem(key)).toBe(JSON.stringify(draft)); expect(screen.getByLabelText('Campaign name')).toBeDisabled();
});
it('clears a definitively rejected first attempt', async () => {
  mock.post.mockRejectedValue(new ApiError('Access revoked', 403)); view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save campaign draft' }));
  await screen.findByText(/creation was rejected/); expect(sessionStorage.getItem(key)).toBeNull(); await waitFor(() => expect(screen.getByLabelText('Campaign name')).toBeEnabled());
});
it.each([{ workspace_id: 'other' }, { execution_authorized: true }, { budget_cents: 1 }, { id: campaign }])('holds inconsistent success %j', async override => {
  mock.post.mockImplementation(async (init: RequestInit) => ({ ...JSON.parse(init.body as string), workspace_id: workspace, status: 'draft', execution_authorized: false, duplicate: false, ...override }));
  view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save campaign draft' })); await screen.findByText(/result is unconfirmed/);
  expect(screen.getByRole('button', { name: 'Retry exact draft request' })).toBeEnabled();
});
it('lets operators read without creating', async () => {
  mock.role = 'operator'; view(); expect(await screen.findByText(draft.name)).toBeVisible(); expect(screen.getByRole('button', { name: 'Save campaign draft' })).toBeDisabled();
});
it('rejects a cross-workspace list and cursor', async () => {
  mock.page = { items: [{ ...row, workspace_id: 'other' }], next_after: campaign }; view();
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be verified'); expect(screen.queryByText(draft.name)).toBeNull(); expect(screen.getByRole('button', { name: 'Next campaigns' })).toBeDisabled();
});
it('blocks corrupted pending storage and isolates it by user', async () => {
  sessionStorage.setItem(key, 'bad-json'); const first = view(); expect(await screen.findByRole('alert')).toHaveTextContent('saved draft request');
  expect(screen.getByRole('button', { name: 'Save campaign draft' })).toBeDisabled(); first.unmount(); view('other-user');
  expect(screen.queryByText(/saved draft request/)).toBeNull(); expect(screen.queryByRole('button', { name: 'Retry exact draft request' })).toBeNull();
});
it('does not mutate if storage cannot preserve the request', async () => {
  view(); await fill(); const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
  fireEvent.click(screen.getByRole('button', { name: 'Save campaign draft' })); await screen.findByText(/No request was sent/); expect(mock.post).not.toHaveBeenCalled(); storage.mockRestore();
});
it('paginates with the verified cursor and hides stale rows after a failed refresh', async () => {
  mock.page = { items: [row], next_after: campaign }; view(); await screen.findByText(draft.name);
  mock.page = { items: [], next_after: null }; fireEvent.click(screen.getByRole('button', { name: 'Next campaigns' }));
  await screen.findByText('No campaign drafts on this page.'); expect(mock.fetch.mock.calls.some(call => call[0].endsWith(`&after=${campaign}`))).toBe(true);
  mock.page = { items: [row], next_after: campaign }; fireEvent.click(screen.getByRole('button', { name: 'Previous campaigns' })); await screen.findByText(draft.name);
  mock.page = { items: [{ ...row, workspace_id: 'other' }], next_after: null }; fireEvent.click(screen.getByRole('button', { name: 'Refresh campaigns' }));
  await screen.findByRole('alert'); expect(screen.queryByText(draft.name)).toBeNull();
});
