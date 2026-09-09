import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import type { Lead } from '@/types';

const state = vi.hoisted(() => ({
  record: {} as Record<string, unknown>,
  update: vi.fn(),
  error: null as { message: string } | null,
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
                if (column !== 'id' || id !== state.record.id) throw new Error('Wrong lead updated');
                for (const field of ['id', 'created_at', 'updated_at', 'total_score', 'seller_score',
                  'contact_attempts', 'dnc', 'ai_calling_paused', 'sms_sequence_active']) {
                  if (field in payload) throw new Error(`Server-managed field submitted: ${field}`);
                }
                if (state.error) return { data: null, error: state.error };
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
vi.mock('@/hooks/useLeads', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/hooks/useLeads')>(),
  useLeads: () => ({ data: { data: [state.record as unknown as Lead], count: 1 }, isLoading: false, error: null }),
}));
vi.mock('@/hooks/useDeals', () => ({ useCreateDeal: () => ({ mutateAsync: vi.fn() }) }));
vi.mock('@/hooks/useAIAgent', () => ({ useLeadQualifier: () => ({ qualify: vi.fn() }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { Leads } from '@/pages/Leads';

beforeEach(() => {
  vi.clearAllMocks();
  state.error = null;
  state.record = {
    id: 'qa-lead', created_at: '2026-09-01', updated_at: '2026-09-08',
    property_address: 'QA drawer address', city: 'Dallas', state: 'TX', status: 'new',
    owner_first_name: 'Ana', internal_notes: null, seller_notes: 'Keep seller notes',
    asking_price: 100000, estimated_equity_pct: 50, next_follow_up_date: '2026-09-15',
    score_motivation: 1, score_timeline: 2, score_equity: 3, score_condition: 1, score_flexibility: 2,
    total_score: 9, seller_score: 75, contact_attempts: 0, dnc: false, ai_calling_paused: false,
    sms_sequence_active: false, email_sequence_active: false,
  };
});

function renderDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><Leads /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(screen.getByText('QA drawer address'));
}

async function save() {
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(screen.queryByLabelText('Internal Notes')).not.toBeInTheDocument());
}

it('saves only changed editable fields and preserves concurrent automation updates', async () => {
  renderDrawer();
  fireEvent.change(screen.getByLabelText('Internal Notes'), { target: { value: 'QA edited note' } });
  fireEvent.change(screen.getByLabelText('Owner First'), { target: { value: 'Temporary change' } });
  fireEvent.change(screen.getByLabelText('Owner First'), { target: { value: 'Ana' } });
  // A webhook updates this record after the drawer opened.
  state.record = { ...state.record, status: 'hot', score_motivation: 3, total_score: 11,
    seller_score: 95, contact_attempts: 4, dnc: true, ai_calling_paused: true };
  await save();
  expect(state.update).toHaveBeenCalledWith('leads', { internal_notes: 'QA edited note' });
  expect(state.record).toMatchObject({ internal_notes: 'QA edited note', seller_notes: 'Keep seller notes',
    status: 'hot', total_score: 11, seller_score: 95, score_motivation: 3, contact_attempts: 4,
    dnc: true, ai_calling_paused: true, owner_first_name: 'Ana' });
});

it('retains a rejected draft, shows the database error, and retries only its edits', async () => {
  state.error = { message: 'Database write unavailable' };
  renderDrawer();
  fireEvent.change(screen.getByLabelText('Internal Notes'), { target: { value: 'Retry this draft' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Database write unavailable'));
  expect(screen.getByLabelText('Internal Notes')).toHaveValue('Retry this draft');
  expect(state.record.internal_notes).toBeNull();
  state.error = null;
  await save();
  expect(state.update).toHaveBeenCalledTimes(2);
  expect(state.update).toHaveBeenLastCalledWith('leads', { internal_notes: 'Retry this draft' });
  expect(state.record.internal_notes).toBe('Retry this draft');
});

it('persists cleared nullable amounts and follow-up date as null', async () => {
  renderDrawer();
  for (const label of ['Asking Price', 'Est. Equity %', 'Next Follow-up']) {
    fireEvent.change(screen.getByLabelText(label), { target: { value: '' } });
  }
  await save();
  expect(state.update).toHaveBeenCalledWith('leads', {
    asking_price: null, estimated_equity_pct: null, next_follow_up_date: null,
  });
  expect(state.record).toMatchObject({ asking_price: null, estimated_equity_pct: null,
    next_follow_up_date: null, status: 'new', seller_notes: 'Keep seller notes' });
});

it('displays stored zeros and leaves them untouched when saving a note', async () => {
  state.record.asking_price = 0;
  state.record.estimated_equity_pct = 0;
  renderDrawer();
  expect(screen.getByLabelText('Asking Price')).toHaveValue(0);
  expect(screen.getByLabelText('Est. Equity %')).toHaveValue(0);
  fireEvent.change(screen.getByLabelText('Internal Notes'), { target: { value: 'Keep zero amounts' } });
  await save();
  expect(state.update).toHaveBeenCalledWith('leads', { internal_notes: 'Keep zero amounts' });
  expect(state.record).toMatchObject({ asking_price: 0, estimated_equity_pct: 0 });
});

it('saves a manually edited score without submitting the generated total', async () => {
  renderDrawer();
  fireEvent.click(screen.getByRole('button', { name: 'Motivation score 3' }));
  expect(screen.getByText('11 / 15')).toBeInTheDocument();
  await save();
  expect(state.update).toHaveBeenCalledWith('leads', { score_motivation: 3 });
  expect(state.record.score_motivation).toBe(3);
});
