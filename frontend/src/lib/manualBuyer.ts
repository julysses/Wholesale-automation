import { z } from 'zod';
import { ApiError, apiFetch } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import type { BuyerWrite } from '@/hooks/useBuyers';

const money = z.number().finite().min(0).max(1_000_000_000).nullable().default(null);
const fields = z.object({
  first_name: z.string().trim().min(1).max(300), last_name: z.string().trim().min(1).max(300),
  company: z.string().max(500).default(''), email: z.string().max(320).default(''),
  phone: z.string().max(80).default(''), source: z.string().max(80).default(''),
  tier: z.enum(['A', 'B', 'C']).default('C'), target_zips: z.array(z.string().max(20)).max(100).default([]),
  min_price: money, max_price: money, pof_amount: money,
  close_speed_days: z.number().int().min(0).max(10000).nullable().default(null),
  strategy: z.array(z.enum(['fix_flip', 'buy_hold', 'brrrr', 'str'])).max(4).default([]),
  property_types: z.array(z.enum(['SFR', 'duplex', 'MFR', 'land', 'condo'])).max(5).default([]),
  pof_verified: z.boolean().default(false), active: z.boolean().default(true),
  buys_land: z.boolean().default(false), buys_infill: z.boolean().default(false),
  land_buyer_type: z.enum(['builder', 'land_banker', 'trailer_park', 'mineral_rights']).nullable().default(null),
  notes: z.string().max(10000).default(''),
}).strict().refine(v => v.min_price === null || v.max_price === null || v.min_price <= v.max_price,
  'Minimum price cannot exceed maximum price');
const draftSchema = z.object({ actor: z.string().min(1), request_id: z.string().uuid(), buyer: fields }).strict();
export type PendingBuyer = z.infer<typeof draftSchema>;
const receiptSchema = z.object({
  id: z.string().uuid(), state: z.enum(['pending', 'saved', 'canceled']), saved: z.boolean(),
  buyer_id: z.string().uuid().nullable().optional(), buyer: z.record(z.string(), z.unknown()).nullable().optional(),
  current_exists: z.boolean().optional(),
});
export type ManualBuyerReceipt = z.infer<typeof receiptSchema>;

async function actor() {
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session?.user?.id) throw new Error('Sign in again to recover buyer saves.');
  return data.session.user.id;
}
const key = (id: string) => `hilltop.pending-manual-buyer.v1.${id}`;
export async function pendingManualBuyer(): Promise<PendingBuyer | null> {
  const id = await actor();
  const raw = sessionStorage.getItem(key(id));
  if (!raw) return null;
  const draft = draftSchema.parse(JSON.parse(raw));
  if (draft.actor !== id) throw new Error('This saved request belongs to another operator.');
  return draft;
}
function confirm(value: unknown, id: string) {
  const receipt = receiptSchema.parse(value);
  if (receipt.id !== id || receipt.saved !== (receipt.state === 'saved')) throw new Error('Buyer receipt is unconfirmed. Keep the same request.');
  if (receipt.saved && (receipt.buyer_id !== id || receipt.buyer?.id !== id
    || receipt.buyer.sms_opt_in !== false || receipt.buyer.email_opt_in !== false
    || typeof receipt.current_exists !== 'boolean')) throw new Error('Buyer receipt is unconfirmed. Keep the same request.');
  return receipt;
}
async function finish(draft: PendingBuyer, receipt: ManualBuyerReceipt, onPending: (v: PendingBuyer | null) => void) {
  if (await actor() !== draft.actor) throw new Error('Sign in as the original operator to recover this save.');
  if (receipt.state !== 'pending') { sessionStorage.removeItem(key(draft.actor)); onPending(null); }
  return receipt;
}
export async function createManualBuyer(buyer: BuyerWrite, onPending: (v: PendingBuyer | null) => void) {
  let draft = await pendingManualBuyer();
  const wasPending = !!draft;
  const value = fields.parse(buyer);
  if (draft && JSON.stringify(draft.buyer) !== JSON.stringify(value)) throw new Error('Recover or stop the original save before changing buyer details.');
  if (!draft) {
    draft = { actor: await actor(), request_id: crypto.randomUUID(), buyer: value };
    // Persist before POST. Unavailable storage must fail before any write.
    sessionStorage.setItem(key(draft.actor), JSON.stringify(draft));
  }
  onPending(draft);
  if (await actor() !== draft.actor) throw new Error('Sign in as the original operator to recover this save.');
  let response: Response;
  try {
    response = await apiFetch('/api/buyers/manual', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: draft.request_id, buyer: draft.buyer }) });
  } catch (error) {
    // A fresh validation failure cannot have written. A later validation response
    // cannot disprove an earlier uncertain save, so never release that reference.
    if (!wasPending && error instanceof ApiError && error.status === 422) {
      sessionStorage.removeItem(key(draft.actor)); onPending(null);
    }
    throw error;
  }
  const receipt = confirm(await response.json(), draft.request_id);
  if (receipt.state === 'pending') throw new Error('Buyer save is still unconfirmed. Recover the original request.');
  return finish(draft, receipt, onPending);
}
export async function recoverManualBuyer(cancel: boolean, onPending: (v: PendingBuyer | null) => void) {
  const draft = await pendingManualBuyer();
  if (!draft) return null;
  const response = await apiFetch(`/api/buyers/manual/${draft.request_id}${cancel ? '/cancel' : ''}`,
    cancel ? { method: 'POST' } : undefined);
  return finish(draft, confirm(await response.json(), draft.request_id), onPending);
}
