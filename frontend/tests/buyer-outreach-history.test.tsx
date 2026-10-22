import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  rows: [] as Record<string, unknown>[], failFrom: Infinity, countMode: 'normal', calls: vi.fn(), api: vi.fn(),
}));
vi.mock('@/lib/supabase', () => ({ supabase: { from: (table: string) => {
  const builder = {
    select: () => builder, order: () => builder,
    range: async (from: number, to: number) => {
      state.calls(table, from, to);
      if (table !== 'buyer_outreach_log') return { data: [], count: 0, error: null };
      if (from >= state.failFrom) return { data: null, count: null, error: { message: 'History read failed' } };
      const start = state.countMode === 'repeat' ? 0 : from;
      return { data: state.rows.slice(start, start + 200), error: null,
        count: state.countMode === 'missing' ? null : state.countMode === 'changed' && from ? state.rows.length + 1 : state.rows.length };
    },
  };
  return builder;
} } }));
vi.mock('@/lib/api', () => ({ apiFetch: state.api }));
vi.mock('@/hooks/useDeals', () => ({ useDeals: () => ({ data: [] }) }));
vi.mock('@/components/buyers/BuyerImportModal', () => ({ BuyerImportModal: () => null }));
vi.mock('@/components/buyers/BuyerProfileDrawer', () => ({ BuyerProfileDrawer: () => null }));
import { BuyerOutreachHistory } from '@/components/buyers/BuyerOutreachHistory';
import { BuyerIntelligence } from '@/pages/BuyerIntelligence';

function mount(element = <BuyerOutreachHistory />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}
beforeEach(() => {
  state.calls.mockClear(); state.api.mockClear(); state.failFrom = Infinity; state.countMode = 'normal';
  state.rows = Array.from({ length: 1003 }, (_, n) => ({
    id: `event-${n}`, buyer_id: `buyer-${n}`, buyers: { first_name: `Recipient ${n}`, last_name: 'QA' },
    channel: n === 1002 ? 'email' : 'sms', direction: 'outbound', status: n === 0 ? 'dry_run' : 'sent',
    body: n === 0 ? '<script>unsafe()</script><b>Recorded email</b>' : `Recorded message ${n}`,
    to_address: n === 1002 ? 'old,(late)@example.test' : `+1214555${n.toString().padStart(4, '0')}`,
    provider: 'synthetic', provider_msg_id: `receipt-${n}`, created_at: '2026-10-22T12:00:00Z',
    replied_at: n === 1002 ? '2026-10-22T13:00:00Z' : null,
  }));
});

it('loads all 1,003 capped records, renders 25 and finds old destinations without another request', async () => {
  mount();
  await screen.findByText('1,003 saved activity records');
  expect(screen.getAllByRole('row')).toHaveLength(26);
  expect(screen.queryByText('Recipient 25 QA')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next outreach page' }));
  expect(screen.getByText('Recipient 25 QA')).toBeInTheDocument();
  const count = state.calls.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Search outreach history'), { target: { value: 'old,(late)' } });
  expect(screen.getByText('Recipient 1002 QA')).toBeInTheDocument();
  expect(screen.getByText('receipt-1002')).toBeInTheDocument();
  expect(screen.getByText(/Reply recorded/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Outreach history channel'), { target: { value: 'sms' } });
  expect(screen.getByText('No saved records match these filters')).toBeInTheDocument();
  expect(state.calls).toHaveBeenCalledTimes(count);
  expect(state.api).not.toHaveBeenCalled();
});

it('refuses a partial first load instead of displaying its first 200 rows or a false empty state', async () => {
  state.failFrom = 200;
  mount();
  expect(screen.queryByText('No saved outreach records')).not.toBeInTheDocument();
  await screen.findByRole('alert');
  expect(screen.queryByText('Recipient 0 QA')).not.toBeInTheDocument();
  expect(screen.queryByText('No saved outreach records')).not.toBeInTheDocument();
  expect(screen.getByText('Outreach totals unavailable')).toBeInTheDocument();
});

it('retains confirmed data after a failed refresh and replaces it only after verified recovery', async () => {
  mount(); await screen.findByText('Recipient 0 QA');
  state.failFrom = 0;
  fireEvent.click(screen.getByRole('button', { name: 'Refresh outreach history' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Showing last confirmed saved records');
  expect(screen.getByText('Recipient 0 QA')).toBeInTheDocument();
  expect(screen.getByText('1,003 saved activity records')).toBeInTheDocument();
  state.failFrom = Infinity; state.rows = [];
  fireEvent.click(screen.getByRole('button', { name: 'Retry outreach history' }));
  await screen.findByText('No saved outreach records');
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(screen.queryByText('Recipient 0 QA')).not.toBeInTheDocument();
});

it.each(['missing', 'changed', 'repeat'])('rejects %s completeness evidence', async mode => {
  state.countMode = mode;
  mount(); await screen.findByRole('alert');
  expect(screen.queryByText('1,003 saved activity records')).not.toBeInTheDocument();
  expect(screen.queryByText('No saved outreach records')).not.toBeInTheDocument();
  expect(state.calls.mock.calls.length).toBeLessThanOrEqual(2);
});

it('renders provider status literally and treats recorded HTML as text', async () => {
  const { container } = mount();
  await screen.findByText('Recipient 0 QA');
  expect(screen.getByText('dry_run')).toBeInTheDocument();
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('tbody b')).toBeNull();
  expect(screen.getAllByText('<script>unsafe()</script><b>Recorded email</b>')).toHaveLength(2);
});

it('reads history only when its actual page tab is opened and performs no send', async () => {
  mount(<BuyerIntelligence />);
  await screen.findByText(/0 active buyers/);
  expect(state.calls.mock.calls.some(([table]) => table === 'buyer_outreach_log')).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Outreach Log' }));
  await screen.findByText('1,003 saved activity records');
  expect(state.api).not.toHaveBeenCalled();
});
