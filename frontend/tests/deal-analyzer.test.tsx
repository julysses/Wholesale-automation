import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ api: vi.fn(), save: vi.fn(), update: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('sonner', () => ({ toast: { success: mocks.success, error: mocks.error } }));
vi.mock('@/hooks/useLeads', () => ({ useLeads: () => ({ data: { data: [{ id: 'lead-1', property_address: 'Test Property' }] } }) }));
vi.mock('@/lib/supabase', () => ({ supabase: {
  from: (table: string) => table === 'deal_analyses'
    ? { insert: mocks.save }
    : { update: mocks.update },
} }));
import { DealAnalyzer } from '@/pages/DealAnalyzer';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.save.mockReturnValue({ select: () => ({ single: async () => ({ data: { id: 'analysis-1' }, error: null }) }) });
  mocks.update.mockReturnValue({ eq: () => ({ select: () => ({ single: async () => ({ error: null }) }) }) });
  render(<QueryClientProvider client={new QueryClient()}><DealAnalyzer /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText('ARV Override'), { target: { value: '250000' } });
});

it('saves a shared analysis and re-enables the save button', async () => {
  fireEvent.change(screen.getByLabelText('Select Lead'), { target: { value: 'lead-1' } });
  const save = screen.getByRole('button', { name: /Save ARV/ });
  fireEvent.click(save);
  await waitFor(() => expect(mocks.success).toHaveBeenCalledWith('Analysis saved to lead and Acquisitions'));
  expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ lead_id: 'lead-1', arv_mid: 250000 }));
  expect(save).toBeEnabled();
});

it('shows a save failure and allows retry', async () => {
  mocks.save.mockReturnValue({ select: () => ({ single: async () => ({ error: new Error('Save failed') }) }) });
  fireEvent.change(screen.getByLabelText('Select Lead'), { target: { value: 'lead-1' } });
  const save = screen.getByRole('button', { name: /Save ARV/ });
  fireEvent.click(save);
  await waitFor(() => expect(mocks.error).toHaveBeenCalledWith('Save failed'));
  expect(save).toBeEnabled();
  expect(mocks.success).not.toHaveBeenCalled();
});

it('reports AI failure without inventing a recommendation', async () => {
  mocks.api.mockRejectedValue(new Error('AI is unavailable'));
  fireEvent.click(screen.getByRole('button', { name: 'Get AI Take' }));
  await waitFor(() => expect(mocks.error).toHaveBeenCalledWith('AI is unavailable'));
  expect(screen.queryByText(/Your numbers look solid/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Get AI Take' })).toBeEnabled();
});
