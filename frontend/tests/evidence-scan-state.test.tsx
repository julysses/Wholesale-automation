import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EvidenceUploadPanel } from '@/components/acquisition/EvidenceUploadPanel';
import { parseScanState } from '@/lib/acquisition/evidence';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), scan: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error {} }));
const W = '10000000-0000-4000-8000-000000000001', C = '20000000-0000-4000-8000-000000000001', U = '30000000-0000-4000-8000-000000000001';
const A = '40000000-0000-4000-8000-000000000001', O = '50000000-0000-4000-8000-000000000001';
const path = `/api/acquisition/workspaces/${W}/campaigns/${C}/evidence`;
function result() { return { workspace_id: W, campaign_id: C, artifact_id: A, status: 'no_detection_observed', quarantined: false,
  observation_id: O, checked_at: new Date().toISOString(), preview_authorized: false, content_approved: false, execution_authorized: false }; }
function records() { const now = new Date().toISOString(); return { workspace_id: W, campaign_id: C, purpose: 'mail_content', current_policy: null,
  items: [{ workspace_id: W, campaign_id: C, artifact_id: A, purpose: 'mail_content', expected_sha256: 'a'.repeat(64), expected_byte_size: 42,
    media_type: 'text/plain', retention_policy_id: O, created_at: '2026-01-01T00:00:00Z', retain_until: '2099-01-01T00:00:00Z', revoked_at: null,
    checked_at: now, status: 'pending_verification', bytes_verified: false, content_approved: false, execution_authorized: false }],
  next_after: null, checked_at: now, execution_authorized: false, upload_enabled: false }; }
beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks(); mock.scan.mockImplementation(result);
  mock.fetch.mockImplementation(async (url: string) => new Response(JSON.stringify(url.endsWith('/scan-state') ? await mock.scan() : url.endsWith('/memberships')
    ? [{ workspace_id: W, user_id: U, role: 'owner', status: 'active' }] : records())));
});
afterEach(() => vi.restoreAllMocks());
async function open() {
  render(<QueryClientProvider client={new QueryClient()}><EvidenceUploadPanel userId={U} workspace={W} campaign={C} onPending={() => {}}/></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Add or review evidence files' }));
  return screen.findByRole('button', { name: 'Check file status' });
}
it('checks only the chosen file on demand and keeps scan, preview, content and mailing approval separate', async () => {
  const check = await open(); expect(mock.scan).not.toHaveBeenCalled(); fireEvent.click(check);
  await screen.findByText('No threat detected in the current scan');
  expect(mock.fetch).toHaveBeenCalledWith(`${path}/${A}/scan-state`, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(screen.getByText(/Next: Content review is still required/)).toBeVisible();
  expect(screen.queryByRole('img')).toBeNull(); expect(screen.queryByRole('button', { name: /approve|send|preview/i })).toBeNull();
});
it('hides a previous clean result during refresh and after an access denial', async () => {
  const check = await open(); fireEvent.click(check); await screen.findByText('No threat detected in the current scan');
  let reject!: (error: Error) => void; mock.scan.mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
  fireEvent.click(check); await screen.findByText('Checking current file status…');
  expect(screen.queryByText('No threat detected in the current scan')).toBeNull();
  reject(new Error('Forbidden')); await screen.findByRole('alert');
  expect(screen.queryByText('No threat detected in the current scan')).toBeNull();
});
it('explains a detection hold even when the file has also been withdrawn', async () => {
  mock.scan.mockImplementation(() => ({ ...result(), status: 'revoked', quarantined: true, observation_id: null }));
  fireEvent.click(await open()); await screen.findByText('File withdrawn');
  expect(screen.getByText('A recorded detection also keeps this file on hold.')).toBeVisible();
});
it('removes the prior result when overall evidence access is refreshed and denied', async () => {
  fireEvent.click(await open()); await screen.findByText('No threat detected in the current scan');
  mock.fetch.mockRejectedValue(new Error('Forbidden')); fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence status' }));
  await waitFor(() => expect(screen.queryByText('No threat detected in the current scan')).toBeNull());
  expect(screen.queryByRole('button', { name: 'Check file status' })).toBeNull();
});
it.each([
  { workspace_id: C }, { campaign_id: W }, { artifact_id: O }, { preview_authorized: true }, { content_approved: true },
  { execution_authorized: true }, { quarantined: true }, { observation_id: null }, { status: 'not_scanned' },
  { checked_at: '2000-01-01T00:00:00Z' }, { checked_at: '2099-01-01T00:00:00Z' }, { private_payload: 'hidden' },
])('rejects mismatched, stale, contradictory or authority-bearing status: %j', changes => {
  expect(() => parseScanState({ ...result(), ...changes }, W, C, A)).toThrow();
});
