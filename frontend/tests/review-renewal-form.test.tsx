import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReviewRenewalForm } from '../src/components/acquisition/ReviewRenewalForm';
import { readPendingRenewal, renewalKey } from '../src/lib/acquisition/review-renewal';
import { choice, context, id } from './review-renewal-fixture';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, reject: false, hold: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedRenewal = true; status = 409; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.lose = false; mock.reject = false; mock.hold = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Rejected', 409);
      if (mock.lose) throw new Error('Lost response');
      const body = JSON.parse(init.body as string);
      return { json: async () => ({ workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2,
        kind: body.kind, deadline_term: body.deadline_term, review_id: body.id, root_review_id: body.root_review_id,
        previous_review_id: body.previous_review_id, sequence: body.expected_sequence + 1, duplicate: true,
        review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    const c = choice(); c.checked_at = new Date().toISOString(); c.candidate.max_expires_at = new Date(Date.now() + 300000).toISOString(); c.candidate.sources[0].expires_at = c.candidate.max_expires_at;
    const held = { ...c, status: 'supporting_review_required', candidate: null };
    if (path.endsWith('/candidate')) return { json: async () => mock.hold ? held : c };
    return { json: async () => ({ workspace_id: c.workspace_id, contract_id: c.contract_id, contract_version: 2, checked_at: c.checked_at,
      execution_authorized: false, items: [{ root_review_id: c.root_review_id, kind: c.kind, deadline_term: c.deadline_term, status: c.status, current_review: c.current_review }] }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ReviewRenewalForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function select() { fireEvent.click(screen.getByText('Check review renewals')); fireEvent.click(await screen.findByText('Read original review')); await screen.findByText('The signed agreement gives an explicit local closing time.'); }
async function confirm() { await select(); fireEvent.click(screen.getByText('Next: confirm renewal')); fireEvent.change(screen.getByLabelText('Renewal decision notes'), { target: { value: 'I personally reviewed the same original facts and supporting documents.' } }); fireEvent.click(screen.getByRole('checkbox')); }
it('opens intentionally, shows three steps and read-only original findings, then saves only the renewal selectors', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); await confirm();
  expect(screen.getByLabelText('Review renewal steps')).toHaveTextContent('1. Choose review');
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByText('Record review renewal')); await waitFor(() => expect(mock.saved).toHaveBeenCalledOnce());
  const body = JSON.parse(mock.fetch.mock.calls.find(([, init]) => init?.method === 'POST')![1].body);
  expect(body.root_review_id).toBe(id(7)); expect(body).not.toHaveProperty('findings'); expect(body).not.toHaveProperty('sources');
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toBeNull();
});
it('recovers a lost save after remount using the exact original request, even if a later attempt rejects', async () => {
  const view = open(); await confirm(); mock.lose = true; fireEvent.click(screen.getByText('Record review renewal'));
  await screen.findByText('Retry saved renewal'); const original = sessionStorage.getItem(renewalKey(context.userId, context.workspaceId));
  view.unmount(); mock.reject = true; open(); fireEvent.click(screen.getByText('Retry saved renewal'));
  await screen.findByText('Save is unconfirmed. Retry the same saved renewal to avoid duplicates.'); expect(sessionStorage.getItem(renewalKey(context.userId, context.workspaceId))).toBe(original);
  mock.reject = false; mock.lose = false; fireEvent.click(screen.getByText('Retry saved renewal')); await waitFor(() => expect(mock.saved).toHaveBeenCalledOnce());
  const bodies = mock.fetch.mock.calls.filter(([, init]) => init?.method === 'POST').map(([, init]) => init.body);
  expect(new Set(bodies).size).toBe(1);
});
it('clears only a definitive first rejection and requires personal confirmation again after refresh or edits', async () => {
  open(); await confirm(); fireEvent.change(screen.getByLabelText('Renewal validity (minutes)'), { target: { value: '10' } });
  expect(screen.getByText('Record review renewal')).toBeDisabled(); fireEvent.click(screen.getByRole('checkbox'));
  mock.reject = true; fireEvent.click(screen.getByText('Record review renewal')); await screen.findByText('The renewal was not saved. Refresh checks before reviewing again.');
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toBeNull(); expect(screen.getByRole('checkbox')).not.toBeChecked();
});
it('holds supporting-review restrictions, disabled contexts and corrupt saved recovery', async () => {
  const view = open(true); expect(screen.getByText('Check review renewals')).toBeDisabled(); view.unmount();
  mock.hold = true; const second = open(); await select(); expect(screen.getByText('Next: confirm renewal')).toBeDisabled();
  expect(screen.getByText('Renew the earlier supporting review first.')).toBeInTheDocument(); second.unmount();
  sessionStorage.setItem(renewalKey(context.userId, context.workspaceId), 'broken'); open();
  expect(screen.getByRole('alert')).toHaveTextContent('Saved renewal details'); expect(mock.pending).toHaveBeenLastCalledWith(true);
});
