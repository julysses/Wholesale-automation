import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BuyerProfiles } from '../src/components/acquisition/BuyerProfiles';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), lose: false, deny: false, paused: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedBuyer = true; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.lose = mock.deny = mock.paused = false;
  mock.fetch.mockImplementation(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.deny) throw new ApiError('Denied', 403);
      if (mock.lose) throw new Error('Lost response');
      const r = JSON.parse(init.body as string);
      return { json: async () => ({ request_id: r.id, workspace_id: id(2), buyer_id: r.buyer_id, revision: r.expected_revision + 1,
        details: r.details, duplicate: false, profile_recorded: true, buyer_verified: false, contact_authorized: false, execution_authorized: false }) };
    }
    return { json: async () => ({ workspace_id: id(2), checked_at: new Date().toISOString(), can_save: !mock.paused,
      items: [], next_cursor: null, contact_authorized: false, execution_authorized: false }) };
  });
});
function open() { return render(<QueryClientProvider client={new QueryClient()}><BuyerProfiles userId={id(1)} workspace={id(2)} disabled={false} onPending={mock.pending} /></QueryClientProvider>); }
async function prepare() {
  const view = open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Open buyer profiles'));
  await screen.findByText('No buyer profiles on this page.'); fireEvent.click(screen.getByText('Add buyer'));
  fireEvent.change(screen.getByLabelText('First name'), { target: { value: 'Sample' } });
  fireEvent.change(screen.getByLabelText('Last name'), { target: { value: 'Buyer' } });
  fireEvent.change(screen.getByLabelText(/Source and context/), { target: { value: 'Self-reported preferences from a buyer inquiry.' } });
  fireEvent.click(screen.getByText('Review buyer details')); await screen.findByText('3. Review and save'); return view;
}
const posts = () => mock.fetch.mock.calls.filter(c => c[1]?.method === 'POST');
it('guides entry and explicit review before saving unknown budgets without authority', async () => {
  await prepare(); expect(posts()).toHaveLength(0); expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByText('Save buyer profile')); await screen.findByText(/Buyer details saved for review/);
  expect(posts()).toHaveLength(1); expect(JSON.parse(posts()[0][1].body)).toMatchObject({ expected_revision: 0, details: { min_price_cents: null, max_price_cents: null, close_speed_days: null } });
  expect(sessionStorage.length).toBe(0); fireEvent.click(screen.getByText('Close without saving')); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('recovers the same request after reload and retains it after a later denial', async () => {
  mock.lose = true; const view = await prepare(); fireEvent.click(screen.getByText('Save buyer profile')); await screen.findByText(/Save is unconfirmed/);
  const original = posts()[0][1].body; view.unmount(); mock.lose = false; mock.deny = true; open();
  fireEvent.click(screen.getByText('Retry saved buyer request')); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  await waitFor(() => expect(screen.getByText('Retry saved buyer request')).toBeEnabled()); mock.deny = false;
  fireEvent.click(screen.getByText('Retry saved buyer request')); await screen.findByText(/Buyer details saved for review/);
  expect(posts().map(c => c[1].body)).toEqual([original, original, original]); expect(sessionStorage.length).toBe(0);
});
it('clears definite first-attempt rejection without retrying a new request automatically', async () => {
  mock.deny = true; await prepare(); fireEvent.click(screen.getByText('Save buyer profile')); await screen.findByText(/The save was rejected/);
  expect(sessionStorage.length).toBe(0); expect(posts()).toHaveLength(1);
});
it('rechecks a newly paused acquisition before making any save request', async () => {
  await prepare(); mock.paused = true; fireEvent.click(screen.getByText('Save buyer profile')); await screen.findByText(/Current buyer details or save permission changed/);
  expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});
it('blocks corrupt recovery without making API calls', () => {
  sessionStorage.setItem(`wholesale.acquisition.buyer:v1:${id(1)}:${id(2)}`, '{broken'); open();
  expect(screen.getByRole('alert')).toHaveTextContent('Saved buyer recovery could not be read safely'); expect(mock.fetch).not.toHaveBeenCalled();
});
