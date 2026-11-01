import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TitleReviewForm } from '../src/components/acquisition/TitleReviewForm';
import { titleLabels } from '../src/lib/acquisition/title-review';
import { preserveTitle, titleKey, type PendingTitle } from '../src/lib/acquisition/title-review';
import { titleId as id, titleContext as context, titleScope as scope, titleChoice, titleReference } from './fixtures/title-review';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, deny: false, revoked: false, withdraw: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedTitle = true; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.lose = mock.deny = mock.revoked = mock.withdraw = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.deny) throw new ApiError('Denied', 403);
      if (mock.lose) throw new Error('Lost response');
      const body = JSON.parse(init.body as string); return { json: async () => ({ ...scope, kind: 'title_findings', review_id: body.id, sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    if (path.includes('/references?')) { const purpose = new URL(path, 'http://local').searchParams.get('purpose'), now = Date.now(); return { json: async () => ({ ...scope, purpose, items: purpose === 'title_report' ? [titleReference(now)] : [], next_after: null, checked_at: new Date(now).toISOString(), execution_authorized: false }) }; }
    if (path.includes('/references/')) return { json: async () => mock.revoked ? { ...titleReference(), status: 'source_revoked', verification_id: null } : titleReference() };
    const c = titleChoice(path.includes('artifact_id=') ? id(8) : null);
    return { json: async () => mock.withdraw ? { ...c, status: 'paused', candidate: null, resolution: null, withdrawal: { review_id: id(20), artifact_id: id(8), source_version: 2, verification_id: id(9), policy_id: id(10), expected_sequence: 1, original_status: 'requires_resolution' }, current_review: { ...c.current_review, review_id: id(20), sequence: 1, status: 'requires_resolution' } } : c };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><TitleReviewForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function start() {
  const view = open(); fireEvent.click(screen.getByText('Open title review')); await screen.findByRole('option', { name: /Original version 2/ });
  fireEvent.change(screen.getByLabelText('Title report'), { target: { value: id(8) } });
  await waitFor(() => expect(screen.getByText('Start title findings')).toBeEnabled()); fireEvent.click(screen.getByText('Start title findings')); return view;
}
async function fill(approve = false) {
  const view = await start(); expect(screen.getByLabelText('Report cutoff precision')).toHaveValue('unknown');
  if (approve) {
    fireEvent.change(screen.getByLabelText('Report cutoff precision'), { target: { value: 'instant' } });
    fireEvent.change(screen.getByLabelText('Original report timestamp'), { target: { value: new Date(Date.now() - 10000).toISOString() } });
    fireEvent.change(screen.getByLabelText('Report cutoff page or clause'), { target: { value: 'Original page 1' } });
  }
  fireEvent.change(screen.getByLabelText('Report scope and limitations'), { target: { value: 'Synthetic report with all known limitations preserved.' } });
  fireEvent.click(screen.getByText('Next: title findings'));
  expect(screen.getByText('Next: title decision')).toBeDisabled();
  for (const label of Object.values(titleLabels)) {
    expect(screen.getByLabelText(`${label} finding`)).toHaveValue('unknown');
    if (approve) { fireEvent.change(screen.getByLabelText(`${label} finding`), { target: { value: 'satisfactory' } }); fireEvent.click(screen.getByText(`Cite title report for ${label.toLowerCase()}`)); fireEvent.change(screen.getByLabelText(`${label} source 1 page or clause`), { target: { value: 'Original page 2' } }); }
    else fireEvent.change(screen.getByLabelText(`${label} next action`), { target: { value: `Ask title counsel to resolve ${label.toLowerCase()}.` } });
    fireEvent.change(screen.getByLabelText(`${label} notes`), { target: { value: 'Personally reviewed this synthetic title finding.' } });
  }
  fireEvent.click(screen.getByText('Next: title decision')); expect(screen.getByLabelText('Title decision')).toHaveValue('requires_resolution');
  if (approve) { await waitFor(() => expect(screen.getByRole('option', { name: 'Approve the reviewed findings' })).toBeEnabled()); fireEvent.change(screen.getByLabelText('Title decision'), { target: { value: 'approved' } }); }
  fireEvent.change(screen.getByLabelText('Title decision notes'), { target: { value: 'Personally reviewed the synthetic report and findings.' } });
  fireEvent.click(screen.getByRole('checkbox')); await waitFor(() => expect(screen.getByText(approve ? 'Record title approval' : 'Record resolution hold')).toBeEnabled()); return view;
}
it('opens explicitly, holds navigation and closes without writes', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Open title review'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); fireEvent.click(screen.getByText('Close without saving'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false)); expect(mock.fetch.mock.calls.some(c => c[1]?.method === 'POST')).toBe(false);
});
it('records unknown findings as an explicit resolution hold with required actions', async () => {
  await fill(); fireEvent.click(screen.getByText('Record resolution hold')); await screen.findByText(/Title decision recorded/);
  const body = JSON.parse(mock.fetch.mock.calls.find(c => c[1]?.method === 'POST')![1].body);
  expect(body.status).toBe('requires_resolution'); expect(body.expires_at).toBeNull(); expect(body.findings.report_as_of).toEqual({ precision: 'unknown', calendar_date: null, instant: null }); expect(body.findings.ownership.required_action).toMatch(/counsel/); expect(sessionStorage.length).toBe(0);
});
it('preserves exact findings through response loss, reload, denial and recovery', async () => {
  mock.lose = true; let view = await fill(true); fireEvent.click(screen.getByText('Record title approval')); await screen.findByText(/Save is unconfirmed/);
  const original = mock.fetch.mock.calls.find(c => c[1]?.method === 'POST')![1].body;
  expect(sessionStorage.length).toBe(1); view.unmount(); mock.lose = false; mock.deny = true; view = open();
  fireEvent.click(screen.getByText('Retry saved title decision')); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  view.unmount(); mock.deny = false; open(); fireEvent.click(screen.getByText('Retry saved title decision')); await screen.findByText(/Title decision recorded/);
  const posts = mock.fetch.mock.calls.filter(c => c[1]?.method === 'POST'); expect(posts).toHaveLength(3); for (const post of posts) expect(post[1].body).toBe(original); expect(sessionStorage.length).toBe(0);
});
it('allows independent original withdrawal while paused and without a selected report', async () => {
  mock.withdraw = true; open(); fireEvent.click(screen.getByText('Open title review')); fireEvent.click(await screen.findByText('Withdraw my previous title decision'));
  fireEvent.change(screen.getByLabelText('Title decision notes'), { target: { value: 'Withdraw my original decision while review is paused.' } }); fireEvent.click(screen.getByText('Record title withdrawal')); await screen.findByText(/Title decision recorded/);
  const body = JSON.parse(mock.fetch.mock.calls.find(c => c[1]?.method === 'POST')![1].body); expect(body).toMatchObject({ status: 'withdrawn', expected_sequence: 1, artifact_id: id(8), personally_reviewed: false, findings: null, expires_at: null });
});
it('holds revoked originals and resets acknowledgement on refresh', async () => {
  await fill(true); mock.revoked = true; fireEvent.click(screen.getByText('Refresh title checks'));
  await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeChecked()); fireEvent.click(screen.getByRole('checkbox'));
  await screen.findByText(/Refresh the original document checks/); expect(screen.getByText('Record title approval')).toBeDisabled(); expect(mock.fetch.mock.calls.some(c => c[1]?.method === 'POST')).toBe(false);
});
it('clears only a definite rejection on the first write attempt', async () => {
  await fill(); mock.deny = true; fireEvent.click(screen.getByText('Record resolution hold')); await screen.findByText(/title decision was not saved/); expect(sessionStorage.length).toBe(0); expect(screen.getByRole('checkbox')).not.toBeChecked();
});
it('blocks corrupt recovery and adjacent pending work without requests', async () => {
  let view = open(true); expect(screen.getByText('Open title review')).toBeDisabled(); view.unmount();
  sessionStorage.setItem(titleKey(id(1), id(2)), '{broken'); view = open(); expect(screen.getByRole('alert')).toHaveTextContent(/could not be read safely/); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); expect(mock.fetch).not.toHaveBeenCalled();
});
it('retains original version recovery without any new candidate request', async () => {
  const saved: PendingTitle = { version: 1, context, request: { id: id(7), expected_version: 2, expected_sequence: 1, status: 'withdrawn', artifact_id: id(8), verification_id: id(9), policy_id: id(10), expires_at: null, personally_reviewed: false, findings: null, note: 'Withdraw the exact original title decision.' } };
  preserveTitle(sessionStorage, saved); open(); fireEvent.click(screen.getByText('Retry saved title decision')); await screen.findByText(/Title decision recorded/); expect(mock.fetch).toHaveBeenCalledTimes(1); expect(mock.fetch.mock.calls[0][0]).toMatch(/versions\/2\/title-review$/);
});
