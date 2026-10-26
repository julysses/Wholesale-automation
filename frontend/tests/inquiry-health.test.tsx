import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InquiryHealth } from '../src/components/acquisition/InquiryHealth';
const mock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch }));
const data = { summary: { requires_review: 1, retrying: 0, expired_leases: 0, awaiting_worker: 0, leased: 0, completed: 2 },
  items: [{ receipt_id: 'receipt-fixture', provider: 'facebook', state: 'review', attempts: 1, reason_code: 'CREDENTIALS_INVALID',
    guidance: 'Ask the integration administrator to verify the Page credential.', blockers: ['CREDENTIALS_INVALID'], next_attempt_at: '', lease_expires_at: null }],
  next_after: null, checked_at: '2026-10-26T12:00:00Z' };
beforeEach(() => { mock.fetch.mockReset(); mock.fetch.mockResolvedValue({ json: async () => data }); });
function view(workspace = 'one', client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return { client, node: <QueryClientProvider client={client}><InquiryHealth userId="user" workspace={workspace} /></QueryClientProvider> };
}
it('shows actionable held inquiry guidance without a mutation control', async () => {
  render(view().node);
  expect(await screen.findByText('1 inquiry needs review.')).toBeVisible();
  expect(screen.getByText(data.items[0].guidance)).toBeVisible();
  expect(screen.queryByRole('button', { name: /retry|recover|enable/i })).not.toBeInTheDocument();
  expect(mock.fetch.mock.calls.every(call => !call[1]?.method)).toBe(true);
});
it('hides cached guidance after access failure and never implies a healthy queue', async () => {
  render(view().node); await screen.findByText(data.items[0].guidance);
  mock.fetch.mockRejectedValue(new Error('private provider detail'));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh inquiry health' }));
  expect(await screen.findByText(/Inquiry health is unavailable/)).toBeVisible();
  expect(screen.queryByText(data.items[0].guidance)).not.toBeInTheDocument();
  expect(screen.queryByText(/private provider detail/)).not.toBeInTheDocument();
});
it('switches workspace scope without retaining old inquiry data', async () => {
  const initial = view(); const result = render(initial.node); await screen.findByText(data.items[0].guidance);
  mock.fetch.mockResolvedValue({ json: async () => ({ ...data, summary: { ...data.summary, requires_review: 0 }, items: [] }) });
  result.rerender(view('two', initial.client).node);
  expect(await screen.findByText('No unfinished inquiries on this page.')).toBeVisible();
  expect(screen.queryByText(data.items[0].guidance)).not.toBeInTheDocument();
  await waitFor(() => expect(mock.fetch.mock.calls.at(-1)?.[0]).toContain('/two/inquiries/health'));
});
it('paginates only with the server cursor and supports returning', async () => {
  mock.fetch.mockResolvedValueOnce({ json: async () => ({ ...data, next_after: 'cursor-1' }) });
  render(view().node); await screen.findByText(data.items[0].guidance);
  fireEvent.click(screen.getByRole('button', { name: 'More inquiries' }));
  await waitFor(() => expect(mock.fetch.mock.calls.at(-1)?.[0]).toContain('after=cursor-1'));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Previous inquiries' })).toBeEnabled());
});
