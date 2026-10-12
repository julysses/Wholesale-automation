import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
    if (queryKey[0] === 'deal_analyses') return { data: { count: 1, data: [{
      id: 'analysis-qa', analyzed_at: '2026-10-12T12:00:00Z', property_address: 'Synthetic analysis', is_viable: true,
      arv_low: 400000, mao: 275000, projected_assignment_fee: 7777,
      offer_range_low: 210000, offer_range_high: 255000,
      summary: 'Historical suggested price $210,000',
    }] } };
    if (queryKey[0] === 'offer_recommendations') return { data: [{
      id: 'rec-qa', property_address: 'Synthetic research', opening_offer: 210000,
      target_offer: 235000, ceiling_offer: 255000,
      opening_script: 'Historical script', motivation_level: 'high',
    }] };
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

it('retains underwriting without presenting generated offers or projected fees', () => {
  render(<Acquisitions />);
  fireEvent.click(screen.getByRole('button', { name: /Deal Analysis/ }));
  expect(screen.getByText('$400,000')).toBeTruthy();
  expect(screen.getByText('$275,000')).toBeTruthy();
  expect(screen.getByText('MAO estimate')).toBeTruthy();
  expect(screen.queryByText(/210,000|255,000|7,777/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Review saved analysis' }));
  expect(screen.getByText(/Historical notes may contain retired/)).toBeTruthy();
});
it('does not present historical negotiation prices as current offer instructions', () => {
  render(<Acquisitions />);
  fireEvent.click(screen.getByRole('button', { name: /Negotiation/ }));
  expect(screen.getByText(/Saved negotiation research — not approved/)).toBeTruthy();
  expect(screen.queryByText(/210,000|235,000|255,000/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Review saved analysis' }));
  expect(screen.getByText(/Archived script — review required, do not send/)).toBeTruthy();
});
