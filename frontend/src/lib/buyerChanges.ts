import { z } from 'zod';
import { apiFetch } from '@/lib/api';
import { supabase } from '@/lib/supabase';

const draftSchema = z.object({ actor: z.string().min(1), request_id: z.string().uuid(), buyer_id: z.string().uuid(),
  kind: z.enum(['update','delete']), expected: z.record(z.string(), z.unknown()), updates: z.record(z.string(), z.unknown()).nullable() }).strict();
export type PendingBuyerChange = z.infer<typeof draftSchema>;
const resultSchema = z.object({ id: z.string().uuid(), state: z.enum(['pending','canceled','updated','deleted','stale','missing']),
  buyer_id: z.string().uuid().nullable().optional(), kind: z.enum(['update','delete']).nullable().optional(),
  buyer: z.record(z.string(), z.unknown()).nullable().optional(), current_exists: z.boolean().optional(), transaction_count: z.number().int().nonnegative().optional() });
export type BuyerChangeResult = z.infer<typeof resultSchema>;
export const BUYER_CHANGE_EVENT = 'hilltop-buyer-change';
const key = (actor: string) => `hilltop.pending-buyer-change.v1.${actor}`;
async function actor() {
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session?.user?.id) throw new Error('Sign in as the original operator to recover buyer changes.');
  return data.session.user.id;
}
export async function pendingBuyerChange() {
  const id = await actor(); const raw = sessionStorage.getItem(key(id));
  if (!raw) return null;
  const value = draftSchema.parse(JSON.parse(raw));
  if (value.actor !== id || value.expected.id !== value.buyer_id) throw new Error('Saved buyer change scope requires review.');
  if (await actor() !== id) throw new Error('Sign in as the original operator.');
  return value;
}
async function finish(value: PendingBuyerChange, response: Response) {
  const result = resultSchema.parse(await response.json());
  if (await actor() !== value.actor || result.id !== value.request_id
    || (!['pending','canceled'].includes(result.state) && (result.buyer_id !== value.buyer_id || result.kind !== value.kind
      || result.current_exists === undefined || result.transaction_count === undefined))
    || (['updated','deleted'].includes(result.state) && result.buyer?.id !== value.buyer_id)
    || (result.state === 'updated' && value.kind !== 'update') || (result.state === 'deleted' && value.kind !== 'delete')) {
    throw new Error('Buyer change receipt is unconfirmed. Keep the original reference.');
  }
  if (result.state !== 'pending') {
    sessionStorage.removeItem(key(value.actor)); window.dispatchEvent(new Event(BUYER_CHANGE_EVENT));
  }
  return result;
}
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k,v]) => `${JSON.stringify(k)}:${stable(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
async function saveUnlocked(kind: 'update' | 'delete', expected: Record<string, unknown>, updates: Record<string, unknown> | null) {
  let value = await pendingBuyerChange();
  const proposed = { kind, expected, updates, buyer_id: String(expected.id) };
  if (value && stable({ kind:value.kind, expected:value.expected, updates:value.updates, buyer_id:value.buyer_id }) !== stable(proposed)) {
    throw new Error('Recover or stop the original buyer change before changing its details or selecting another buyer.');
  }
  if (!value) {
    value = draftSchema.parse({ ...proposed, actor:await actor(), request_id:crypto.randomUUID() });
    sessionStorage.setItem(key(value.actor), JSON.stringify(value)); // Must succeed before the write.
    window.dispatchEvent(new Event(BUYER_CHANGE_EVENT));
  }
  if (await actor() !== value.actor) throw new Error('Recover as the original operator.');
  const body = { request_id:value.request_id, buyer_id:value.buyer_id, kind:value.kind, expected:value.expected, updates:value.updates };
  return finish(value, await apiFetch('/api/buyers/mutations', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }, value.actor));
}
async function recoverUnlocked(action: 'check' | 'retry' | 'cancel') {
  const value = await pendingBuyerChange();
  if (!value) return null;
  if (action === 'retry') return saveUnlocked(value.kind, value.expected, value.updates);
  if (await actor() !== value.actor) throw new Error('Recover as the original operator.');
  return finish(value, await apiFetch(`/api/buyers/mutations/${value.request_id}${action === 'cancel' ? '/cancel' : ''}`, action === 'cancel' ? { method:'POST' } : undefined, value.actor));
}

let changing = false;
async function oneChange<T>(work: () => Promise<T>): Promise<T> {
  if (changing) throw new Error('A buyer change is already in progress. Wait for its saved result.');
  changing = true;
  try { return await work(); } finally { changing = false; }
}
export function saveBuyerChange(kind: 'update' | 'delete', expected: Record<string, unknown>, updates: Record<string, unknown> | null) {
  return oneChange(() => saveUnlocked(kind, expected, updates));
}
export function recoverBuyerChange(action: 'check' | 'retry' | 'cancel') {
  return oneChange(() => recoverUnlocked(action));
}

export function buyerChangeMessage(state: BuyerChangeResult['state']) {
  return { updated: 'Buyer edit confirmed. Refresh for current details.', deleted: 'Buyer deletion confirmed.',
    stale: 'The buyer record changed. No change was applied; refresh before trying again.',
    missing: 'The buyer no longer exists. No change was applied.', canceled: 'The pending buyer change was stopped.',
    pending: 'No saved result is confirmed yet. Keep the original request.' }[state];
}
