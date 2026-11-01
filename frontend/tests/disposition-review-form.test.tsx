import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DispositionReviewForm } from '../src/components/acquisition/DispositionReviewForm';
import { dispositionLabels, dispositionCommonNames, preserveDisposition, dispositionKey, type PendingDisposition } from '../src/lib/acquisition/disposition-review';
import { dispositionId as id, dispositionContext as context, dispositionScope as scope, dispositionChoice } from './fixtures/disposition-review';
import { titleReference } from './fixtures/title-review';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, deny: false, revoked: false, withdraw: false, assignment: true, replaced: false, legalMissing: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedDisposition = true; } }));
import { ApiError } from '../src/lib/api';
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset();
  mock.lose = mock.deny = mock.revoked = mock.withdraw = mock.replaced = mock.legalMissing = false; mock.assignment = true;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.deny) throw new ApiError('Denied', 403);
      if (mock.lose) throw new Error('Lost response');
      const body = JSON.parse(init.body as string); return { json: async () => ({ ...scope, kind: 'disposition_findings', review_id: body.id, sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    if (path.includes('/references?')) { const purpose = new URL(path, 'http://local').searchParams.get('purpose'); return { json: async () => ({ ...scope, purpose, items: [], next_after: null, checked_at: new Date().toISOString(), execution_authorized: false }) }; }
    if (path.includes('/references/')) return { json: async () => ({ ...titleReference(), source_version: 1, reference_type: 'term_source', purpose: 'purchase_contract', ...(mock.revoked ? { status: 'source_revoked', verification_id: null } : {}) }) };
    const c = dispositionChoice(mock.assignment);
    if (mock.replaced) { c.resolution.plan_id = id(30); c.candidate.plan_id = id(30); }
    return { json: async () => mock.withdraw ? { ...c, status: 'paused', candidate: null, resolution: null,
      withdrawal: { review_id: id(20), plan_id: id(21), exit_type: 'principal_acquisition', policy_id: id(22), expected_sequence: 1, original_status: 'requires_resolution' },
      current_review: { ...c.current_review, review_id: id(20), sequence: 1, status: 'requires_resolution' } }
      : mock.legalMissing ? { ...c, status: 'legal_evidence_required', candidate: null, resolution: { ...c.resolution, legal_source: null } } : c };
  });
});
function open(disabled = false, ctx = context, withdrawalOnly = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DispositionReviewForm withdrawalOnly={withdrawalOnly} context={ctx} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function start() {
  const view = open(); fireEvent.click(screen.getByText('Open disposition review'));
  await waitFor(() => expect(screen.getByText('Start disposition findings')).toBeEnabled()); fireEvent.click(screen.getByText('Start disposition findings')); return view;
}
async function fill(approve = false) {
  const view = await start(); expect(screen.getByText('Next: disposition decision')).toBeDisabled();
  const labels = mock.assignment ? Object.values(dispositionLabels) : dispositionCommonNames.map(n => dispositionLabels[n]);
  for (const label of labels) {
    expect(screen.getByLabelText(`${label} finding`)).toHaveValue('unknown');
    if (approve) {
      fireEvent.change(screen.getByLabelText(`${label} finding`), { target: { value: 'satisfactory' } });
      fireEvent.click(screen.getByText(`${label === 'Reviewed legal basis' ? 'Cite reviewed legal source' : 'Cite executed contract'} for ${label.toLowerCase()}`));
      fireEvent.change(screen.getByLabelText(`${label} source 1 page or clause`), { target: { value: 'Original clause 14' } });
    } else fireEvent.change(screen.getByLabelText(`${label} next action`), { target: { value: `Ask counsel to resolve ${label.toLowerCase()} before proceeding.` } });
    fireEvent.change(screen.getByLabelText(`${label} notes`), { target: { value: 'Personally reviewed this synthetic original finding.' } });
  }
  fireEvent.click(screen.getByText('Next: disposition decision')); expect(screen.getByLabelText('Disposition decision')).toHaveValue('requires_resolution');
  if (approve) { await waitFor(() => expect(screen.getByRole('option', { name: 'Approve the reviewed findings' })).toBeEnabled()); fireEvent.change(screen.getByLabelText('Disposition decision'), { target: { value: 'approved' } }); }
  fireEvent.change(screen.getByLabelText('Disposition decision notes'), { target: { value: 'Personally reviewed the original contract and required findings.' } });
  fireEvent.click(screen.getByRole('checkbox'));
  await waitFor(() => expect(screen.getByText(approve ? 'Record disposition approval' : 'Record disposition resolution hold')).toBeEnabled()); return view;
}
const posts = () => mock.fetch.mock.calls.filter(c => c[1]?.method === 'POST');
it('opens explicitly, holds navigation and closes without writes', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Open disposition review'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); fireEvent.click(screen.getByText('Close without saving'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false)); expect(posts()).toHaveLength(0);
});
it.each([false, true])('records unknown findings as an explicit resolution hold, assignment=%s', async assignment => {
  mock.assignment = assignment; await fill(); fireEvent.click(screen.getByText('Record disposition resolution hold')); await screen.findByText(/Disposition decision recorded/);
  const body = JSON.parse(posts()[0][1].body); expect(body).toMatchObject({ status: 'requires_resolution', expires_at: null, plan_id: id(11), original_review_id: null });
  expect(body.findings.contractual_interest.required_action).toMatch(/counsel/); expect(!!body.findings.assignment).toBe(assignment); expect(sessionStorage.length).toBe(0);
});
it('preserves exact findings through response loss, reload, later denial and recovery', async () => {
  mock.lose = true; let view = await fill(true); fireEvent.click(screen.getByText('Record disposition approval')); await screen.findByText(/Save is unconfirmed/);
  const original = posts()[0][1].body; expect(JSON.parse(original).findings.contractual_interest.sources[0].artifact_version).toBe(1);
  expect(sessionStorage.length).toBe(1); view.unmount(); mock.lose = false; mock.deny = true; view = open();
  fireEvent.click(screen.getByText('Retry saved disposition decision')); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.length).toBe(1);
  view.unmount(); mock.deny = false; open(); fireEvent.click(screen.getByText('Retry saved disposition decision')); await screen.findByText(/Disposition decision recorded/);
  expect(posts()).toHaveLength(3); for (const post of posts()) expect(post[1].body).toBe(original); expect(sessionStorage.length).toBe(0);
});
it('allows independent original withdrawal while paused without current proposal choices', async () => {
  mock.withdraw = true; open(); fireEvent.click(screen.getByText('Open disposition review')); fireEvent.click(await screen.findByText('Withdraw my previous disposition decision'));
  fireEvent.change(screen.getByLabelText('Disposition decision notes'), { target: { value: 'Withdraw my original decision while review is paused.' } });
  fireEvent.click(screen.getByText('Record disposition withdrawal')); await screen.findByText(/Disposition decision recorded/);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ status: 'withdrawn', original_review_id: id(20), plan_id: id(21), policy_id: id(22), expected_sequence: 1, personally_reviewed: false, findings: null, expires_at: null });
});
it('holds revoked originals and resets acknowledgement on refresh', async () => {
  await fill(true); mock.revoked = true; fireEvent.click(screen.getByText('Refresh disposition checks'));
  await waitFor(() => expect(screen.getByRole('checkbox')).not.toBeChecked()); fireEvent.click(screen.getByRole('checkbox'));
  await screen.findByText(/Refresh the original document checks/); expect(screen.getByText('Record disposition approval')).toBeDisabled(); expect(posts()).toHaveLength(0);
});
it('never silently moves prepared findings to a replacement proposal', async () => {
  await fill(true); mock.replaced = true; fireEvent.click(screen.getByText('Refresh disposition checks'));
  await screen.findByText(/selected review context changed/); fireEvent.click(screen.getByRole('checkbox'));
  expect(screen.getByText('Record disposition approval')).toBeDisabled(); expect(posts()).toHaveLength(0);
});
it('records missing assignment legal evidence as unresolved without enabling approval', async () => {
  mock.legalMissing = true; await fill(); expect(screen.getByRole('option', { name: 'Approve the reviewed findings' })).toBeDisabled();
  fireEvent.click(screen.getByText('Record disposition resolution hold')); await screen.findByText(/Disposition decision recorded/);
  expect(JSON.parse(posts()[0][1].body).findings.assignment.legal_basis).toMatchObject({ finding: 'unknown', sources: [] });
});
it('clears only definite first-attempt rejection', async () => {
  await fill(); mock.deny = true; fireEvent.click(screen.getByText('Record disposition resolution hold')); await screen.findByText(/disposition decision was not saved/);
  expect(sessionStorage.length).toBe(0); expect(screen.getByRole('checkbox')).not.toBeChecked();
});
it('blocks corrupt recovery and adjacent pending work without requests', async () => {
  const view = open(true); expect(screen.getByText('Open disposition review')).toBeDisabled(); view.unmount();
  sessionStorage.setItem(dispositionKey(id(1), id(2)), '{broken'); open(); expect(screen.getByRole('alert')).toHaveTextContent(/could not be read safely/);
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); expect(mock.fetch).not.toHaveBeenCalled();
});
it('recovers original version directly and blocks mismatched context', async () => {
  const saved: PendingDisposition = { version: 1, context, request: { id: id(7), expected_version: 2, expected_sequence: 1, status: 'withdrawn', plan_id: id(11), original_review_id: id(20), policy_id: id(10), expires_at: null, personally_reviewed: false, findings: null, note: 'Withdraw the exact original disposition decision.' } };
  preserveDisposition(sessionStorage, saved); const view = open(false, { ...context, contractVersion: 3 });
  expect(screen.getByRole('alert')).toHaveTextContent(/could not be read safely/); expect(mock.fetch).not.toHaveBeenCalled(); view.unmount();
  open(); fireEvent.click(screen.getByText('Retry saved disposition decision')); await screen.findByText(/Disposition decision recorded/);
  expect(mock.fetch).toHaveBeenCalledTimes(1); expect(mock.fetch.mock.calls[0][0]).toMatch(/versions\/2\/disposition-review$/);
});


it('keeps only original withdrawal available after handoff and preserves uncertain recovery', async () => {
  mock.withdraw = true; mock.lose = true;
  const view = open(false, context, true); fireEvent.click(screen.getByText('Open disposition review'));
  fireEvent.click(await screen.findByText('Withdraw my previous disposition decision'));
  expect(screen.queryByText('Start disposition findings')).not.toBeInTheDocument();
  expect(screen.getByText('Record your withdrawal')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Disposition decision notes'), { target: { value: 'Withdraw the original disposition decision after handoff.' } });
  fireEvent.click(screen.getByText('Record disposition withdrawal')); await screen.findByText(/Save is unconfirmed/);
  const original = posts()[0][1].body; view.unmount(); mock.lose = false;
  open(false, context, true); fireEvent.click(screen.getByText('Retry saved disposition decision'));
  await screen.findByText(/Disposition decision recorded/);
  expect(posts()).toHaveLength(2); expect(posts()[1][1].body).toBe(original); expect(sessionStorage.length).toBe(0);
});
it('does not expose fresh findings from a cached ready choice in withdrawal-only mode', async () => {
  open(false, context, true); fireEvent.click(screen.getByText('Open disposition review'));
  await screen.findByText('No original disposition decision is available for you to withdraw.');
  expect(screen.queryByText('Start disposition findings')).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument(); expect(posts()).toHaveLength(0);
});
