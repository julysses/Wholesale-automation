import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractReviewForm } from '../src/components/acquisition/ContractReviewForm';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), lose: false, reject: false, withdrawable: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 409; rejectedReview = true; } }));
import { ApiError } from '../src/lib/api';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 1 };
const stamp = (delta = 0) => new Date(Date.now() + delta).toISOString();
const scope = { workspace_id: id(2), contract_id: id(6), contract_version: 1 };
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.lose = false; mock.reject = false; mock.withdrawable = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Rejected', 409);
      if (mock.lose) throw new Error('Lost reply');
      const body = JSON.parse(init.body as string);
      return { json: async () => ({ ...scope, kind: 'contract_review', review_id: body.id, sequence: body.expected_sequence + 1, status: body.status,
        duplicate: false, review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    const checked = stamp();
    if (path.endsWith('/candidate')) return { json: async () => ({ ...scope, kind: 'contract_review', artifact_id: id(7), purpose: 'purchase_contract',
      status: 'ready_for_human_review', candidate: { artifact_id: id(7), verification_id: id(8), sha256: 'a'.repeat(64), policy_id: id(9), expected_sequence: mock.withdrawable ? 1 : 0, max_expires_at: stamp(600000) },
      withdrawal: mock.withdrawable ? { review_id: id(10), artifact_id: id(7), verification_id: id(8), policy_id: id(9), expected_sequence: 1 } : null, current_review: { ...scope, kind: 'contract_review', sequence: mock.withdrawable ? 1 : 0, review_id: mock.withdrawable ? id(10) : null, status: mock.withdrawable ? 'requires_review' : 'not_reviewed', approval_current: false, expires_at: null, checked_at: checked, execution_authorized: false }, checked_at: checked, execution_authorized: false }) };
    return { json: async () => ({ ...scope, purpose: 'purchase_contract', current_policy: null, next_after: null, upload_enabled: false, execution_authorized: false, checked_at: checked,
      items: [{ ...scope, artifact_id: id(7), purpose: 'purchase_contract', expected_sha256: 'a'.repeat(64), expected_byte_size: 123, media_type: 'application/pdf', retention_policy_id: id(9), created_at: stamp(-60000), retain_until: stamp(600000), revoked_at: null, checked_at: checked, status: 'pending_verification', bytes_verified: false, legal_review_approved: false, execution_authorized: false }] }) };
  });
});
function open() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ContractReviewForm context={context} disabled={false} onPending={mock.pending}/></QueryClientProvider>); }
async function prepare() {
  await screen.findByRole('option', { name: /123 bytes/ });
  fireEvent.change(screen.getByLabelText('Document to review'), { target: { value: id(7) } });
  await screen.findByText(/Document and reviewer checks passed/);
  fireEvent.change(screen.getByLabelText('Review notes'), { target: { value: 'Personally reviewed the exact original contract and its provisions.' } });
  fireEvent.click(screen.getByRole('checkbox'));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Record reviewed approval' })).toBeEnabled());
}
const posts = () => mock.fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
it('requires personal review and records an exact decision without execution', async () => {
  open(); expect(screen.getByRole('button', { name: 'Record reviewed approval' })).toBeDisabled();
  await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Record reviewed approval' }));
  await screen.findByText(/Review decision recorded/);
  expect(posts()).toHaveLength(1); expect(JSON.parse(posts()[0][1].body)).toMatchObject({ artifact_id: id(7), verification_id: id(8), policy_id: id(9), expected_sequence: 0, personally_reviewed: true });
  expect(sessionStorage.length).toBe(0); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
  fireEvent.change(screen.getByLabelText('Review notes'), { target: { value: 'Start another decision without the previous success message.' } });
  expect(screen.queryByText(/Review decision recorded/)).not.toBeInTheDocument();
});
it('recovers exactly after reload and does not discard an uncertain save after later rejection', async () => {
  mock.lose = true; const view = open(); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Record reviewed approval' }));
  await screen.findByText(/Save is unconfirmed/); const original = posts()[0][1].body; view.unmount();
  mock.lose = false; mock.reject = true; open(); fireEvent.click(screen.getByRole('button', { name: 'Retry saved review' }));
  await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  mock.reject = false; fireEvent.click(screen.getByRole('button', { name: 'Retry saved review' }));
  await screen.findByText(/Review decision recorded/);
  expect(posts().every(([, init]) => init.body === original)).toBe(true); expect(sessionStorage.length).toBe(0);
});
it('unlocks only a definitively rejected first attempt', async () => {
  mock.reject = true; open(); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Record reviewed approval' }));
  await screen.findByText(/The review was not saved/); expect(sessionStorage.length).toBe(0);
});

it('withdraws the exact prior decision without a renewed personal-review attestation', async () => {
  mock.withdrawable = true; open();
  await screen.findByRole('option', { name: /123 bytes/ });
  fireEvent.change(screen.getByLabelText('Document to review'), { target: { value: id(7) } });
  await screen.findByText(/Document and reviewer checks passed/);
  fireEvent.change(screen.getByLabelText('Review notes'), { target: { value: 'Withdraw my prior decision pending updated title information.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Withdraw my review' }));
  await screen.findByText(/Review decision recorded/);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ status: 'withdrawn', expected_sequence: 1, personally_reviewed: false, expires_at: null });
});
