import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({ api: vi.fn(), actor: '00000000-0000-4000-8000-000000000001' }));
vi.mock('@/lib/api', () => ({ apiFetch: state.api }));
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession: async () => ({ data: { session: { user: { id: state.actor } } }, error: null }) } } }));
import { BuyerAnalysisPanel } from '@/components/buyers/BuyerAnalysisPanel';
const buyer = '00000000-0000-4000-8000-000000000002';
const response = (value: unknown) => new Response(JSON.stringify(value));
let reference = '';
const receipt = (fields = {}) => ({ id: reference, state: 'running', kind: 'classify', selected_buyer: buyer,
  total: 1, processed: 0, applied: 0, failed: 0, stale: 0, missing: 0, unknown: 0, blocked: 0, held: 0, ready: 0, pending: 1,
  can_run: true, offset: 0, items: [], ...fields });
beforeEach(() => {
  vi.restoreAllMocks(); state.api.mockReset(); sessionStorage.clear(); state.actor = '00000000-0000-4000-8000-000000000001'; reference = '';
  state.api.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/config')) return response({ configured: true });
    if (path.endsWith('/start')) { reference = JSON.parse(String(init?.body)).request_id; return response(receipt()); }
    return response(receipt());
  });
});
async function prepare() {
  fireEvent.click(screen.getByText('Prepare AI classification'));
  await screen.findByRole('checkbox');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Create analysis request'));
  await screen.findByText('Run one AI classification');
}
it('does no work on mount, and preparation never runs paid analysis automatically', async () => {
  render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />);
  expect(state.api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Prepare AI classification'));
  expect(await screen.findByText('Create analysis request')).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByText('Create analysis request'));
  await screen.findByText('Run one AI classification');
  expect(state.api.mock.calls.some(([path]) => path.endsWith('/run'))).toBe(false);
  const body = JSON.parse(state.api.mock.calls.find(([path]) => path.endsWith('/start'))![1].body);
  expect(body.paid_confirmed).toBe(true); expect(body.buyer_id).toBe(buyer);
  expect(sessionStorage.length).toBe(1);
});
it('lost paid response retains the same reference across reopening and never reruns automatically', async () => {
  const view = render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />); await prepare();
  state.api.mockRejectedValueOnce(new Error('Synthetic response loss'));
  fireEvent.click(screen.getByText('Run one AI classification'));
  await screen.findByRole('alert');
  expect(screen.queryByText('Run one AI classification')).not.toBeInTheDocument();
  const saved = reference; view.unmount();
  state.api.mockImplementation(async (path: string) => path.endsWith('/config') ? response({ configured: true }) : response(receipt({ state: 'review', held: 1, can_run: false })));
  render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />);
  fireEvent.click(screen.getByText('Prepare AI classification'));
  await screen.findByText(/provider outcomes need review/);
  expect(screen.getByText(`Reference: ${saved}`)).toBeInTheDocument();
  expect(state.api.mock.calls.filter(([path]) => path.endsWith('/run'))).toHaveLength(1);
});
it('cannot write when durable browser storage is unavailable', async () => {
  render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />);
  fireEvent.click(screen.getByText('Prepare AI classification')); await screen.findByRole('checkbox');
  fireEvent.click(screen.getByRole('checkbox'));
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Synthetic storage blocked'); });
  fireEvent.click(screen.getByText('Create analysis request'));
  await screen.findByRole('alert');
  expect(state.api.mock.calls.some(([path]) => path.endsWith('/start'))).toBe(false);
});
it('rejects another request receipt and checks read-only without running', async () => {
  render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />); await prepare();
  state.api.mockResolvedValueOnce(response(receipt({ id: buyer })));
  fireEvent.click(screen.getByText('Check saved status'));
  await screen.findByRole('alert');
  expect(screen.queryByText('Run one AI classification')).not.toBeInTheDocument();
  expect(state.api.mock.calls.filter(([path]) => path.endsWith('/run'))).toHaveLength(0);
});
it('rechecks the operator before paid work', async () => {
  render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />); await prepare();
  state.actor = buyer;
  fireEvent.click(screen.getByText('Run one AI classification'));
  await screen.findByRole('alert');
  expect(state.api.mock.calls.some(([path]) => path.endsWith('/run'))).toBe(false);
});
it('retained results can be applied with unavailable AI configuration', async () => {
  const view = render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />); await prepare();view.unmount();
  state.api.mockImplementation(async (path: string) => path.endsWith('/config') ? response({ configured: false }) : response(receipt({ ready: 1 })));
  render(<BuyerAnalysisPanel kind="classify" buyerId={buyer} />);fireEvent.click(screen.getByText('Prepare AI classification'));
  await screen.findByText('Apply saved result');
  await waitFor(() => expect(screen.getByText('Apply saved result')).toBeEnabled());
});
