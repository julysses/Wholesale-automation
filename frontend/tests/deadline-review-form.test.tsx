import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeadlineReviewForm } from '../src/components/acquisition/DeadlineReviewForm';
import { deadlineKey } from '../src/lib/acquisition/deadline-review';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), saved: vi.fn(), lose: false, withdrawal: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedDeadline = true; } }));
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
const scope = { workspace_id: id(2), contract_id: id(6), contract_version: 2 };
beforeEach(() => {
  sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.saved.mockReset(); mock.lose = false; mock.withdrawal = false;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    const stamp = new Date().toISOString(), expiry = new Date(Date.now() + 300000).toISOString();
    if (init?.method === 'POST') {
      if (mock.lose) throw new Error('Lost response');
      const body = JSON.parse(init.body as string);
      return { json: async () => ({ ...scope, kind: 'deadline_resolution', term: body.term, interpretation_review_id: body.original_review_id ?? body.id,
        review_id: body.id, sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
    }
    if (path.includes('/references?')) return { json: async () => ({ ...scope, purpose: 'purchase_contract', items: [8, 18].map(n => ({ ...scope, artifact_id: id(n), source_version: 1, reference_type: 'term_source', link_id: null, status: 'available_for_review', purpose: 'purchase_contract', sha256: 'a'.repeat(64), verification_id: id(9), source_created_at: stamp, checked_at: stamp, review_approved: false, execution_authorized: false })), next_after: null, checked_at: stamp, execution_authorized: false }) };
    const artifact = path.includes(id(18)) ? id(18) : id(8), term = 'closing_deadline';
    return { json: async () => ({ ...scope, term, artifact_id: artifact, status: 'ready_for_human_review',
      candidate: { artifact_id: artifact, source_version: 1, verification_id: id(9), sha256: 'a'.repeat(64), policy_id: id(10), expected_sequence: mock.withdrawal ? 4 : 0, max_expires_at: expiry },
      original_source: { term, artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64), locator: 'Original closing clause', verification_id: id(9) },
      withdrawal: mock.withdrawal ? { review_id: id(7), artifact_id: id(8), source_version: 1, verification_id: id(9), policy_id: id(10), expected_sequence: 4 } : null,
      current_review: { ...scope, kind: 'deadline_resolution', term, sequence: mock.withdrawal ? 4 : 0, review_sequence: mock.withdrawal ? 1 : null, review_id: mock.withdrawal ? id(7) : null, interpretation_review_id: mock.withdrawal ? id(7) : null,
        original_term: { precision: 'date', calendar_date: '2026-11-20', instant: null }, resolution: mock.withdrawal ? { term, calendar_date: '2026-11-20', local_time: '17:00:00', time_zone: 'America/Chicago', resolved_instant: '2026-11-20T17:00:00-06:00', basis: 'explicit_document_time', source: { term, artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64), locator: 'Closing clause' }, rationale: 'Synthetic explicit time recorded in original document.' } : null,
        status: mock.withdrawal ? 'approved' : 'not_reviewed', approval_current: mock.withdrawal, expires_at: mock.withdrawal ? expiry : null, checked_at: stamp, execution_authorized: false }, checked_at: stamp, execution_authorized: false }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DeadlineReviewForm context={context} disabled={disabled} onPending={mock.pending} onSaved={mock.saved} /></QueryClientProvider>); }
async function choose(artifact = id(8)) {
  fireEvent.click(screen.getByText('Open date review')); await screen.findAllByRole('option', { name: /Document from version 1/ });
  fireEvent.change(screen.getByLabelText('Interpretation source'), { target: { value: artifact } });
  await screen.findByText('Original closing deadline: 2026-11-20');
}
async function fill() {
  for (const [label, value] of [['Local cutoff time', '17:00:00'], ['Named time zone', 'America/Chicago'], ['Explicit UTC offset', '-06:00'], ['Interpretation source clause', 'Closing clause page 4'], ['Interpretation rationale', 'Personally reviewed the explicit original time and named zone.'], ['Date-review decision notes', 'Approve the exact synthetic date interpretation after personal review.']]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole('checkbox')); await waitFor(() => expect(screen.getByText('Record date interpretation')).toBeEnabled());
}
it('opens intentionally and holds navigation until unsaved work closes', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Open date review'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); fireEvent.click(screen.getByText('Close without saving'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false)); expect(mock.fetch.mock.calls.some(c => c[1]?.method === 'POST')).toBe(false);
});
it('keeps time blank and requires exact personal interpretation before approval', async () => {
  open(); await choose(); expect(screen.getByLabelText('Local cutoff time')).toHaveValue(''); expect(screen.getByText('Record date interpretation')).toBeDisabled();
  await fill(); fireEvent.change(screen.getByLabelText('Explicit UTC offset'), { target: { value: '-05:00' } });
  expect(screen.getByRole('checkbox')).not.toBeChecked(); expect(screen.getByText('Record date interpretation')).toBeDisabled();
});
it('recovers exactly the original approval after lost response and reload', async () => {
  const view = open(); await choose(); await fill(); mock.lose = true;
  fireEvent.click(screen.getByText('Record date interpretation')); await screen.findByText(/Save is unconfirmed/);
  const stored = sessionStorage.getItem(deadlineKey(id(1), id(2))); expect(stored).not.toBeNull();
  view.unmount(); mock.lose = false; open(); fireEvent.click(screen.getByText('Retry saved date review')); await screen.findByText(/Date review recorded/);
  const posts = mock.fetch.mock.calls.filter(c => c[1]?.method === 'POST'); expect(posts).toHaveLength(2); expect(posts[0][1].body).toBe(posts[1][1].body);
  expect(JSON.parse(posts[0][1].body).resolution.calendar_date).toBe('2026-11-20'); expect(sessionStorage.length).toBe(0);
});
it('withdraws the original review despite another selected document and newer shared cursor', async () => {
  mock.withdrawal = true; open(); await choose(id(18));
  fireEvent.change(screen.getByLabelText('Date-review decision notes'), { target: { value: 'Withdraw my original synthetic date interpretation for further review.' } });
  fireEvent.click(screen.getByText('Withdraw my date review')); await screen.findByText(/Date review recorded/);
  const body = JSON.parse(mock.fetch.mock.calls.find(c => c[1]?.method === 'POST')![1].body);
  expect(body).toMatchObject({ artifact_id: id(8), original_review_id: id(7), expected_sequence: 4, resolution: null, personally_reviewed: false });
});
it('holds corrupt recovery without issuing requests', async () => {
  sessionStorage.setItem(deadlineKey(id(1), id(2)), '{broken'); open(); expect(screen.getByRole('alert')).toHaveTextContent('reconciliation');
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true)); expect(mock.fetch).not.toHaveBeenCalled();
});
it('cannot open when an adjacent step is active', () => { open(true); expect(screen.getByText('Open date review')).toBeDisabled(); });
