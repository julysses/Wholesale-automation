import { supabase } from '@/lib/supabase';

/** Send the current session to our API and surface unsuccessful operations. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  if (!path.startsWith('/api/') || path.includes('\\')) {
    throw new Error('Invalid API path');
  }
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session) throw new Error('Your session has expired. Please sign in again.');
  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${data.session.access_token}`);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  }
  return response;
}
