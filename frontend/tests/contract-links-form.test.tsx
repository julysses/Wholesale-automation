import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractLinksForm } from '../src/components/acquisition/ContractLinksForm';
import { emptyTerms } from '../src/lib/acquisition/contract-terms';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, reject: false, revoked: false, termSource: false, stale: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedLink = true; } }));
import { ApiError } from '../src/lib/api';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), contractId: id(3), contractVersion: 2, leadId: id(4), propertyId: id(5), offerId: id(6) };
beforeEach(() => { sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.lose = false; mock.reject = false; mock.revoked = false; mock.termSource = false; mock.stale = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Denied', 409); if (mock.lose) throw new Error('Lost reply'); const body = JSON.parse(init.body as string);
      return { json: async () => path.endsWith('/withdrawals') ? { workspace_id: id(2), contract_id: id(3), contract_version: 2, link_id: id(11), revocation_id: body.id, duplicate: false, execution_authorized: false }
        : { workspace_id: id(2), contract_id: id(3), contract_version: 2, link_id: body.id, source_version: 1, artifact_id: id(8), duplicate: false, review_approved: false, execution_authorized: false } };
    }
    if (path.includes('/versions?')) return { json: async () => ({ workspace_id: id(2), contract_id: id(3), next_after: null, execution_authorized: false,
      items: [1, 2].map(n => ({ id: id(20 + n), workspace_id: id(2), deal_id: id(3), version: n, status: 'draft', previous_version: n === 1 ? null : 1,
        terms: n === 1 ? null : { ...emptyTerms(), note: 'Unknown draft terms retained for this test.' }, actor_id: id(1), created_at: '2026-10-31T22:00:00Z' })) }) };
    const version = path.includes('/versions/1/') ? 1 : 2, checked = mock.stale ? '2020-01-01T00:00:00Z' : new Date().toISOString();
    return { json: async () => ({ workspace_id: id(2), contract_id: id(3), contract_version: version, purpose: 'purchase_contract', checked_at: checked, next_after: null, execution_authorized: false,
      items: [{ workspace_id: id(2), contract_id: id(3), contract_version: version, artifact_id: id(8), source_version: 1,
        reference_type: version === 1 ? 'native' : mock.termSource ? 'term_source' : 'linked', link_id: version === 1 || mock.termSource ? null : id(11),
        status: mock.revoked ? 'source_revoked' : 'available_for_review', purpose: 'purchase_contract', sha256: 'a'.repeat(64), verification_id: mock.revoked ? null : id(10),
        source_created_at: '2020-01-01T00:00:00Z', checked_at: checked, review_approved: false, execution_authorized: false }] }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ContractLinksForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function chooseLink() {
  fireEvent.click(screen.getByRole('button', { name: 'Choose an earlier document' })); await screen.findByRole('option', { name: /Version 1/ });
  fireEvent.change(screen.getByLabelText('Earlier contract version'), { target: { value: '1' } }); await screen.findByRole('option', { name: /Original version 1/ });
  fireEvent.change(screen.getByLabelText('Original document to reference'), { target: { value: id(8) } });
  fireEvent.change(screen.getByLabelText('Reason for this reference change'), { target: { value: 'This original document supports the changed contract version.' } });
}
const posts = () => mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
it('uses discovered original identity and does not copy a document or carry approval', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); await chooseLink(); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true));
  fireEvent.click(screen.getByRole('button', { name: 'Save document reference' })); await screen.findByText(/Original document referenced/);
  expect(posts()).toHaveLength(1); expect(JSON.parse(posts()[0][1].body)).toMatchObject({ source_version: 1, artifact_id: id(8), verification_id: id(10), sha256: 'a'.repeat(64) });
  expect(sessionStorage.length).toBe(0); expect(mock.saved).toHaveBeenCalledTimes(1); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('recovers the same reference after reload and retains uncertainty on later denial', async () => {
  mock.lose = true; const view = open(); await chooseLink(); fireEvent.click(screen.getByRole('button', { name: 'Save document reference' }));
  await screen.findByText(/Save is unconfirmed/); view.unmount(); mock.lose = false; mock.reject = true; open();
  fireEvent.click(await screen.findByRole('button', { name: 'Retry saved reference' })); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  mock.reject = false; fireEvent.click(screen.getByRole('button', { name: 'Retry saved reference' })); await screen.findByText(/Original document referenced/);
  expect(posts()).toHaveLength(3); expect(new Set(posts().map(call => call[1].body)).size).toBe(1); expect(sessionStorage.length).toBe(0);
});
it('withdraws an explicit link after source revocation, without requiring fresh approval', async () => {
  mock.revoked = true; open(); fireEvent.click(screen.getByRole('button', { name: 'Withdraw a reference' })); await screen.findByRole('option', { name: /Original version 1/ });
  fireEvent.change(screen.getByLabelText('Reference to withdraw'), { target: { value: id(8) } }); fireEvent.change(screen.getByLabelText('Reason for this reference change'), { target: { value: 'This reference no longer supports the changed contract terms.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm reference withdrawal' })); await screen.findByText(/Reference withdrawn. The original document/);
  expect(posts()[0][0]).toContain(`/document-links/${id(11)}/withdrawals`); expect(JSON.parse(posts()[0][1].body)).not.toHaveProperty('artifact_id');
});
it('does not offer term citations as independently withdrawable links', async () => {
  mock.termSource = true; open(); fireEvent.click(screen.getByRole('button', { name: 'Withdraw a reference' }));
  await waitFor(() => expect(mock.fetch).toHaveBeenCalled()); expect(screen.queryByRole('option', { name: /Original version/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Confirm reference withdrawal' })).toBeDisabled();
});
it('releases only a definitively rejected first attempt', async () => {
  mock.reject = true; open(); await chooseLink(); fireEvent.click(screen.getByRole('button', { name: 'Save document reference' }));
  await screen.findByText(/The reference change was not saved/); expect(sessionStorage.length).toBe(0); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('cancel releases the editing hold without any write', async () => {
  open(); await chooseLink(); fireEvent.click(screen.getByRole('button', { name: 'Cancel unsaved reference change' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false)); expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});
it('does not read or mutate while a sibling workflow holds the contract', () => {
  open(true); expect(screen.getByRole('button', { name: 'Choose an earlier document' })).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled();
});
