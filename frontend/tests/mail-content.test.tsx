import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MailContentReviews } from '../src/components/acquisition/MailContentReviews';
import { ApiError } from '@/lib/api';
import { ids, templateRow, destinationRow, prepared, reviewRow, currentState, internalProof, leadRow } from './fixtures/mail-content';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), save: vi.fn(), prepare: vi.fn(), proof: vi.fn(), state: vi.fn(), role: 'owner', history: [] as unknown[], templateScope: '' }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { constructor(message: string, public status: number) { super(message); } } }));
const root = `/api/acquisition/workspaces/${ids.workspace}/campaigns/${ids.campaign}/mail-content`;
const key = `acquisition-content-request:v1:${ids.user}:${ids.workspace}:${ids.campaign}`;
const pending = { content_id: ids.content, review: { id: ids.review, expected_version: 0, action: 'approved', creative_id: ids.creative, destination_review_id: ids.destination, company_name: 'Hilltop Home Company', preparation_hash: 'a'.repeat(64), evidence_ref: ids.review, evidence_hash: 'b'.repeat(64), expires_at: '2098-01-01T00:00:00Z', note: 'Reviewed the complete content and retained evidence.' } };
beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks(); mock.role = 'owner'; mock.history = []; mock.templateScope = ids.workspace;
  mock.prepare.mockImplementation(prepared); mock.proof.mockImplementation(internalProof); mock.state.mockImplementation(currentState);
  mock.save.mockImplementation((body, path) => ({ review_id: body.id, workspace_id: ids.workspace, content_id: path.split('/').at(-2), version: body.expected_version + 1, duplicate: false, execution_authorized: false }));
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') { const body = JSON.parse(String(init.body)); return { json: async () => path.endsWith('/prepare') ? mock.prepare(body) : path.endsWith('/proof') ? mock.proof(body) : mock.save(body, path) }; }
    return { json: async () => path.endsWith('/memberships') ? [{ workspace_id: ids.workspace, user_id: ids.user, status: 'active', role: mock.role }]
      : path.includes('/mail-templates?') ? { items: [{ ...templateRow, workspace_id: mock.templateScope }], next_after: null }
      : path.includes('/mail-destinations?') ? { items: [destinationRow], next_after: null }
      : path.includes('/leads?') ? [leadRow]
      : path.startsWith(`${root}?`) ? { items: mock.history, next_after: null } : mock.state() };
  });
});
function view(onPending = vi.fn()) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MailContentReviews userId={ids.user} workspace={ids.workspace} campaign={ids.campaign} onPending={onPending}/></QueryClientProvider>); }
async function open() { view(); fireEvent.click(screen.getByRole('button', { name: 'Review mail content' })); await waitFor(() => expect(screen.getByLabelText('Saved message')).toBeEnabled()); }
async function fill() {
  fireEvent.change(screen.getByLabelText('Saved message'), { target: { value: ids.creative } }); fireEvent.change(screen.getByLabelText('Reviewed response destination'), { target: { value: ids.destination } });
  fireEvent.click(screen.getByRole('button', { name: 'Prepare content for review' })); await screen.findByText(/Content prepared for your review/);
  fireEvent.change(screen.getByLabelText('Content evidence reference'), { target: { value: ids.review } }); fireEvent.change(screen.getByLabelText('Content evidence SHA-256 digest'), { target: { value: 'b'.repeat(64) } });
  fireEvent.change(screen.getByLabelText('Content approval expires at (ISO date with time zone)'), { target: { value: '2098-01-01T00:00:00Z' } });
  fireEvent.change(screen.getByLabelText('Content review or withdrawal reason'), { target: { value: pending.review.note } }); fireEvent.click(screen.getByRole('checkbox'));
}
it('prepares exact saved sources and records an explicit non-executing approval', async () => {
  await open(); await fill(); expect(mock.prepare).toHaveBeenCalledWith({ creative_id: ids.creative, destination_review_id: ids.destination, company_name: 'Hilltop Home Company' });
  expect(screen.getByText(/Hello Hilltop Home Company: \[Property address\]/)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Record content approval' })); await screen.findByText(/Content decision recorded/);
  expect(mock.save.mock.calls[0][0]).toEqual({ ...pending.review, id: expect.any(String) }); expect(sessionStorage.getItem(key)).toBeNull();
});
it('invalidates preparation and attestation when wording changes', async () => {
  await open(); await fill(); fireEvent.change(screen.getByLabelText('Company name printed on mail'), { target: { value: 'Changed name' } });
  expect(screen.getByRole('button', { name: 'Record content approval' })).toBeDisabled(); expect(screen.getByRole('checkbox')).not.toBeChecked(); expect(mock.save).not.toHaveBeenCalled();
});
it('holds an uncertain decision across remount and retries its identical body', async () => {
  sessionStorage.setItem(key, JSON.stringify(pending)); mock.save.mockRejectedValueOnce(new Error('lost')); const held = vi.fn(); const first = view(held);
  fireEvent.click(await screen.findByRole('button', { name: 'Retry exact content decision' })); await screen.findByText(/decision is unconfirmed/); expect(held).toHaveBeenLastCalledWith(`${ids.campaign}:content`, true);
  first.unmount(); view(); fireEvent.click(screen.getByRole('button', { name: 'Retry exact content decision' })); await screen.findByText(/Content decision recorded/);
  expect(mock.save.mock.calls.map(c => c[0])).toEqual([pending.review, pending.review]); expect(sessionStorage.getItem(key)).toBeNull();
});
it('retains an uncertain request after denied retry authority', async () => {
  sessionStorage.setItem(key, JSON.stringify(pending)); mock.save.mockRejectedValue(new ApiError('Denied', 403)); view(); fireEvent.click(await screen.findByRole('button', { name: 'Retry exact content decision' }));
  await screen.findByText(/decision is unconfirmed/); expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(pending);
});
it('clears a first definitive rejection and requires fresh preparation', async () => {
  mock.save.mockRejectedValue(new ApiError('Stale', 409)); await open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Record content approval' }));
  await screen.findByText(/Decision rejected/); expect(sessionStorage.getItem(key)).toBeNull(); expect(screen.getByRole('button', { name: 'Record content approval' })).toBeDisabled();
});
it.each([{ execution_authorized: true }, { workspace_id: ids.user }, { version: 99 }])('retains inconsistent receipt %j', async override => {
  sessionStorage.setItem(key, JSON.stringify(pending)); mock.save.mockResolvedValue({ review_id: ids.review, workspace_id: ids.workspace, content_id: ids.content, version: 1, duplicate: true, execution_authorized: false, ...override }); view();
  fireEvent.click(await screen.findByRole('button', { name: 'Retry exact content decision' })); await screen.findByText(/decision is unconfirmed/); expect(sessionStorage.getItem(key)).not.toBeNull();
});
it('rejects corrupted storage and extra authority fields without sending', async () => {
  sessionStorage.setItem(key, JSON.stringify({ ...pending, execution_authorized: true })); const held = vi.fn(); view(held); await screen.findByRole('alert'); expect(held).toHaveBeenLastCalledWith(`${ids.campaign}:content`, true); expect(mock.save).not.toHaveBeenCalled();
});
it('rejects cross-workspace source lists and preparation responses', async () => {
  mock.templateScope = ids.user; await openWithoutReady(); await screen.findByText('Message versions could not be verified.'); expect(screen.getByLabelText('Saved message')).toBeDisabled(); expect(mock.prepare).not.toHaveBeenCalled();
});
async function openWithoutReady() { view(); fireEvent.click(screen.getByRole('button', { name: 'Review mail content' })); }
it('requires explicit current version loading and sends withdrawal without replacement evidence', async () => {
  mock.history = [reviewRow()]; await open(); fireEvent.click(await screen.findByRole('button', { name: `Inspect content ${ids.content}` })); await screen.findByText(/Current content: approved/);
  expect(screen.getByRole('button', { name: 'Prepare content for review' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Content review or withdrawal reason'), { target: { value: pending.review.note } }); fireEvent.click(screen.getByRole('button', { name: 'Withdraw content approval' }));
  await screen.findByText(/Content decision recorded/); expect(mock.save.mock.calls[0][0]).toEqual({ id: expect.any(String), expected_version: 1, action: 'withdrawn', note: pending.review.note });
});
it('lets an operator inspect approved content and preview only the enrolled property as inert text', async () => {
  mock.role = 'operator'; mock.history = [reviewRow()]; await openWithoutReady(); fireEvent.click(await screen.findByRole('button', { name: `Inspect content ${ids.content}` })); await screen.findByText(/Current content: approved/);
  await waitFor(() => expect(screen.getByLabelText('Preview property')).toBeEnabled()); fireEvent.change(screen.getByLabelText('Preview property'), { target: { value: ids.lead } }); fireEvent.click(screen.getByRole('button', { name: 'Prepare internal preview' }));
  await screen.findByText(/Internal content preview — not ready/); expect(mock.proof).toHaveBeenCalledWith({ lead_id: ids.lead }); expect(document.querySelector('script')).toBeNull(); expect(screen.getByText(/<script>unsafe/)).toBeVisible(); expect(screen.getByRole('button', { name: 'Record content approval' })).toBeDisabled();
});
it.each([{ review_id: ids.user }, { execution_authorized: true }, { property_id: ids.user }, { source_checked_at: '2026-01-01T00:00:00Z' }])('rejects inconsistent or stale preview %j', async override => {
  mock.history = [reviewRow()]; mock.proof.mockImplementation(() => ({ ...internalProof(), ...override })); await open(); fireEvent.click(await screen.findByRole('button', { name: `Inspect content ${ids.content}` }));
  await waitFor(() => expect(screen.getByLabelText('Preview property')).toBeEnabled()); fireEvent.change(screen.getByLabelText('Preview property'), { target: { value: ids.lead } }); fireEvent.click(screen.getByRole('button', { name: 'Prepare internal preview' }));
  await screen.findByText(/Preview unavailable/); expect(screen.queryByText(/Internal content preview — not ready/)).toBeNull();
});
it('sends nothing when storage cannot preserve the new decision', async () => {
  await open(); await fill(); const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
  fireEvent.click(screen.getByRole('button', { name: 'Record content approval' })); await screen.findByText(/No decision was sent/); expect(mock.save).not.toHaveBeenCalled(); storage.mockRestore();
});
it.each([{ workspace_id: ids.user }, { campaign_id: ids.user }])('rejects preparation scoped elsewhere %j', async override => {
  mock.prepare.mockImplementation(() => { const p = prepared(); return { ...p, snapshot: { ...p.snapshot, ...override } }; });
  await open(); fireEvent.change(screen.getByLabelText('Saved message'), { target: { value: ids.creative } }); fireEvent.change(screen.getByLabelText('Reviewed response destination'), { target: { value: ids.destination } });
  fireEvent.click(screen.getByRole('button', { name: 'Prepare content for review' })); await screen.findByText(/Content could not be prepared/); expect(screen.getByRole('button', { name: 'Record content approval' })).toBeDisabled();
});
it('requires reloading an updated review version before preparing another decision', async () => {
  mock.history = [reviewRow()]; await open(); fireEvent.click(await screen.findByRole('button', { name: `Inspect content ${ids.content}` })); await screen.findByText(/Current content: approved/);
  fireEvent.click(screen.getByRole('button', { name: 'Load current content for review' })); expect(screen.getByRole('button', { name: 'Prepare content for review' })).toBeEnabled();
  mock.state.mockImplementation(() => { const s = currentState(); s.version = 2; s.latest_review.version = 2; return s; });
  fireEvent.click(screen.getByRole('button', { name: 'Refresh content sources and status' })); await screen.findByText(/Current content: approved · Version 2/);
  expect(screen.getByRole('button', { name: 'Prepare content for review' })).toBeDisabled(); expect(mock.save).not.toHaveBeenCalled();
});
it.each([{ execution_authorized: true }, { review_current: false }, { content_id: ids.user }])('blocks inconsistent current-state response %j', async override => {
  mock.history = [reviewRow()]; mock.state.mockImplementation(() => ({ ...currentState(), ...override })); await open(); fireEvent.click(await screen.findByRole('button', { name: `Inspect content ${ids.content}` }));
  await screen.findByText('Current content could not be verified.'); expect(screen.getByRole('button', { name: 'Load current content for review' })).toBeDisabled(); expect(screen.queryByRole('button', { name: 'Prepare internal preview' })).toBeNull();
});
