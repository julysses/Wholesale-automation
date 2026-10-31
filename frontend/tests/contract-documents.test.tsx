import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { webcrypto, createHash } from 'node:crypto';
import { ContractDocuments } from '@/components/acquisition/ContractDocuments';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), register: vi.fn(), upload: vi.fn(), enabled: true, policy: true, role: 'owner', wrongScope: false }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { constructor(message: string, public status: number, public rejectedCreate = false, public rejectedCost = false, public retryAfterSeconds?: number) { super(message); } } }));
const W = '10000000-0000-4000-8000-000000000001', C = '20000000-0000-4000-8000-000000000001', U = '30000000-0000-4000-8000-000000000001', P = '40000000-0000-4000-8000-000000000001';
const context = { userId: U, workspaceId: W, contractId: C, contractVersion: 1, propertyId: P, leadId: P, offerId: P };
const key = `wholesale.contract.document:v1:${U}:${W}`, path = `/api/acquisition/workspaces/${W}/contracts/${C}/versions/1/documents`;
const body = 'Synthetic original file contents', digest = createHash('sha256').update(body).digest('hex');
function pending(stage: 'register' | 'upload' = 'upload') { return { version: 1, context, stage, registration: { id: '50000000-0000-4000-8000-000000000001', purpose: 'purchase_contract', expected_sha256: digest, expected_byte_size: body.length, media_type: 'text/plain', retention_policy_id: P, provenance_note: 'Synthetic reviewed source for this content.' } }; }
function candidates() { return { workspace_id: mock.wrongScope ? C : W, contract_id: C, contract_version: 1, purpose: 'purchase_contract', current_policy: mock.policy ? { id: P, workspace_id: W, purpose: 'purchase_contract', version: 1, retention_seconds: 86400, valid_from: '2026-01-01T00:00:00Z', valid_until: '2099-01-01T00:00:00Z' } : null, items: [], next_after: null, checked_at: new Date().toISOString(), execution_authorized: false, upload_enabled: mock.enabled }; }
function uploaded() { const saved = JSON.parse(sessionStorage.getItem(key)!), r = saved.registration, now = new Date().toISOString(); return { workspace_id: W, contract_id: C, contract_version: 1, artifact_id: r.id, purpose: 'purchase_contract', sha256: r.expected_sha256, byte_size: r.expected_byte_size, media_type: r.media_type, retention_policy_id: r.retention_policy_id, checked_at: now, registry_checked_at: now, retain_until: '2099-01-01T00:00:00Z', status: 'stored_unverified', verifier_version: 'acquisition-contract-document-bytes-v1', registry_verifier_version: 'acquisition-contract-document-registry-v1', upload_version: 'acquisition-contract-document-upload-v1', write_outcome: 'stored_or_existing', scan_status: 'not_scanned', byte_match_observed: true, verification_persisted: false, legal_review_approved: false, execution_authorized: false }; }
function file(value = body) {
  const f = new File([value], 'evidence.txt', { type: 'text/plain' });
  // Node 20 WebCrypto rejects jsdom-realm ArrayBuffers. Preserve real hashing
  // with a Node-realm buffer and exclude unrelated pooled bytes.
  Object.defineProperty(f, 'arrayBuffer', { value: async () => {
    const bytes = Buffer.from(value);
    return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  } });
  return f;
}
beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks(); mock.enabled = true; mock.policy = true; mock.role = 'owner'; mock.wrongScope = false;
  vi.stubGlobal('crypto', { subtle: webcrypto.subtle, randomUUID: () => '60000000-0000-4000-8000-000000000001' });
  mock.register.mockImplementation(r => ({ artifact_id: r.id, workspace_id: W, contract_id: C, contract_version: 1, retain_until: '2099-01-01T00:00:00Z', duplicate: false, bytes_verified: false, execution_authorized: false }));
  mock.upload.mockImplementation(uploaded);
  mock.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const result = init?.method === 'POST' ? url === path ? await mock.register(JSON.parse(String(init.body))) : await mock.upload(url, init)
      : url.endsWith('/memberships') ? [{ workspace_id: W, user_id: U, status: 'active', role: mock.role }] : candidates();
    return new Response(JSON.stringify(result));
  });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function view(held = vi.fn()) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ContractDocuments context={context} onPending={held}/></QueryClientProvider>); }
async function open() { view(); await waitFor(() => expect(screen.getByLabelText('Original document')).toBeEnabled()); }
async function select(value = body) { fireEvent.change(screen.getByLabelText('Original document'), { target: { files: [file(value)] } }); await screen.findByText(/File checked locally/); }
async function prepare() { await open(); await select(); fireEvent.change(screen.getByLabelText('Where did this document come from?'), { target: { value: 'Original source supplied for the content review.' } }); }
it('hashes locally and sends one registration then the same raw file without preview or approval', async () => {
  await prepare(); expect(mock.register).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button', { name: 'Save and upload document' }));
  await screen.findByText(/Upload confirmed/);
  expect(mock.register).toHaveBeenCalledTimes(1); expect(mock.register.mock.calls[0][0]).toMatchObject({ expected_sha256: digest, expected_byte_size: body.length, media_type: 'text/plain', retention_policy_id: P });
  expect(mock.upload.mock.calls[0][1].body).toBeInstanceOf(File); expect(mock.upload.mock.calls[0][1].headers).toEqual({ 'Content-Type': 'application/octet-stream' });
  expect(sessionStorage.getItem(key)).toBeNull(); expect(screen.queryByRole('img')).toBeNull(); expect(screen.queryByText(digest)).toBeNull();
});
it.each(['paused', 'policy', 'role', 'scope'])('keeps new writes closed for %s', async mode => {
  mock.enabled = mode !== 'paused'; mock.policy = mode !== 'policy'; mock.role = mode === 'role' ? 'acquisition_caller' : 'owner'; mock.wrongScope = mode === 'scope';
  view(); await waitFor(() => expect(mock.fetch).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('button', { name: 'Save and upload document' })).toBeDisabled(); expect(mock.register).not.toHaveBeenCalled();
});
it('retains and retries exactly the registration after a lost reply', async () => {
  mock.register.mockRejectedValueOnce(new ApiError('Lost reply', 503)); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Save and upload document' }));
  await screen.findByText(/The result is unconfirmed/); const saved = sessionStorage.getItem(key); expect(JSON.parse(saved!).stage).toBe('register');
  expect(saved).not.toContain('evidence.txt'); expect(mock.upload).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Check saved registration' })); await screen.findByText(/Upload confirmed/);
  expect(mock.register.mock.calls[1][0]).toEqual(mock.register.mock.calls[0][0]); expect(mock.upload).toHaveBeenCalledTimes(1);
});
it('recovers a saved upload only with the original file and never registers another record', async () => {
  sessionStorage.setItem(key, JSON.stringify(pending())); const held = vi.fn(); view(held);
  await screen.findByText(/Recover the saved document/); expect(screen.getByRole('button', { name: 'Retry saved document upload' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Original document'), { target: { files: [file('different contents')] } }); await screen.findByText(/Choose the exact original file/);
  expect(screen.getByRole('button', { name: 'Retry saved document upload' })).toBeDisabled(); await select();
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved document upload' })); await screen.findByText(/Upload confirmed/);
  expect(mock.register).not.toHaveBeenCalled(); expect(held).toHaveBeenCalledWith(true); expect(held).toHaveBeenLastCalledWith(false);
});
it('retains the file checkpoint on uncertain upload and waits on server capacity', async () => {
  mock.upload.mockRejectedValueOnce(new ApiError('Unknown', 503)).mockRejectedValueOnce(new ApiError('Busy', 429, false, false, 120));
  await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Save and upload document' })); await screen.findByText(/The result is unconfirmed/);
  const saved = sessionStorage.getItem(key); expect(JSON.parse(saved!).stage).toBe('upload');
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved document upload' })); await screen.findByText(/Upload capacity is occupied/);
  expect(screen.getByRole('button', { name: 'Retry saved document upload' })).toBeDisabled(); expect(sessionStorage.getItem(key)).toBe(saved); expect(mock.register).toHaveBeenCalledTimes(1);
});
it('preserves the exact request when an upload receipt claims approval', async () => {
  mock.upload.mockImplementation(() => ({ ...uploaded(), legal_review_approved: true })); await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Save and upload document' }));
  await screen.findByText(/The result is unconfirmed/); expect(JSON.parse(sessionStorage.getItem(key)!).stage).toBe('upload'); expect(screen.queryByText(/Upload confirmed/)).toBeNull();
});
it('blocks corrupted or cross-user recovery without sending anything', async () => {
  sessionStorage.setItem(key, JSON.stringify({ ...pending(), context: { ...context, userId: C } })); view(); await screen.findByRole('alert'); expect(screen.getByRole('button', { name: 'Save and upload document' })).toBeDisabled(); expect(mock.register).not.toHaveBeenCalled();
});
it('releases only an explicitly rejected first registration', async () => {
  mock.register.mockRejectedValueOnce(Object.assign(new ApiError('Rejected', 403), { rejectedDocument: true }));
  await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Save and upload document' }));
  await screen.findByText(/The document was not registered/);
  expect(sessionStorage.getItem(key)).toBeNull(); expect(mock.upload).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByLabelText('Document type')).toBeEnabled());
});
it('never clears an earlier uncertain registration when its retry is rejected', async () => {
  mock.register.mockRejectedValueOnce(new ApiError('Lost reply', 503));
  await prepare(); fireEvent.click(screen.getByRole('button', { name: 'Save and upload document' }));
  await screen.findByText(/The result is unconfirmed/); const saved = sessionStorage.getItem(key);
  mock.register.mockRejectedValueOnce(Object.assign(new ApiError('Rejected', 403), { rejectedDocument: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Check saved registration' }));
  await waitFor(() => expect(mock.register).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Check saved registration' })).toBeEnabled());
  expect(sessionStorage.getItem(key)).toBe(saved); expect(mock.upload).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Document type')).toBeDisabled();
});
