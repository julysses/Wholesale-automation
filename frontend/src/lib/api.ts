import { supabase } from '@/lib/supabase';

export class ApiError extends Error {
  status: number;
  rejectedCreate: boolean;
  rejectedContract = false;
  rejectedDocument = false;
  rejectedReview = false;
  rejectedTerms = false;
  rejectedLink = false;
  rejectedSignature = false;
  rejectedExecution = false;
  rejectedTitle = false;
  rejectedPlan = false;
  rejectedBuyer = false;
  rejectedDisposition = false;
  rejectedRenewal = false;
  rejectedDeadline = false;
  rejectedTransition = false;
  rejectedCost: boolean;
  retryAfterSeconds?: number;
  constructor(message: string, status: number, rejectedCreate = false, rejectedCost = false, retryAfterSeconds?: number) {
    super(message); this.status = status; this.rejectedCreate = rejectedCreate; this.rejectedCost = rejectedCost; this.retryAfterSeconds = retryAfterSeconds;
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
    const error = new ApiError(typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`, response.status,
      response.headers.get('X-Deal-Create-Rejected') === 'true',
      init?.method === 'POST' && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/cost-evidence$/.test(path)
        && [401, 403, 409].includes(response.status) && response.headers.get('X-Acquisition-Cost-Rejected') === 'true',
      response.status === 429 && /^[0-9]{1,3}$/.test(response.headers.get('Retry-After') ?? '')
        && Number(response.headers.get('Retry-After')) >= 1 && Number(response.headers.get('Retry-After')) <= 120
        ? Number(response.headers.get('Retry-After')) : undefined);
    error.rejectedBuyer = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/buyers$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Buyer-Rejected') === 'true';
    error.rejectedContract = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/drafts$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Contract-Rejected') === 'true';
    error.rejectedDocument = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/documents$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Document-Rejected') === 'true';
    error.rejectedReview = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/reviews\/(contract_review|title_review|assignment_basis)$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Review-Rejected') === 'true';
    error.rejectedTerms = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/terms$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Terms-Rejected') === 'true';
    error.rejectedLink = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/document-links(?:\/[a-f0-9-]{36}\/withdrawals)?$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Link-Rejected') === 'true';
    error.rejectedSignature = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/signature-review$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Signature-Rejected') === 'true';
    error.rejectedExecution = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/execution-review$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Execution-Review-Rejected') === 'true';
    error.rejectedTitle = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/title-review$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Title-Review-Rejected') === 'true';
    error.rejectedPlan = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/disposition-plan$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Disposition-Plan-Rejected') === 'true';
    error.rejectedRenewal = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/review-renewals$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Renewal-Rejected') === 'true';
    error.rejectedDisposition = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/disposition-review$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Disposition-Review-Rejected') === 'true';
    error.rejectedDeadline = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/versions\/[1-9][0-9]*\/deadline-reviews$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Deadline-Review-Rejected') === 'true';
    error.rejectedTransition = init?.method === 'POST'
      && /^\/api\/acquisition\/workspaces\/[a-f0-9-]{36}\/contracts\/[a-f0-9-]{36}\/transitions$/.test(path)
      && [401, 403, 409].includes(response.status)
      && response.headers.get('X-Acquisition-Transition-Rejected') === 'true';
    throw error;
  }
  return response;
}
