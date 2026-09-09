import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import type { Buyer } from '@/types';

const state = vi.hoisted(() => ({
  record: {} as Record<string, unknown>,
  update: vi.fn(),
}));

vi.mock('@/lib/supabase', () => ({
  supabase: {
    from: (table: string) => ({
      update: (payload: Record<string, unknown>) => {
        state.update(table, payload);
        return {
          eq: (column: string, id: string) => ({
            select: () => ({
              single: async () => {
                if (column !== 'id' || id !== state.record.id) throw new Error('Wrong buyer updated');
                state.record = { ...state.record, ...payload };
                return { data: state.record, error: null };
              },
            }),
          }),
        };
      },
    }),
  },
}));
vi.mock('@/hooks/useBuyers', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/hooks/useBuyers')>(),
  useBuyers: () => ({ data: [state.record as unknown as Buyer], isLoading: false, error: null }),
}));
vi.mock('@/hooks/useDeals', () => ({ useDeals: () => ({ data: [] }) }));
vi.mock('@/hooks/useAIAgent', () => ({ useBuyerMatcher: () => ({ match: vi.fn() }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { Buyers } from '@/pages/Buyers';

beforeEach(() => {
  vi.clearAllMocks();
  state.record = {
    id: 'buyer-1', first_name: 'QA', last_name: 'Buyer', tier: 'C',
    company: 'Keep company', notes: 'Keep notes', target_zips: ['75201'],
    strategy: ['buy_hold'], property_types: ['SFR'],
    min_price: 100000, max_price: 250000, close_speed_days: 14, pof_amount: 300000,
    deals_closed: 7, active: true,
  };
});

function editBuyer() {
  fireEvent.click(screen.getByRole('button', { name: 'Actions for QA Buyer' }));
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }));
}

function renderBuyers() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><Buyers /></QueryClientProvider>);
  editBuyer();
}

it.each([
  ['Min Price', 'min_price'], ['Max Price', 'max_price'],
  ['Close Speed (days)', 'close_speed_days'], ['POF Amount', 'pof_amount'],
])('persists clearing %s as null through the update hook and preserves other buyer data', async (label, field) => {
  const before = { ...state.record };
  renderBuyers();
  fireEvent.change(screen.getByLabelText(label), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(screen.queryByLabelText('First Name *')).not.toBeInTheDocument());

  expect(state.update).toHaveBeenCalledWith('buyers', expect.objectContaining({ [field]: null }));
  expect(state.record).toMatchObject({ ...before, [field]: null });
  editBuyer();
  expect(screen.getByLabelText(label)).toHaveValue(null);
  expect(screen.getByLabelText('Company')).toHaveValue('Keep company');
  expect(screen.getByLabelText('Notes')).toHaveValue('Keep notes');
});

it('keeps stored zero amounts when editing an unrelated field', async () => {
  state.record.min_price = 0;
  state.record.pof_amount = 0;
  renderBuyers();
  expect(screen.getByLabelText('Min Price')).toHaveValue(0);
  expect(screen.getByLabelText('POF Amount')).toHaveValue(0);
  fireEvent.change(screen.getByLabelText('Company'), { target: { value: 'Updated company' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(state.record.company).toBe('Updated company'));
  expect(state.record).toMatchObject({ min_price: 0, pof_amount: 0, max_price: 250000 });
});
