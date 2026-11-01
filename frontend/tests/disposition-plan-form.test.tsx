import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DispositionPlanForm } from '../src/components/acquisition/DispositionPlanForm';
import { preservePlan, planKey } from '../src/lib/acquisition/disposition-plan';
import { context, pending, receipt, planState } from './fixtures/disposition-plan';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, deny: false, paused: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedPlan = true; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.lose = mock.deny = mock.paused = false;
  mock.fetch.mockImplementation(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.deny) throw new ApiError('Denied', 403);
      if (mock.lose) throw new Error('Lost response');
      return { json: async () => receipt(JSON.parse(init.body as string)) };
    }
    return { json: async () => planState(mock.paused, mock.paused) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient()}><DispositionPlanForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function prepare() {
  const view = open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Open purchase path'));
  await screen.findByText('Choose an internal proposal for the next review.');
  expect(screen.getByLabelText('Proposed purchase path')).toHaveValue(''); expect(screen.getByText('3. Save internal proposal')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Proposed purchase path'), { target: { value: 'wholesale_assignment' } });
  fireEvent.change(screen.getByLabelText('2. Explain the proposed path'), { target: { value: 'Propose assignment for separate title and legal review.' } });
  await waitFor(() => expect(screen.getByText('3. Save internal proposal')).toBeEnabled()); return view;
}
const posts = () => mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
it('requires an intentional path and reason, saves intent only, releases navigation', async () => {
  await prepare(); expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByText('3. Save internal proposal')); await screen.findByText(/Internal proposal saved/);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ exit_type: 'wholesale_assignment', status: 'proposed', original_plan_id: null, expected_sequence: 0 });
  expect(posts()).toHaveLength(1); expect(sessionStorage.length).toBe(0); expect(mock.pending).toHaveBeenLastCalledWith(false); expect(mock.saved).toHaveBeenCalledOnce();
});
it('recovers a lost reply after reload and keeps original request after a later denial', async () => {
  mock.lose = true; const view = await prepare(); fireEvent.click(screen.getByText('3. Save internal proposal')); await screen.findByText(/Save is unconfirmed/);
  const original = posts()[0][1].body; view.unmount(); mock.lose = false; mock.deny = true;
  open(); fireEvent.click(screen.getByText('Retry saved proposal')); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  mock.deny = false; fireEvent.click(screen.getByText('Retry saved proposal')); await screen.findByText(/Internal proposal saved/);
  expect(posts().map(call => call[1].body)).toEqual([original, original, original]); expect(sessionStorage.length).toBe(0);
});
it('clears only definite first-attempt rejection', async () => {
  mock.deny = true; await prepare(); fireEvent.click(screen.getByText('3. Save internal proposal'));
  await screen.findByText(/The proposal was not saved/); expect(sessionStorage.length).toBe(0);
});
it('withdraws the original proposal while paused without choosing another path', async () => {
  mock.paused = true; open(); fireEvent.click(screen.getByText('Open purchase path')); fireEvent.click(await screen.findByText('Withdraw my latest proposal'));
  fireEvent.change(screen.getByLabelText('Withdrawal reason'), { target: { value: 'Withdraw the original proposal pending further review.' } });
  fireEvent.click(screen.getByText('Record proposal withdrawal')); await screen.findByText(/Proposal withdrawn/);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ status: 'withdrawn', exit_type: pending.request.exit_type, original_plan_id: pending.request.id, expected_sequence: 1 });
});
it('blocks disabled and corrupt recovery without requests', async () => {
  const view = open(true); expect(screen.getByText('Open purchase path')).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled(); view.unmount();
  sessionStorage.setItem(planKey(context.userId, context.workspaceId), '{bad'); open(); await screen.findByRole('alert'); expect(mock.fetch).not.toHaveBeenCalled(); expect(mock.pending).toHaveBeenLastCalledWith(true);
});
it('retains recovery if storage cannot confirm a write', async () => {
  await prepare(); const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable'); });
  fireEvent.click(screen.getByText('3. Save internal proposal')); await screen.findByText(/Saved purchase-path details could not be read safely/);
  expect(posts()).toHaveLength(0); expect(mock.pending).toHaveBeenLastCalledWith(true); spy.mockRestore();
});
it('does not clear mismatched receipts', async () => {
  preservePlan(sessionStorage, pending); mock.fetch.mockResolvedValue({ json: async () => ({ ...receipt(), exit_type: 'wholesale_assignment' }) });
  open(); fireEvent.click(screen.getByText('Retry saved proposal')); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
});
