import { supabase } from '@/lib/supabase';

export class ApiError extends Error {
  status: number;
  rejectedCreate: boolean;
  rejectedCost: boolean;
  constructor(message: string, status: number, rejectedCreate = false, rejectedCost = false) {
    super(message); this.status = status; this.rejectedCreate = rejectedCreate; this.rejectedCost = rejectedCost;
  }
}

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
    throw new ApiError(typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`, response.status,
      response.headers.get('X-Deal-Create-Rejected') === 'true',
      init?.method === 'POST' && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/cost-evidence$/.test(path)
        && [401, 403, 409].includes(response.status) && response.headers.get('X-Acquisition-Cost-Rejected') === 'true');
  }
  return response;
}
