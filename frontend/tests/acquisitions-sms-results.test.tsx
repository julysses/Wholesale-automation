import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('@/lib/supabase', () => ({ supabase: {} }));
vi.mock('@/components/dashboard/StrategyComparisonPanel', () => ({ StrategyComparisonPanel: () => null }));
const leads = Array.from({ length: 6 }, (_, i) => ({
  id: `lead-${i}`, property_address: `${i} Test St`, city: 'Dallas', state: 'TX', zip_code: '75201',
  qual: { classification: 'WARM', qualification_score: 65 },
}));
vi.mock('@tanstack/react-query', () => ({
  useQuery: (options: { queryKey: string[]; select?: (rows: typeof leads) => unknown }) => ({
    data: options.queryKey[0] === 'acquisition_leads' ? options.select?.(leads) ?? leads : [],
    isLoading: false, refetch: vi.fn(),
  }),
}));
import { Acquisitions } from '@/pages/Acquisitions';

beforeEach(() => {
  mocks.api.mockReset();
  vi.stubGlobal('confirm', vi.fn(() => true));
  vi.stubGlobal('alert', vi.fn());
});

it('retains partial WARM send results and locks the bulk button after an interrupted batch', async () => {
  mocks.api.mockResolvedValueOnce({ json: async () => ({ sent_count: 5, failed_count: 0, skipped_count: 0, dry_run_count: 0, log_failed_count: 1 }) });
  mocks.api.mockRejectedValueOnce(new Error('Network interrupted'));
  render(<Acquisitions />);
  fireEvent.click(screen.getByRole('button', { name: /WARM Leads/ }));
  const send = screen.getByRole('button', { name: 'Bulk SMS All Warm Leads' });
  fireEvent.click(send);
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('5 accepted by provider'));
  expect(screen.getByRole('alert')).toHaveTextContent('1 activity-log updates failed');
  expect(screen.getByRole('alert')).toHaveTextContent('1 recipients have unknown results');
  expect(send).toBeDisabled();
  expect(JSON.parse(mocks.api.mock.calls[0][1].body).lead_ids).toEqual(leads.slice(0, 5).map(lead => lead.id));
  expect(mocks.api).toHaveBeenCalledTimes(2);
});
