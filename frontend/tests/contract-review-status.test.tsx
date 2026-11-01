import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractDocuments } from '../src/components/acquisition/ContractDocuments';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), fail: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error {} }));
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 1 };
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.fail = false;
  mock.fetch.mockImplementation(async (path: string) => {
    if (path.includes('/reviews/')) {
      if (mock.fail) throw new Error('Review unavailable');
      return { json: async () => ({ workspace_id: id(2), contract_id: id(6), contract_version: 1, kind: path.split('/').at(-1), sequence: 1, review_id: id(7), status: 'approved', approval_current: true, expires_at: new Date(Date.now() + 60000).toISOString(), checked_at: new Date().toISOString(), execution_authorized: false }) };
    }
    return { json: async () => path.endsWith('/memberships') ? [{ workspace_id: id(2), user_id: id(1), status: 'active', role: 'owner' }]
      : { workspace_id: id(2), contract_id: id(6), contract_version: 1, purpose: 'purchase_contract', current_policy: null, items: [], next_after: null, checked_at: new Date().toISOString(), execution_authorized: false, upload_enabled: false } };
  });
});
function open(disabled = false) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <ContractDocuments context={context} disabled={disabled} onPending={mock.pending} /></QueryClientProvider>);
}
it('checks only the selected review on demand and removes approval after a failed refresh', async () => {
  open(); const button = screen.getByRole('button', { name: 'Check purchase contract' });
  await waitFor(() => expect(button).toBeEnabled());
  expect(mock.fetch.mock.calls.some(([path]) => path.includes('/reviews/'))).toBe(false);
  fireEvent.click(button); await screen.findByText('Review current');
  expect(mock.fetch.mock.calls.filter(([path]) => path.includes('/reviews/'))[0][0]).toBe(`/api/acquisition/workspaces/${id(2)}/contracts/${id(6)}/versions/1/reviews/contract_review`);
  mock.fail = true; fireEvent.click(button);
  await screen.findByText(/Review could not be confirmed/);
  expect(screen.queryByText('Review current')).not.toBeInTheDocument();
  expect(mock.fetch.mock.calls.every(([, options]) => !options?.method || options.method === 'GET')).toBe(true);
});
it('holds all review checks when the saved contract context cannot be confirmed', () => {
  open(true);
  for (const name of ['Check purchase contract', 'Check title review', 'Check assignment basis']) expect(screen.getByRole('button', { name })).toBeDisabled();
  expect(mock.fetch).not.toHaveBeenCalled();
});
