import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ExecutionReviewForm } from '../src/components/acquisition/ExecutionReviewForm';
import { executionKey, preserveExecution, type PendingExecution } from '../src/lib/acquisition/execution-review';
import { emptyTerms } from '../src/lib/acquisition/contract-terms';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), reject: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedExecution = true; } }));
import { ApiError } from '../src/lib/api';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
const scope = { workspace_id: id(2), contract_id: id(6), contract_version: 2 };
const saved: PendingExecution = { version: 1, context, request: { id: id(7), expected_version: 2, expected_sequence: 1, status: 'withdrawn', artifact_id: id(8), verification_id: id(9), policy_id: id(10), expires_at: null, personally_reviewed: false, findings: null, note: 'Withdraw the exact previously reviewed agreement.' } };
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.reject = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    const stamp = new Date().toISOString();
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Denied', 403);
      const body = JSON.parse(init.body as string);
      return { json: async () => ({ ...scope, kind: 'executed_contract', review_id: body.id, sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    if (path.includes('/references?')) return { json: async () => ({ ...scope, purpose: 'purchase_contract', items: [{ ...scope, artifact_id: id(8), source_version: 2, reference_type: 'native', link_id: null, status: 'available_for_review', purpose: 'purchase_contract', sha256: 'a'.repeat(64), verification_id: id(9), source_created_at: stamp, checked_at: stamp, review_approved: false, execution_authorized: false }], next_after: null, checked_at: stamp, execution_authorized: false }) };
    return { json: async () => ({ ...scope, artifact_id: id(8), status: 'ready_for_human_review', candidate: { artifact_id: id(8), source_version: 2, verification_id: id(9), sha256: 'a'.repeat(64), policy_id: id(10), expected_sequence: 0, max_expires_at: new Date(Date.now() + 300000).toISOString() }, withdrawal: null, prepared_terms: { ...emptyTerms(), note: 'Prepared terms are incomplete and require review.' }, current_review: { ...scope, kind: 'executed_contract', review_id: null, sequence: 0, status: 'not_reviewed', approval_current: false, expires_at: null, checked_at: stamp, execution_authorized: false }, checked_at: stamp, execution_authorized: false }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ExecutionReviewForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
it('opens explicitly, holds navigation, and closes without any save', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Open execution review' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true));
  fireEvent.click(screen.getByRole('button', { name: 'Close without saving' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
  expect(mock.fetch.mock.calls.some(call => call[1]?.method === 'POST')).toBe(false);
});
it('requires personal findings and preserves unknown terms for follow-up', async () => {
  open(); fireEvent.click(screen.getByText('Open execution review'));
  await screen.findByRole('option', { name: /Original version 2/ });
  fireEvent.change(screen.getByLabelText('Verified purchase-contract document'), { target: { value: id(8) } });
  await waitFor(() => expect(screen.getByText('Start agreement review')).toBeEnabled());
  fireEvent.click(screen.getByText('Start agreement review'));
  expect(screen.getByText('Next: compare terms')).toBeDisabled();
  for (const label of ['Seller signatures', 'Buyer signatures', 'Signing authority', 'Complete agreement']) {
    expect(screen.getByLabelText(label)).toHaveValue('unknown');
    fireEvent.change(screen.getByLabelText(label), { target: { value: 'confirmed' } });
    fireEvent.change(screen.getByLabelText(`${label} page or clause`), { target: { value: 'Page 4' } });
    fireEvent.change(screen.getByLabelText(`${label} findings`), { target: { value: 'Personally checked this synthetic signature block.' } });
  }
  fireEvent.click(screen.getByText('Next: compare terms'));
  expect(screen.getByLabelText('Purchase price ($)')).toHaveValue('');
  expect(screen.getByText('Next: review decision')).toBeDisabled();
  expect(mock.fetch.mock.calls.some(call => call[1]?.method === 'POST')).toBe(false);
});
it('recovers the exact original request after a later denial without erasing it', async () => {
  preserveExecution(sessionStorage, saved); mock.reject = true; const view = open();
  fireEvent.click(screen.getByText('Retry saved execution review')); await screen.findByText(/Save is unconfirmed/);
  expect(sessionStorage.length).toBe(1); view.unmount(); mock.reject = false; open();
  fireEvent.click(screen.getByText('Retry saved execution review')); await screen.findByText(/Execution review recorded/);
  const posts = mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
  expect(posts).toHaveLength(2); expect(posts[0][1].body).toBe(posts[1][1].body);
  expect(JSON.parse(posts[0][1].body)).toEqual(saved.request); expect(sessionStorage.length).toBe(0);
});
it('holds malformed recovery and makes no request', async () => {
  sessionStorage.setItem(executionKey(id(1), id(2)), '{broken'); open();
  expect(screen.getByRole('alert')).toHaveTextContent(/could not be read safely/);
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); expect(mock.fetch).not.toHaveBeenCalled();
  expect(sessionStorage.length).toBe(1);
});
it('cannot open while an adjacent step is held', () => { open(true); expect(screen.getByText('Open execution review')).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled(); });

async function prepareCompleteReview() {
  const { executionChoice, executionTerms } = await import('./fixtures/execution-review');
  const previous = mock.fetch.getMockImplementation()!, prepared = executionTerms(id(8));
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/candidate')) return { json: async () => executionChoice(context, id(8), prepared) };
    const response = await previous(path, init);
    if (path.includes('/references?')) { const page = await response.json(); page.items[0].source_version = 1; page.items[0].reference_type = 'term_source'; return { json: async () => page }; }
    return response;
  });
  open(); fireEvent.click(screen.getByText('Open execution review')); await screen.findByRole('option', { name: /Original version 1/ });
  fireEvent.change(screen.getByLabelText('Verified purchase-contract document'), { target: { value: id(8) } });
  await waitFor(() => expect(screen.getByText('Start agreement review')).toBeEnabled()); fireEvent.click(screen.getByText('Start agreement review'));
  for (const label of ['Seller signatures', 'Buyer signatures', 'Signing authority', 'Complete agreement']) {
    fireEvent.change(screen.getByLabelText(label), { target: { value: 'confirmed' } });
    fireEvent.change(screen.getByLabelText(`${label} page or clause`), { target: { value: 'Synthetic page 4' } });
    fireEvent.change(screen.getByLabelText(`${label} findings`), { target: { value: 'Personally checked the synthetic signature evidence.' } });
  }
  fireEvent.click(screen.getByText('Next: compare terms')); await screen.findByRole('option', { name: /Source version 1/ });
  expect(screen.getByText('Next: review decision')).toBeDisabled();
  for (const term of ['purchase_price', 'earnest_money', 'assignment', 'effective', 'inspection_deadline', 'closing_deadline']) {
    fireEvent.change(screen.getByLabelText('Term to cite'), { target: { value: term } });
    fireEvent.change(screen.getByLabelText('Original source document'), { target: { value: id(8) } });
    fireEvent.change(screen.getByLabelText('Page or clause reference'), { target: { value: `Synthetic ${term} clause` } });
    fireEvent.click(screen.getByText('Attach source to term'));
  }
  fireEvent.change(screen.getByLabelText('Returned-term review notes'), { target: { value: 'Personally compared every synthetic returned term to its source.' } });
  fireEvent.click(screen.getByText('Next: review decision')); expect(screen.getByText('Record execution review')).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('Decision notes'), { target: { value: 'Personally reviewed all synthetic findings and supporting clauses.' } });
}
it('saves only after explicit findings, six original sources and final personal review', async () => {
  await prepareCompleteReview(); fireEvent.click(screen.getByText('Record execution review')); await screen.findByText(/Execution review recorded/);
  const posts = mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST'); expect(posts).toHaveLength(1);
  const request = JSON.parse(posts[0][1].body); expect(request.findings.terms.sources).toHaveLength(6); expect(request.personally_reviewed).toBe(true);
  expect(request.findings.terms.purchase_price_cents).toBe(14000000); expect(request.expected_version).toBe(2); expect(sessionStorage.length).toBe(0); expect(mock.saved).toHaveBeenCalledOnce();
});
it('clears a definite first-attempt rejection and removes the personal acknowledgement', async () => {
  await prepareCompleteReview(); mock.reject = true; fireEvent.click(screen.getByText('Record execution review'));
  await screen.findByText(/The review was not saved/); expect(sessionStorage.length).toBe(0); expect(screen.getByRole('checkbox')).not.toBeChecked(); expect(mock.saved).not.toHaveBeenCalled();
});
it('withdraws the original agreement even when the selected new agreement is held', async () => {
  const { executionChoice, executionTerms } = await import('./fixtures/execution-review'); const previous = mock.fetch.getMockImplementation()!;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (!path.endsWith('/candidate')) return previous(path, init);
    const choice = executionChoice(context, id(8), executionTerms(id(8)), { ...saved.request, id: id(70), artifact_id: id(71), status: 'approved' }, 1);
    return { json: async () => ({ ...choice, status: 'evidence_review_required', candidate: null }) };
  });
  open(); fireEvent.click(screen.getByText('Open execution review')); await screen.findByRole('option', { name: /Original version 2/ });
  fireEvent.change(screen.getByLabelText('Verified purchase-contract document'), { target: { value: id(8) } });
  fireEvent.click(await screen.findByText('Withdraw my previous execution review'));
  fireEvent.change(screen.getByLabelText('Decision notes'), { target: { value: 'Withdraw the earlier agreement review while current evidence is held.' } });
  fireEvent.click(screen.getByText('Record withdrawal')); await screen.findByText(/Execution review recorded/);
  const post = mock.fetch.mock.calls.find(call => call[1]?.method === 'POST')!;
  expect(JSON.parse(post[1].body)).toMatchObject({ artifact_id: id(71), status: 'withdrawn', findings: null, personally_reviewed: false });
});
