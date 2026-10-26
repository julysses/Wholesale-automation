import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InquiryRecovery } from '../src/components/acquisition/InquiryRecovery';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), role: 'owner', post: vi.fn(), fresh: null as unknown, history: [] as unknown[] }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const item = { receipt_id: 'receipt', state: 'review', updated_at: '2026-10-26T12:00:00.123456+00:00', reason_code: 'CREDENTIALS_INVALID', blockers: ['CREDENTIALS_INVALID'] };
beforeEach(() => {
  mock.role = 'owner'; mock.fresh = item; mock.history = []; mock.post.mockReset(); mock.fetch.mockReset();
  mock.post.mockImplementation(async (init: RequestInit) => { const body = JSON.parse(init.body as string); return { recovery_id: body.id, receipt_id: 'receipt', cycle: 1, duplicate: false, outreach_authorized: false }; });
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => ({ json: async () => {
    if (init?.method === 'POST') return mock.post(init);
    if (path.endsWith('/memberships')) return [{ workspace_id: 'workspace', user_id: 'user', role: mock.role, status: 'active' }];
    if (path === '/health') return { items: [mock.fresh] };
    return mock.history;
  } }));
});
function view() { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><InquiryRecovery userId="user" workspace="workspace" item={item} healthPath="/health" onSaved={vi.fn()} onClose={vi.fn()} /></QueryClientProvider>); }
async function fill() {
  await waitFor(() => expect(screen.getByLabelText('Correction and review note')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Correction and review note'), { target: { value: 'Administrator verified the corrected Page credential.' } });
  fireEvent.change(screen.getByLabelText('Evidence reference'), { target: { value: 'review-ticket-42' } });
  fireEvent.click(screen.getByRole('checkbox'));
}
it('requires acknowledgment and submits the exact timestamp after fresh health validation', async () => {
  view(); expect(screen.getByRole('button', { name: 'Approve recovery cycle' })).toBeDisabled(); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Approve recovery cycle' }));
  expect(await screen.findByText(/Recovery approval recorded/)).toBeVisible();
  expect(JSON.parse(mock.post.mock.calls[0][0].body).expected_updated_at).toBe(item.updated_at);
  expect(mock.fetch.mock.calls.findIndex(call => call[0] === '/health')).toBeLessThan(mock.fetch.mock.calls.findIndex(call => call[1]?.method === 'POST'));
});
it('retains exact request and freezes edits after a lost reply without refetching a changed hold', async () => {
  mock.post.mockRejectedValueOnce(new Error('lost response')); view(); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Approve recovery cycle' }));
  const retry = await screen.findByRole('button', { name: 'Retry exact recovery request' });
  expect(screen.getByLabelText('Correction and review note')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Close recovery review' })).toBeDisabled();
  mock.fresh = { ...item, state: 'completed' }; fireEvent.click(retry);
  await screen.findByText(/Recovery approval recorded/);
  expect(mock.post.mock.calls[0][0].body).toBe(mock.post.mock.calls[1][0].body);
  expect(mock.fetch.mock.calls.filter(call => call[0] === '/health')).toHaveLength(1);
});
it('rejects stale or newly blocked state before posting', async () => {
  mock.fresh = { ...item, blockers: ['INTEGRATION_DISABLED'] }; view(); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Approve recovery cycle' }));
  await screen.findByText(/inquiry changed or could not be checked/); expect(mock.post).not.toHaveBeenCalled();
});
it('shows history but denies operators approval', async () => {
  mock.role = 'operator'; mock.history = [{ id: 'prior', cycle: 1, reason_code: 'CREDENTIALS_INVALID', review_note: 'Earlier reviewed correction', evidence_ref: 'prior-ticket', created_at: '2026-10-26' }]; view();
  expect(await screen.findByText('Earlier reviewed correction')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Approve recovery cycle' })).toBeDisabled();
});
it('blocks another cycle when the history budget is exhausted', async () => {
  mock.history = [1, 2, 3].map(cycle => ({ id: String(cycle), cycle, reason_code: 'CREDENTIALS_INVALID', review_note: 'Reviewed correction', evidence_ref: 'ticket', created_at: '2026-10-26' })); view();
  await screen.findByText('Cycle 3 · 2026-10-26'); expect(screen.getByLabelText('Correction and review note')).toBeDisabled();
});
