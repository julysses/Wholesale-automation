vi.mock('@/components/buyers/BuyerChangeRecovery', () => ({ BuyerChangeRecovery: () => null }));
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { queryAllConfirmed } from '@/lib/queryAll';

const state = vi.hoisted(() => ({ rows: [] as Record<string, unknown>[], fail: false, calls: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ supabase: { from: () => {
  const filters: [string, unknown][] = [];
  const query = {
    select: () => query, order: () => query,
    eq: (key: string, value: unknown) => { filters.push([key, value]); return query; },
    range: async (from: number, to: number) => {
      state.calls(from, to);
      const rows = state.rows.filter(row => filters.every(([key, value]) => row[key] === value));
      return state.fail ? { data: null, count: null, error: { message: 'Read failed' } }
        : { data: rows.slice(from, Math.min(to + 1, from + 200)), count: rows.length, error: null };
    },
    limit: async () => ({ data: [], error: null }),
  };
  return query;
} } }));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/hooks/useDeals', () => ({ useDeals: () => ({ data: [] }) }));
vi.mock('@/hooks/useAIAgent', () => ({ useBuyerMatcher: () => ({ match: vi.fn() }) }));
vi.mock('@/components/buyers/BuyerImportModal', () => ({ BuyerImportModal: () => null }));
vi.mock('@/components/buyers/BuyerProfileDrawer', () => ({ BuyerProfileDrawer: () => null }));
import { BuyerIntelligence } from '@/pages/BuyerIntelligence';
import { Buyers } from '@/pages/Buyers';
import { LandBuyerHub } from '@/components/land/LandBuyerHub';

function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
  return client;
}
beforeEach(() => {
  state.fail = false; state.calls.mockClear();
  state.rows = Array.from({ length: 1003 }, (_, index) => ({
    id: `buyer-${index}`, first_name: `Buyer ${index}`, last_name: 'QA', active: true,
    ibie_score: 80, ibie_tier: 'A', tier: 'A', tags: [], buys_land: true,
    land_buyer_type: index === 1002 ? null : 'builder', deals_closed: 0,
    email: index === 1002 ? 'literal,(last)@example.test' : '',
  }));
});

it('reads beyond server caps and searches the last buyer literally without another database read', async () => {
  mount(<Buyers />);
  await screen.findByText('Buyer 0 QA');
  expect(screen.queryByText('Buyer 25 QA')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next buyer page' }));
  expect(screen.getByText('Buyer 25 QA')).toBeInTheDocument();
  const calls = state.calls.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Search buyers'), { target: { value: 'literal,(last)' } });
  expect(screen.getByText('Buyer 1002 QA')).toBeInTheDocument();
  expect(state.calls).toHaveBeenCalledTimes(calls);
});

it('loads the full leaderboard, retains confirmed records on refresh failure and allows recovery', async () => {
  const client = mount(<BuyerIntelligence />);
  await screen.findByText('Buyer 0 QA');
  expect(screen.queryByText('Buyer 25 QA')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Search buyer leaderboard'), { target: { value: 'literal,(last)' } });
  expect(screen.getByText('Buyer 1002 QA')).toBeInTheDocument();
  state.fail = true;
  await act(async () => { await client.invalidateQueries({ queryKey: ['buyers'] }); });
  expect(await screen.findByRole('alert')).toHaveTextContent('Read failed');
  expect(screen.getByText('Buyer 1002 QA')).toBeInTheDocument();
  state.fail = false;
  fireEvent.click(screen.getByRole('button', { name: 'Retry loading buyers' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
});

it('keeps uncategorized land buyers visible after capped reads', async () => {
  mount(<LandBuyerHub />);
  await screen.findByText('Buyer 1002 QA');
  expect(screen.getByText('Needs category review')).toBeInTheDocument();
  expect(screen.queryByText('Buyer 25 QA')).not.toBeInTheDocument();
});

it('does not show an empty leaderboard when the first request failed', async () => {
  state.fail = true;
  mount(<BuyerIntelligence />);
  await screen.findByRole('alert');
  expect(screen.queryByText('No buyers found')).not.toBeInTheDocument();
});

it.each(['missing', 'changed', 'duplicate', 'incomplete'])('rejects %s completeness evidence', async mode => {
  let calls = 0;
  await expect(queryAllConfirmed(async () => {
    calls++;
    return { error: null, count: mode === 'missing' ? null : mode === 'changed' && calls > 1 ? 3 : 2,
      data: calls === 1 ? [{ id: 'a' }] : mode === 'duplicate' ? [{ id: 'a' }] : [] };
  })).rejects.toThrow(/confirmed|changed|completely/);
  expect(calls).toBeLessThanOrEqual(2);
});
