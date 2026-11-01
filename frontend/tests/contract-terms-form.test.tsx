import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractTermsForm } from '../src/components/acquisition/ContractTermsForm';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, reject: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedTerms = true; } }));
import { ApiError } from '../src/lib/api';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), contractId: id(3), contractVersion: 1, leadId: id(4), propertyId: id(5), offerId: id(6) };
beforeEach(() => { sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.lose = false; mock.reject = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Denied', 409);
      if (mock.lose) throw new Error('Lost reply');
      const body = JSON.parse(init.body as string);
      return { json: async () => ({ request_id: body.id, workspace_id: id(2), contract_id: id(3), version: 2, status: 'draft', duplicate: false, execution_authorized: false }) };
    }
    if (path.includes('/versions?')) return { json: async () => ({ workspace_id: id(2), contract_id: id(3), next_after: null, execution_authorized: false,
      items: [{ id: id(9), workspace_id: id(2), deal_id: id(3), version: 1, status: 'draft', previous_version: null, terms: null, actor_id: id(1), created_at: '2026-10-31T22:00:00Z' }] }) };
    const checked = new Date().toISOString();
    return { json: async () => ({ workspace_id: id(2), contract_id: id(3), contract_version: 1, purpose: 'purchase_contract', checked_at: checked, next_after: null, execution_authorized: false,
      items: [{ workspace_id: id(2), contract_id: id(3), contract_version: 1, artifact_id: id(8), source_version: 1, reference_type: 'native', link_id: null,
        status: 'available_for_review', purpose: 'purchase_contract', sha256: 'a'.repeat(64), verification_id: id(10), source_created_at: '2026-10-31T22:00:00Z', checked_at: checked, review_approved: false, execution_authorized: false }] }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ContractTermsForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function edit() { await waitFor(() => expect(screen.getByRole('button', { name: 'Edit draft terms' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: 'Edit draft terms' })); fireEvent.change(screen.getByLabelText('Reason for this version'), { target: { value: 'Prepared exact draft terms from the source contract.' } }); }
const posts = () => mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
it('saves unknown fields as null and prevents another version until refreshed', async () => {
  open(); await edit(); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); fireEvent.click(screen.getByRole('button', { name: 'Save new draft version' }));
  await screen.findByText(/New draft version saved/); expect(posts()).toHaveLength(1);
  expect(JSON.parse(posts()[0][1].body).terms).toMatchObject({ purchase_price_cents: null, earnest_money_cents: null, assignment_allowed: null, effective: { precision: 'unknown' } });
  expect(mock.saved).toHaveBeenCalledTimes(1); expect(sessionStorage.length).toBe(0);
});
it('requires a source and preserves exact cents and original document identity', async () => {
  open(); await edit(); fireEvent.change(screen.getByLabelText('Purchase price ($)'), { target: { value: '123456.29' } });
  expect(screen.getByRole('button', { name: 'Save new draft version' })).toBeDisabled();
  await screen.findByRole('option', { name: /Source version 1/ });
  fireEvent.change(screen.getByLabelText('Original source document'), { target: { value: id(8) } });
  fireEvent.change(screen.getByLabelText('Page or clause reference'), { target: { value: 'Page 1, purchase price clause' } });
  fireEvent.click(screen.getByRole('button', { name: 'Attach source to term' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save new draft version' })); await screen.findByText(/New draft version saved/);
  expect(JSON.parse(posts()[0][1].body).terms).toMatchObject({ purchase_price_cents: 12345629, sources: [{ term: 'purchase_price', artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64) }] });
});
it('recovers byte-identical terms after reload and keeps a later rejection uncertain', async () => {
  mock.lose = true; const view = open(); await edit(); fireEvent.click(screen.getByRole('button', { name: 'Save new draft version' }));
  await screen.findByText(/Save is unconfirmed/); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); view.unmount();
  mock.lose = false; mock.reject = true; open(); fireEvent.click(await screen.findByRole('button', { name: 'Retry saved terms' }));
  await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  mock.reject = false; fireEvent.click(screen.getByRole('button', { name: 'Retry saved terms' })); await screen.findByText(/New draft version saved/);
  expect(posts()).toHaveLength(3); expect(new Set(posts().map(call => call[1].body)).size).toBe(1); expect(sessionStorage.length).toBe(0);
});
it('clears only a first-attempt explicit rejection', async () => {
  mock.reject = true; open(); await edit(); fireEvent.click(screen.getByRole('button', { name: 'Save new draft version' }));
  await screen.findByText(/The terms were not saved/); expect(sessionStorage.length).toBe(0); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('makes no reads or writes while another workflow owns the hold', () => {
  open(true); expect(screen.getByRole('button', { name: 'Edit draft terms' })).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled();
});

it('releases the unsaved editing hold when the operator discards changes', async () => {
  open(); await edit(); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true));
  fireEvent.click(screen.getByRole('button', { name: 'Discard unsaved edits' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false)); expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});
