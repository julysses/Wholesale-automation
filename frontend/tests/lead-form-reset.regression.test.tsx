import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock('@/hooks/useLeads', () => ({
  useLeads: () => ({ data: { data: [], count: 0 }, isLoading: false, error: null }),
  useCreateLead: () => ({ mutateAsync: mocks.create, isPending: false }),
  useDeleteLead: () => ({ mutate: vi.fn() }),
  useUpdateLead: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLogActivity: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/useDeals', () => ({ useCreateDeal: () => ({ mutateAsync: vi.fn() }) }));
vi.mock('@/hooks/useAIAgent', () => ({ useLeadQualifier: () => ({ qualify: vi.fn() }) }));
vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { Leads } from '@/pages/Leads';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.create.mockResolvedValue({ id: 'qa-lead' });
});

function openAdd() {
  fireEvent.click(screen.getByRole('button', { name: 'Add Lead', exact: true }));
}

function renderLeads() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter><Leads /></MemoryRouter></QueryClientProvider>);
  openAdd();
}

function fillDraft() {
  fireEvent.change(screen.getByLabelText('Property Address *'), { target: { value: 'QA draft address' } });
  fireEvent.change(screen.getByLabelText('City *'), { target: { value: 'Dallas' } });
  fireEvent.change(screen.getByLabelText('Seller Notes'), { target: { value: 'Previous draft notes' } });
}

function expectFreshForm() {
  expect(screen.getByLabelText('Property Address *')).toHaveValue('');
  expect(screen.getByLabelText('City *')).toHaveValue('');
  expect(screen.getByLabelText('Seller Notes')).toHaveValue('');
  expect(screen.getByLabelText('State')).toHaveValue('TX');
}

it('starts a fresh Add Lead form after cancelling a draft', () => {
  renderLeads();
  fillDraft();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true }));
  openAdd();
  expectFreshForm();
  expect(mocks.create).not.toHaveBeenCalled();
});

it('clears the successfully saved form so reopening cannot resubmit the previous lead', async () => {
  renderLeads();
  fillDraft();
  fireEvent.submit(screen.getByLabelText('Property Address *').closest('form')!);
  await waitFor(() => expect(screen.queryByLabelText('Property Address *')).not.toBeInTheDocument());
  expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ property_address: 'QA draft address', city: 'Dallas' }));
  openAdd();
  expectFreshForm();
  fireEvent.submit(screen.getByLabelText('Property Address *').closest('form')!);
  expect(mocks.create).toHaveBeenCalledTimes(1);
});
