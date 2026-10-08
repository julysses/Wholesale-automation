import { ApiError, apiFetch } from '@/lib/api';
import type { Deal, } from '@/types';
import type { DealWrite } from '@/hooks/useDeals';
export interface PendingDeal { request_id: string; deal: DealWrite }
const key = 'hilltop.pending-pipeline-deal.v1';
export function pendingDeal(): PendingDeal | null {
  const raw = sessionStorage.getItem(key);
  if (!raw) return null;
  const value = JSON.parse(raw);
  if (!value?.request_id || !value?.deal?.lead_id) throw new Error('Pending deal cannot be recovered. Review Pipeline before creating another deal.');
  return value;
}
const canonical = (value: DealWrite) => JSON.stringify(JSON.parse(JSON.stringify(value)), Object.keys(value).sort());
export async function createPipelineDeal(deal: DealWrite, onPending: (value: PendingDeal | null) => void) {
  let draft = pendingDeal();
  if (draft && canonical(draft.deal) !== canonical(deal)) throw new Error('An unconfirmed deal create is pending. Recover that exact save before creating another deal.');
  if (!draft) {
    draft = { request_id: crypto.randomUUID(), deal };
    sessionStorage.setItem(key, JSON.stringify(draft));
  }
  onPending(draft);
  let response: Response;
  try {
    response = await apiFetch('/api/deals', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(draft) });
  } catch (error) {
    // Only a definite validation/no-write rejection releases this reference. Transport or conflict outcomes remain recoverable.
    if (error instanceof ApiError && (error.status === 422 || error.rejectedCreate)) {
      sessionStorage.removeItem(key); onPending(null);
    }
    throw error;
  }
  const saved = await response.json();
  if (saved.id !== draft.request_id || !saved.updated_at) throw new Error('Deal acknowledgement is unconfirmed. Retry the same reference.');
  sessionStorage.removeItem(key); onPending(null);
  return saved as Deal;
}
export async function updatePipelineDeal(id: string, expected: string, updates: DealWrite) {
  const response = await apiFetch(`/api/deals/${id}`, { method:'PATCH', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({expected_updated_at:expected,updates}) });
  const saved = await response.json();
  if (saved.id !== id || !saved.updated_at) throw new Error('Deal update acknowledgement is unconfirmed. Refresh before continuing.');
  return saved as Deal;
}
