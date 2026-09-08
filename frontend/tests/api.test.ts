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
