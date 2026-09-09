import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ api: vi.fn(), send: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('@/lib/outreachBatches', () => ({ sendOutreachBatches: mocks.send, outreachResultText: () => 'Provider results' }));
vi.mock('@/lib/supabase', () => ({ supabase: { from: () => {
  const query = {
    select: () => query,
    order: () => query,
    limit: () => Promise.resolve({ data: [], error: null }),
  };
  return query;
} } }));
vi.mock('@/hooks/useDeals', () => ({ useDeals: () => ({ data: [
  { id: 'deal-dallas', stage: 'under_contract', buyer_price: 150000, contract_price: 140000, arv: 230000, assignment_fee: 10000, lead: { property_address: '123 Dallas St', zip_code: '75201', property_type: 'SFR', bedrooms: 3, bathrooms: 2 } },
  { id: 'deal-houston', stage: 'under_contract', buyer_price: 190000, arv: 280000, assignment_fee: 15000, lead: { property_address: '456 Houston Rd', zip_code: '77001', property_type: 'duplex', bedrooms: 4, bathrooms: 3 } },
] }) }));
vi.mock('@/components/buyers/BuyerImportModal', () => ({ BuyerImportModal: () => null }));
vi.mock('@/components/buyers/BuyerProfileDrawer', () => ({ BuyerProfileDrawer: () => null }));
import { BuyerIntelligence } from '@/pages/BuyerIntelligence';

function match(id: string, name: string) {
  return { rank: 1, buyer_id: id, buyer_name: name, company: '', phone: '', email: '', ibie_score: 80, match_score: 90, zip_score: 30, price_score: 30, type_score: 30, tags: [], match_reasons: [] };
}
function response(matches: ReturnType<typeof match>[]) {
  return { ok: true, json: async () => ({ matches, total_matches: matches.length }) };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.api.mockResolvedValue(response([match('buyer-1', 'First Buyer'), match('buyer-2', 'Second Buyer')]));
  mocks.send.mockResolvedValue({ sent: 1, failed: 0, skipped: 0, dryRun: 0, logFailed: 0, unresolved: 0, unattempted: 0, interrupted: false });
});

async function openMatch(dealId: string) {
  fireEvent.change(screen.getByLabelText('Select Deal'), { target: { value: dealId } });
  fireEvent.click(screen.getByRole('button', { name: 'Find Buyers' }));
  await screen.findByText('First Buyer');
}

it('carries the selected property into outreach, resets drafts for new recipients, and clears the old deal', async () => {
  render(<BuyerIntelligence />);
  fireEvent.click(screen.getByRole('button', { name: 'Deal Match' }));
  await openMatch('deal-dallas');
  fireEvent.click(screen.getByText('First Buyer'));
  fireEvent.click(screen.getByRole('button', { name: 'Blast 1' }));
  expect((screen.getByLabelText('SMS Message') as HTMLTextAreaElement).value).toContain('75201');
  expect((screen.getByLabelText('SMS Message') as HTMLTextAreaElement).value).toContain('$150,000');
  fireEvent.change(screen.getByLabelText('SMS Message'), { target: { value: 'Old edited draft' } });
  fireEvent.click(screen.getByText('Second Buyer'));
  fireEvent.click(screen.getByRole('button', { name: 'Blast 2' }));
  expect(screen.getByLabelText('SMS Message')).not.toHaveValue('Old edited draft');

  fireEvent.change(screen.getByLabelText('Select Deal'), { target: { value: 'deal-houston' } });
  expect(screen.queryByLabelText('SMS Message')).not.toBeInTheDocument();
  expect(screen.queryByText('First Buyer')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Blast 2' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Find Buyers' }));
  await screen.findByText('First Buyer');
  fireEvent.click(screen.getByText('First Buyer'));
  fireEvent.click(screen.getByRole('button', { name: 'Blast 1' }));
  expect((screen.getByLabelText('SMS Message') as HTMLTextAreaElement).value).toContain('77001');
  fireEvent.click(screen.getByRole('button', { name: 'EMAIL', exact: true }));
  expect((screen.getByLabelText('Email Body') as HTMLTextAreaElement).value).toContain('456 Houston Rd');
  fireEvent.click(screen.getByRole('button', { name: 'Send EMAIL to 1 Buyers' }));
  await waitFor(() => expect(mocks.send).toHaveBeenCalledTimes(1));
  expect(mocks.send.mock.calls[0][3]).toMatchObject({ deal_id: 'deal-houston', property_address: '456 Houston Rd', zip_code: '77001', price: 190000, arv: 280000, assignment_fee: 15000, property_type: 'duplex', beds: 4, baths: 3 });
});

it('ignores an old deal match response after another deal has been selected', async () => {
  let resolveOld!: (value: ReturnType<typeof response>) => void;
  mocks.api.mockReturnValueOnce(new Promise<ReturnType<typeof response>>((resolve) => { resolveOld = resolve; }));
  mocks.api.mockResolvedValueOnce(response([match('current-buyer', 'Current Buyer')]));
  render(<BuyerIntelligence />);
  fireEvent.click(screen.getByRole('button', { name: 'Deal Match' }));
  fireEvent.change(screen.getByLabelText('Select Deal'), { target: { value: 'deal-dallas' } });
  fireEvent.click(screen.getByRole('button', { name: 'Find Buyers' }));
  const oldSignal = mocks.api.mock.calls[0][1].signal as AbortSignal;
  fireEvent.change(screen.getByLabelText('Select Deal'), { target: { value: 'deal-houston' } });
  expect(oldSignal.aborted).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Find Buyers' }));
  await screen.findByText('Current Buyer');
  await act(async () => { resolveOld(response([match('old-buyer', 'Old Buyer')])); });
  expect(screen.queryByText('Old Buyer')).not.toBeInTheDocument();
  expect(screen.getByText('Current Buyer')).toBeInTheDocument();
});
