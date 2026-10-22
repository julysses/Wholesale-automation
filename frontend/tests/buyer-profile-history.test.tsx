import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
import { BuyerProfileDrawer } from '@/components/buyers/BuyerProfileDrawer';
const buyer = (id: string) => ({ id, first_name: id, last_name: 'QA', tags: [] });
function response(id: string, count = 1) {
  return { ok: true, json: async () => ({ buyer_id: id, total: count,
    transactions: Array.from({ length: count }, (_, n) => ({ id: `${id}-${n}`, buyer_id: id, property_address: `${id} purchase ${n}`, purchase_price: 0 })) }) };
}
function mount(id = 'A') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const element = (key: string) => <QueryClientProvider client={client}><BuyerProfileDrawer key={key} buyer={buyer(key)} open onClose={() => {}} /></QueryClientProvider>;
  const view = render(element(id));
  return { client, change: (key: string) => view.rerender(element(key)) };
}
beforeEach(() => { mocks.api.mockReset(); });
it('cannot place a late purchase response under another buyer', async () => {
  let resolve!: (value: ReturnType<typeof response>) => void;
  mocks.api.mockReturnValueOnce(new Promise(resolveValue => { resolve = resolveValue; }));
  mocks.api.mockResolvedValueOnce(response('B'));
  const view = mount();
  const signal = mocks.api.mock.calls[0][1].signal;
  view.change('B');
  expect(signal.aborted).toBe(true);
  await screen.findByText('B purchase 0');
  await act(async () => { resolve(response('A')); });
  expect(screen.queryByText('A purchase 0')).not.toBeInTheDocument();
});
it('retains same-buyer confirmed history on refresh failure and retries explicitly', async () => {
  mocks.api.mockResolvedValueOnce(response('A', 26));
  const { client } = mount();
  await screen.findByText('A purchase 0');
  expect(screen.queryByText('A purchase 25')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next purchases' }));
  expect(screen.getByText('A purchase 25')).toBeInTheDocument();
  mocks.api.mockRejectedValueOnce(new Error('Offline'));
  await act(async () => { await client.invalidateQueries({ queryKey: ['buyer_transactions'] }); });
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.getByText('A purchase 25')).toBeInTheDocument();
  mocks.api.mockResolvedValueOnce(response('A', 0));
  fireEvent.click(screen.getByRole('button', { name: 'Retry purchase history' }));
  await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(screen.queryByText('A purchase 25')).not.toBeInTheDocument();
});
it.each(['foreign buyer', 'wrong row', 'incomplete', 'duplicate'])('rejects %s purchase evidence without presenting empty history', async kind => {
  const data = await response('A', 2).json();
  if (kind === 'foreign buyer') data.buyer_id = 'B';
  if (kind === 'wrong row') data.transactions[0].buyer_id = 'B';
  if (kind === 'incomplete') data.total = 3;
  if (kind === 'duplicate') data.transactions[1].id = data.transactions[0].id;
  mocks.api.mockResolvedValueOnce({ ok: true, json: async () => data });
  mount();
  await screen.findByRole('alert');
  expect(screen.queryByText('A purchase 0')).not.toBeInTheDocument();
  expect(screen.queryByText('No transactions found')).not.toBeInTheDocument();
});
