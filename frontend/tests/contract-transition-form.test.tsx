import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractTransitionForm } from '../src/components/acquisition/ContractTransitionForm';
import { transitionContext as context, transitionChoice } from './fixtures/contract-transition';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), held: vi.fn(), saved: vi.fn(), lose: false, reject: false, wrong: false, paused: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedTransition = true; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); vi.restoreAllMocks(); mock.fetch.mockReset(); mock.held.mockReset(); mock.saved.mockReset(); mock.lose = false; mock.reject = false; mock.wrong = false; mock.paused = false;
  mock.fetch.mockImplementation(async (_path: string, init?: RequestInit) => {
    if (init?.method !== 'POST') return { json: async () => mock.paused ? { ...transitionChoice(), status: 'paused', candidate: null } : transitionChoice() };
    if (mock.reject) throw new ApiError('Definitive rejection'); if (mock.lose) throw new Error('Response lost');
    const request = JSON.parse(init.body as string);
    return { json: async () => ({ workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: mock.wrong ? 1 : 2,
      request_id: request.id, sequence: request.expected_sequence + 1, previous_status: request.expected_status, recorded_status: request.target_status,
      duplicate: false, transition_recorded: true, execution_authorized: false }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ContractTransitionForm context={context} disabled={disabled} onPending={mock.held} onSaved={mock.saved} /></QueryClientProvider>); }
async function fill() {
  fireEvent.click(screen.getByRole('button', { name: 'Review next contract status' }));
  await screen.findByText('Current review checks passed. Confirm the proposed status below.');
  fireEvent.change(screen.getByLabelText('Reason for the status change'), { target: { value: '  Reviewed contract is ready for the separate signature handoff.  ' } });
  fireEvent.click(screen.getByRole('checkbox'));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Record awaiting signature' })).toBeEnabled());
}
const posts = () => mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
it('requires an intentional confirmed action and saves only the discovered version and status', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); await fill(); expect(mock.held).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Record awaiting signature' }));
  await screen.findByText('Contract recorded as awaiting signature. No agreement was sent or signed.');
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ expected_version: 2, expected_sequence: 0, expected_status: 'draft', target_status: 'pending_signature' });
  expect(posts()).toHaveLength(1); expect(sessionStorage.length).toBe(0); expect(mock.saved).toHaveBeenCalledOnce();
  await waitFor(() => expect(mock.held).toHaveBeenLastCalledWith(false));
});
it('preserves the exact uncertain request through reload, later rejection and successful recovery', async () => {
  mock.lose = true; const view = open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record awaiting signature' }));
  await screen.findByText(/Save is unconfirmed/); const raw = sessionStorage.getItem(sessionStorage.key(0)!); view.unmount();
  mock.lose = false; mock.reject = true; open(); fireEvent.click(screen.getByRole('button', { name: 'Retry saved status change' }));
  await waitFor(() => expect(posts()).toHaveLength(2)); await waitFor(() => expect(screen.getByRole('button', { name: 'Retry saved status change' })).toBeEnabled());
  expect(sessionStorage.getItem(sessionStorage.key(0)!)).toBe(raw);
  mock.reject = false; fireEvent.click(screen.getByRole('button', { name: 'Retry saved status change' }));
  await screen.findByText('Contract recorded as awaiting signature. No agreement was sent or signed.');
  expect(posts()).toHaveLength(3); expect(new Set(posts().map(call => call[1].body)).size).toBe(1); expect(sessionStorage.length).toBe(0);
});
it('clears only a first explicitly rejected request and resets personal confirmation', async () => {
  mock.reject = true; open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record awaiting signature' }));
  await screen.findByText('The status change was not saved. Refresh the current checks before trying again.');
  expect(sessionStorage.length).toBe(0); expect(screen.getByRole('checkbox')).not.toBeChecked();
});
it('keeps a wrong-version receipt uncertain', async () => {
  mock.wrong = true; open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record awaiting signature' }));
  await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1); expect(mock.saved).not.toHaveBeenCalled();
});
it('closes unsaved edits without writing and disables sibling-gated opening', async () => {
  const view = open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Close status review without saving' }));
  expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0); expect(mock.held).toHaveBeenLastCalledWith(false); view.unmount();
  mock.fetch.mockClear(); open(true); expect(screen.getByRole('button', { name: 'Review next contract status' })).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled();
});
it('does not offer a transition when paused or when recovery cannot be read', async () => {
  mock.paused = true; const view = open(); fireEvent.click(screen.getByRole('button', { name: 'Review next contract status' }));
  await screen.findByText('Acquisition review is paused.'); expect(screen.getByRole('button', { name: 'Record awaiting signature' })).toBeDisabled(); view.unmount();
  sessionStorage.setItem(`wholesale.contract.transition:v1:${context.userId}:${context.workspaceId}`, 'invalid'); open();
  expect(screen.getByRole('alert')).toHaveTextContent('could not be read'); expect(mock.held).toHaveBeenLastCalledWith(true); expect(sessionStorage.length).toBe(1);
});
it('rechecks elapsed time before sending even if the last render was fresh', async () => {
  open(); await fill(); const current = Date.now(); vi.spyOn(Date, 'now').mockReturnValue(current + 31000);
  fireEvent.click(screen.getByRole('button', { name: 'Record awaiting signature' }));
  await screen.findByText(/Status preparation could not be confirmed/); expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});


it('records executed status only from its discovered review and recovers the exact request', async () => {
  const previous = mock.fetch.getMockImplementation()!;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return previous(path, init);
    const old = transitionChoice();
    return { json: async () => ({ ...old, current_status: 'pending_signature', sequence: 1,
      candidate: { expected_version: 2, expected_sequence: 1, expected_status: 'pending_signature', target_status: 'executed',
        execution_review_id: old.candidate.signature_review_id, expires_at: old.candidate.expires_at } }) };
  });
  mock.lose = true; const view = open();
  fireEvent.click(screen.getByText('Review next contract status'));
  await screen.findByText('Record reviewed execution');
  expect(screen.getByText('Record executed status')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Reason for the status change'), { target: { value: 'Record the independently reviewed returned agreement as executed.' } });
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByText('Record executed status'));
  await screen.findByText(/Save is unconfirmed/); view.unmount(); mock.lose = false; open();
  expect(screen.getByText('Contract version 2 · Executed')).toBeVisible();
  fireEvent.click(screen.getByText('Retry saved status change'));
  await screen.findByText('Executed status recorded. Title and disposition review remain separate steps.');
  expect(posts()).toHaveLength(2); expect(posts()[0][1].body).toBe(posts()[1][1].body);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ expected_status: 'pending_signature', target_status: 'executed', expected_sequence: 1 });
  expect(JSON.parse(posts()[0][1].body)).not.toHaveProperty('execution_review_id');
  expect(sessionStorage.length).toBe(0);
});

it('intentionally begins title review and recovers the same request after reload', async () => {
  const previous = mock.fetch.getMockImplementation()!;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return previous(path, init);
    const old = transitionChoice();
    return { json: async () => ({ ...old, current_status: 'executed', sequence: 2,
      candidate: { expected_version: 2, expected_sequence: 2, expected_status: 'executed', target_status: 'title_review',
        execution_review_id: old.candidate.signature_review_id, expires_at: old.candidate.expires_at } }) };
  });
  mock.lose = true; const view = open(); fireEvent.click(screen.getByText('Review next contract status'));
  await screen.findByText('Begin title review');
  expect(screen.getByText('Record title-review start')).toBeDisabled();
  expect(screen.getByText(/Starting review does not confirm clear title/)).toBeVisible();
  fireEvent.change(screen.getByLabelText('Reason for the status change'), { target: { value: 'Begin title examination of this independently reviewed executed contract.' } });
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByText('Record title-review start'));
  await screen.findByText(/Save is unconfirmed/); view.unmount(); mock.lose = false; open();
  expect(screen.getByText('Contract version 2 · Title review')).toBeVisible();
  fireEvent.click(screen.getByText('Retry saved status change'));
  await screen.findByText('Title review started. Clear title, marketing and assignment still require separate review.');
  expect(posts()).toHaveLength(2); expect(posts()[0][1].body).toBe(posts()[1][1].body);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ expected_status: 'executed', target_status: 'title_review', expected_sequence: 2 });
  expect(JSON.parse(posts()[0][1].body)).not.toHaveProperty('execution_review_id');
  expect(sessionStorage.length).toBe(0);
});

it('holds title entry when recorded execution authority is no longer current', async () => {
  mock.fetch.mockImplementation(async () => ({ json: async () => ({ ...transitionChoice(), current_status: 'executed', sequence: 2,
    status: 'title_review_required', candidate: null }) }));
  open(); fireEvent.click(screen.getByText('Review next contract status'));
  await screen.findByText(/recorded execution review is no longer current/);
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument(); expect(posts()).toHaveLength(0);
});
