import { describe, expect, it, vi } from 'vitest';

const getSession = vi.hoisted(() => vi.fn());
vi.mock('@/lib/supabase', () => ({ supabase: { auth: { getSession } } }));
import { apiFetch } from '@/lib/api';

describe('authenticated API requests', () => {
  it('preserves JSON and multipart bodies while attaching the session', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetcher);
    const body = new FormData(); body.append('file', new Blob(['a,b']), 'test.csv');
    await apiFetch('/api/buyers/import', { method: 'POST', body });
    expect(fetcher.mock.calls[0][1].body).toBe(body);
    expect(fetcher.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer test-token');
    expect(fetcher.mock.calls[0][1].headers.has('Content-Type')).toBe(false);
    await apiFetch('/api/ai/qualify-lead', { headers: { 'Content-Type': 'application/json' }, body: '{}' });
    expect(fetcher.mock.calls[1][1].headers.get('Content-Type')).toBe('application/json');
  });
  it('does not send a request without a session', async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    await expect(apiFetch('/api/ai/test')).rejects.toThrow('sign in');
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('never sends the token to an external URL', async () => {
    await expect(apiFetch('https://example.com/api/test')).rejects.toThrow('Invalid API path');
  });
  it('rejects failed operations instead of allowing success toasts', async () => {
    getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Database unavailable"}', { status: 503 })));
    await expect(apiFetch('/api/buyers/score')).rejects.toThrow('Database unavailable');
  });
});

it.each([
  ['/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/cost-evidence','POST',409,'true',true],
  ['/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/cost-evidence','POST',503,'true',false],
  ['/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/cost-evidence','POST',409,'false',false],
  ['/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/cost-evidence','GET',409,'true',false],
  ['/api/buyers/import','POST',409,'true',false],
])('scopes confirmed cost rejection to its write contract %s %s %s',async(path,method,status,header,rejected)=>{
  getSession.mockResolvedValue({data:{session:{access_token:'test-token'}}});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"detail":"rejected"}',{status:Number(status),headers:{'X-Acquisition-Cost-Rejected':String(header)}})));
  await expect(apiFetch(String(path),{method:String(method)})).rejects.toMatchObject({rejectedCost:rejected});
});

it.each(['120', '5', '0', '-1', '121', 'Wed, 21 Oct 2026 07:28:00 GMT'])('only accepts bounded retry seconds: %s', async value => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 429, headers: { 'Retry-After': value } })));
  await expect(apiFetch('/api/acquisition/test')).rejects.toMatchObject({ retryAfterSeconds: ['120', '5'].includes(value) ? Number(value) : undefined });
});

it.each([
  ['POST', 409, 'true', true], ['POST', 401, 'true', true], ['POST', 403, 'true', true],
  ['POST', 503, 'true', false], ['POST', 409, 'false', false], ['GET', 409, 'true', false],
])('only recognizes explicit contract transaction rejection %s %s %s', async (method, status, header, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Contract-Rejected': String(header) } })));
  await expect(apiFetch('/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/drafts', { method: String(method) })).rejects.toMatchObject({ rejectedContract: rejected });
  await expect(apiFetch('/api/buyers/import', { method: String(method) })).rejects.toMatchObject({ rejectedContract: false });
});
it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('scopes document rejection to its exact registration route (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Document-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/versions/1/documents';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedDocument: rejected });
  for (const other of ['/api/buyers/import', `${path}/40000000-0000-4000-8000-000000000001/bytes?purpose=purchase_contract`, `${path}?purpose=purchase_contract`])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedDocument: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('recognizes only definitive review rejection (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Review-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/versions/1/reviews/contract_review';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedReview: rejected });
  for (const other of ['/api/buyers/import', `${path}/documents/40000000-0000-4000-8000-000000000001/candidate`, `${path}?other=true`])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedReview: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('recognizes only definitive terms rejection (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Terms-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/terms';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedTerms: rejected });
  for (const other of ['/api/buyers/import', `${path}/versions`, `${path}?other=true`])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedTerms: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [503, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('scopes reference rejection to exact link or withdrawal writes (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Link-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/versions/2/document-links';
  for (const endpoint of [path, `${path}/40000000-0000-4000-8000-000000000001/withdrawals`]) await expect(apiFetch(endpoint, { method: String(method) })).rejects.toMatchObject({ rejectedLink: rejected });
  for (const other of ['/api/buyers/import', `${path}/references`, `${path}?other=true`]) await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedLink: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [429, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('scopes signature rejection to its exact review write (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Signature-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/versions/3/signature-review';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedSignature: rejected, rejectedReview: false, rejectedContract: false });
  for (const other of ['/api/buyers/import', `${path}/candidate`, `${path}?other=true`, path.replace('signature-review', 'reviews/contract_review')])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedSignature: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [429, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('scopes lifecycle rejection to its exact review write (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Transition-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/transitions';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedTransition: rejected, rejectedReview: false, rejectedContract: false });
  for (const other of ['/api/buyers/import', `${path}/candidate`, `${path}?other=true`, path.replace('transitions', 'terms')])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedTransition: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [429, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('scopes execution-review rejection to its exact write (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Execution-Review-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/versions/3/execution-review';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedExecution: rejected, rejectedReview: false, rejectedSignature: false });
  for (const other of ['/api/buyers/import', `${path}/documents/40000000-0000-4000-8000-000000000001/candidate`, `${path}?other=true`, path.replace('execution-review', 'signature-review')])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedExecution: false });
});

it.each([[403, 'true', 'POST', true], [409, 'true', 'POST', true], [401, 'true', 'POST', true], [503, 'true', 'POST', false], [429, 'true', 'POST', false], [403, 'false', 'POST', false], [403, 'true', 'GET', false]])('scopes deadline-review rejection to its exact write (%s %s %s)', async (status, header, method, rejected) => {
  getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } } });
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}', { status: Number(status), headers: { 'X-Acquisition-Deadline-Review-Rejected': String(header) } })));
  const path = '/api/acquisition/workspaces/20000000-0000-4000-8000-000000000001/contracts/30000000-0000-4000-8000-000000000001/versions/3/deadline-reviews';
  await expect(apiFetch(path, { method: String(method) })).rejects.toMatchObject({ rejectedDeadline: rejected, rejectedReview: false, rejectedSignature: false });
  for (const other of ['/api/buyers/import', `${path}/documents/40000000-0000-4000-8000-000000000001/candidate`, `${path}?other=true`, path.replace('deadline-reviews', 'signature-review')])
    await expect(apiFetch(other, { method: String(method) })).rejects.toMatchObject({ rejectedDeadline: false });
});
