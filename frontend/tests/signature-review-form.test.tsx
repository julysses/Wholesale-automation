import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SignatureReviewForm } from '../src/components/acquisition/SignatureReviewForm';
import { signatureKey } from '../src/lib/acquisition/signature-review';
import { sigContext as context, sigId as id, signatureChoice } from './fixtures/signature-review';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, reject: false, withdraw: false, held: false, wrong: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedSignature = true; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset();
  mock.lose = false; mock.reject = false; mock.withdraw = false; mock.held = false; mock.wrong = false;
  mock.fetch.mockImplementation(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Denied', 409); if (mock.lose) throw new Error('Lost reply');
      const body = JSON.parse(init.body as string);
      return { json: async () => ({ workspace_id: id(2), contract_id: id(3), contract_version: mock.wrong ? 3 : 2, review_id: body.id,
        sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    return { json: async () => signatureChoice(mock.withdraw, mock.held) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SignatureReviewForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function prepare() {
  fireEvent.click(screen.getByRole('button', { name: 'Open signature-release review' }));
  await screen.findByText(/Reviewing contract version 2 using the original document from version 1/);
  fireEvent.change(screen.getByLabelText('Signature-review notes'), { target: { value: 'I reviewed the exact contract and its original supporting document.' } });
  fireEvent.click(screen.getByRole('checkbox'));
}
const posts = () => mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
it('uses discovered basis and policy, holds navigation and saves without signing', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); await prepare(); expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Record signature-release approval' })); await screen.findByText(/Signature-release review recorded/);
  expect(posts()).toHaveLength(1); expect(JSON.parse(posts()[0][1].body)).toMatchObject({ basis_review_id: id(8), policy_id: id(10), personally_reviewed: true });
  expect(sessionStorage.length).toBe(0); expect(mock.saved).toHaveBeenCalledOnce(); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('recovers the exact saved decision after reload and retains uncertainty on later denial', async () => {
  mock.lose = true; const view = open(); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Record signature-release approval' }));
  await screen.findByText(/Save is unconfirmed/); view.unmount(); mock.lose = false; mock.reject = true; open();
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved signature review' })); await screen.findByText(/Save is unconfirmed/);
  expect(sessionStorage.length).toBe(1); mock.reject = false;
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved signature review' })); await screen.findByText(/Signature-release review recorded/);
  expect(posts()).toHaveLength(3); expect(new Set(posts().map(call => call[1].body)).size).toBe(1); expect(sessionStorage.length).toBe(0);
});
it('withdraws the original basis while approval is paused', async () => {
  mock.withdraw = true; mock.held = true; open(); fireEvent.click(screen.getByRole('button', { name: 'Open signature-release review' }));
  await screen.findByText('Acquisition review is paused.');
  fireEvent.change(screen.getByLabelText('Signature-review notes'), { target: { value: 'Withdraw my original signature-release review after the source changed.' } });
  expect(screen.getByRole('button', { name: 'Record signature-release approval' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Withdraw my signature review' })); await screen.findByText(/Signature-release review recorded/);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ status: 'withdrawn', basis_review_id: id(12), policy_id: id(13), personally_reviewed: false, expires_at: null });
});
it('closes unsaved edits without writing or leaving navigation held', async () => {
  open(); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Close without saving' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false)); expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});
it('keeps a mismatched receipt pending', async () => {
  mock.wrong = true; open(); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Record signature-release approval' }));
  await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1); expect(mock.saved).not.toHaveBeenCalled();
});
it('clears only an explicitly rejected first attempt', async () => {
  mock.reject = true; open(); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Record signature-release approval' }));
  await screen.findByText(/The review was not saved/); expect(sessionStorage.length).toBe(0); expect(screen.getByRole('checkbox')).not.toBeChecked();
});
it('blocks unreadable saved recovery without erasing it', () => {
  sessionStorage.setItem(signatureKey(id(1), id(2)), '{broken'); open();
  expect(screen.getByRole('alert')).toHaveTextContent('Reconcile this tab'); expect(mock.pending).toHaveBeenLastCalledWith(true);
  expect(mock.fetch).not.toHaveBeenCalled(); expect(sessionStorage.length).toBe(1);
});
it('does not load or open while a sibling step is held', () => {
  open(true); expect(screen.getByRole('button', { name: 'Open signature-release review' })).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled();
});
