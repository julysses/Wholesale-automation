import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ fetch: vi.fn(), actor: 'owner-a' }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.fetch }));
vi.mock('@/hooks/useProfile', () => ({ useProfile: () => ({ isAdmin: true, profile: { id: mocks.actor } }) }));
vi.mock('@/components/lists/ForeclosureActions', () => ({ ForeclosureActions: () => null }));
import { DailyLists } from '@/pages/DailyLists';
beforeEach(() => {
  mocks.actor = 'owner-a'; mocks.fetch.mockReset();
  mocks.fetch.mockImplementation(async (url: string) => ({ json: async () => url.includes('/captures') ? { counties: [{county:'Collin',documents:164,complete_documents:164,captured_pages:420,expected_pages:420,extracted_pages:420,extracted_documents:164,quality_review_pages:67,updated_at:null}] } : url.includes('/propstream') ?
    { total: 1, total_budget: { remaining_cents: 5000, committed_cents: 0 }, items: [{ lead_id: 'fixture', address_std: 'Synthetic property', county: 'Collin', stage: 'current_status_review', handoff: null }] } :
    { day: '2026-10-13', review_count: 654, runs: [] } }));
});
it('shows holds without manual forms or claiming automation is active', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><DailyLists /></QueryClientProvider>);
  expect(await screen.findByText('Synthetic property · Collin')).toBeInTheDocument();
  expect(screen.getByText('On hold — current sale needs verification')).toBeInTheDocument();
  expect(screen.getByText('Automation setup in progress')).toBeInTheDocument();
  expect(screen.getByRole('region',{name:'County document capture'})).toHaveTextContent('164 notices captured');
  expect(screen.getByRole('region',{name:'County document capture'})).toHaveTextContent('Text extracted from 420 pages across 164 complete documents · 67 pages flagged for text-quality review');
  expect(view.container.querySelectorAll('input,textarea')).toHaveLength(0);
  expect(mocks.fetch.mock.calls.every(([, options]) => !options || !options.method || options.method === 'GET')).toBe(true);
  mocks.actor = 'owner-b';
  view.rerender(<QueryClientProvider client={client}><DailyLists /></QueryClientProvider>);
  await waitFor(() => expect(client.getQueryData(['daily-lists', 'owner-b'])).toBeTruthy());
});
it('reports failures instead of displaying an empty successful queue', async () => {
  mocks.fetch.mockRejectedValue(new Error('unavailable'));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DailyLists /></QueryClientProvider>);
  expect(await screen.findByText(/Collection status unavailable/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Retry collection status' }));
  expect(screen.queryByText(/No collection receipts/)).not.toBeInTheDocument();
});
