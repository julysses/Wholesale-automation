import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('@/components/dashboard/StrategyComparisonPanel', () => ({ StrategyComparisonPanel: () => null }));
vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey, select }: { queryKey: string[]; select?: (rows: unknown[]) => unknown }) => {
    const rows = queryKey[0] === 'acquisition_leads' ? [{
      id: 'qa', property_address: 'Synthetic Property', city: 'Dallas', state: 'TX', zip_code: '75201',
      owner_first_name: 'Test', owner_last_name: 'Owner',
      qual: { classification: 'HOT', qualification_score: 85, asking_price: 300000,
        offer_range_low: 210000, offer_range_high: 255000, key_quotes: [] },
    }] : [];
    return { data: select ? select(rows) : rows, refetch: vi.fn() };
  },
}));
import { Acquisitions } from '@/pages/Acquisitions';
afterEach(cleanup);
it('shows seller asking price without resurfacing a historical qualification offer range', () => {
  render(<Acquisitions />);
  expect(screen.getByText('$300,000')).toBeTruthy();
  expect(screen.queryByText('Offer range')).toBeNull();
  expect(screen.queryByText(/210,000|255,000/)).toBeNull();
});
