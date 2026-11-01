import { z } from 'zod';
import { id } from './mail-content';

export const buyerPropertyTypes = { SFR: 'Single-family', duplex: 'Duplex', MFR: 'Multifamily', land: 'Land', condo: 'Condo' } as const;
export const buyerStrategies = { fix_flip: 'Fix and flip', buy_hold: 'Buy and hold', brrrr: 'Buy, renovate and refinance', str: 'Short-term rental', development: 'Development', wholesale: 'Wholesale' } as const;
const text = (min: number, max: number) => z.string().min(min).max(max).refine(v => v === v.trim() && ![...v].some(c => c.charCodeAt(0) < 32));
const cents = z.number().int().min(0).max(999999999999).nullable();
const revision = z.number().int().min(1).max(2147483647);
export const buyerDetailsSchema = z.object({
  first_name: text(1, 120), last_name: text(1, 120), company: text(1, 160).nullable(),
  email: text(3, 320).regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/).refine(v => v === v.toLowerCase()).nullable(),
  phone: z.string().regex(/^\+[1-9][0-9]{7,14}$/).nullable(),
  target_zips: z.array(z.string().regex(/^[0-9]{5}$/)).max(100),
  property_types: z.array(z.enum(['SFR', 'duplex', 'MFR', 'land', 'condo'])).max(5),
  strategies: z.array(z.enum(['fix_flip', 'buy_hold', 'brrrr', 'str', 'development', 'wholesale'])).max(6),
  min_price_cents: cents, max_price_cents: cents, max_repairs_cents: cents,
  close_speed_days: z.number().int().min(1).max(365).nullable(), active: z.boolean(), source_note: text(20, 2000),
}).strict().refine(v => [v.target_zips, v.property_types, v.strategies].every(a => new Set(a).size === a.length)
  && (v.min_price_cents === null || v.max_price_cents === null || v.min_price_cents <= v.max_price_cents));
export type BuyerDetails = z.infer<typeof buyerDetailsSchema>;
export const buyerRequestSchema = z.object({ id, buyer_id: id, expected_revision: z.number().int().min(0).max(2147483646), details: buyerDetailsSchema }).strict();
const context = z.object({ userId: id, workspaceId: id }).strict();
export const pendingBuyerSchema = z.object({ version: z.literal(1), context, request: buyerRequestSchema }).strict();
export type PendingBuyer = z.infer<typeof pendingBuyerSchema>;
export const buyerKey = (user: string, workspace: string) => `wholesale.acquisition.buyer:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingBuyer(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(buyerKey(user, workspace));
  if (raw === null) return null;
  if (raw.length > 30000) throw new Error('Buyer recovery exceeds limits');
  const saved = pendingBuyerSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Buyer recovery scope changed');
  return saved;
}
export function preserveBuyer(storage: Storage, value: PendingBuyer) {
  const saved = pendingBuyerSchema.parse(value), c = saved.context, current = readPendingBuyer(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another buyer save needs recovery');
  const raw = JSON.stringify(saved), key = buyerKey(c.userId, c.workspaceId);
  if (raw.length > 30000) throw new Error('Buyer recovery exceeds limits');
  storage.setItem(key, raw);
  if (storage.getItem(key) !== raw) throw new Error('Buyer recovery unavailable');
  return saved;
}
function clear(storage: Storage, value: PendingBuyer) {
  const saved = pendingBuyerSchema.parse(value), c = saved.context, key = buyerKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingBuyer(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Buyer recovery changed');
  storage.removeItem(key);
  if (storage.getItem(key) !== null) throw new Error('Buyer recovery could not be cleared');
}
export function clearConfirmedBuyer(storage: Storage, saved: PendingBuyer, raw: unknown) {
  const receipt = z.object({ request_id: id, workspace_id: id, buyer_id: id, revision, details: buyerDetailsSchema,
    duplicate: z.boolean(), profile_recorded: z.literal(true), buyer_verified: z.literal(false),
    contact_authorized: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const r = saved.request;
  if (receipt.request_id !== r.id || receipt.workspace_id !== saved.context.workspaceId || receipt.buyer_id !== r.buyer_id
    || receipt.revision !== r.expected_revision + 1 || JSON.stringify(receipt.details) !== JSON.stringify(buyerDetailsSchema.parse(r.details))) throw new Error('Buyer receipt mismatch');
  clear(storage, saved);
  return receipt;
}
export function clearRejectedBuyer(storage: Storage, saved: PendingBuyer, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier buyer save remains unconfirmed');
  clear(storage, saved);
}
const projection = { workspace_id: id, checked_at: z.string().datetime({ offset: true }), can_save: z.boolean(),
  contact_authorized: z.literal(false), execution_authorized: z.literal(false) };
const summary = z.object({ buyer_id: id, revision, first_name: text(1, 120), last_name: text(1, 120), company: text(1, 160).nullable(), active: z.boolean(), buyer_verified: z.literal(false) }).strict();
const pageSchema = z.object({ ...projection, items: z.array(summary).max(50), next_cursor: id.nullable() }).strict();
const profileSchema = z.object({ ...projection, buyer_id: id, revision, details: buyerDetailsSchema, buyer_verified: z.literal(false) }).strict();
function fresh(value: { workspace_id: string; checked_at: string }, workspace: string, now: number) {
  const checked = Date.parse(value.checked_at);
  if (value.workspace_id !== workspace || !Number.isFinite(now) || now - checked > 30000 || checked - now > 5000) throw new Error('Refresh current buyer details');
}
export function parseBuyerPage(raw: unknown, workspace: string, after: string | null = null, limit = 25, now = Date.now()) {
  const page = pageSchema.parse(raw); fresh(page, workspace, now);
  const ids = page.items.map(v => v.buyer_id);
  if (!Number.isInteger(limit) || limit < 1 || limit > 50 || ids.length > limit
    || ids.some((v, i) => (i > 0 && v <= ids[i - 1]) || (after !== null && v <= after))
    || page.next_cursor !== null && (ids.length !== limit || page.next_cursor !== ids.at(-1))) throw new Error('Buyer page changed');
  return page;
}
export function parseBuyerProfile(raw: unknown, workspace: string, buyer: string, now = Date.now()) {
  const profile = profileSchema.parse(raw); fresh(profile, workspace, now);
  if (profile.buyer_id !== buyer) throw new Error('Buyer identity changed');
  return profile;
}
export function buyerDollars(value: string): number | null {
  if (value === '') return null;
  if (!/^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$/.test(value)) throw new Error('Enter dollars with at most two decimal places');
  const [whole, fraction = ''] = value.split('.');
  return cents.parse(Number(whole) * 100 + Number(fraction.padEnd(2, '0')));
}

export const emptyBuyer = (): BuyerDetails => ({ first_name: '', last_name: '', company: null, email: null, phone: null,
  target_zips: [], property_types: [], strategies: [], min_price_cents: null, max_price_cents: null,
  max_repairs_cents: null, close_speed_days: null, active: true, source_note: '' });
export type BuyerAmounts = { min_price_cents: string; max_price_cents: string; max_repairs_cents: string; close_speed_days: string };
export function buyerAmounts(details: BuyerDetails): BuyerAmounts {
  const dollars = (v: number | null) => v === null ? '' : `${Math.floor(v / 100)}.${String(v % 100).padStart(2, '0')}`;
  return { min_price_cents: dollars(details.min_price_cents), max_price_cents: dollars(details.max_price_cents),
    max_repairs_cents: dollars(details.max_repairs_cents), close_speed_days: details.close_speed_days?.toString() ?? '' };
}
export function assembleBuyer(details: BuyerDetails, amounts: BuyerAmounts, zips: string) {
  if (amounts.close_speed_days !== '' && !/^[1-9][0-9]{0,2}$/.test(amounts.close_speed_days)) throw new Error('Use whole days');
  return { ...details, first_name: details.first_name.trim(), last_name: details.last_name.trim(),
    company: details.company?.trim() || null, email: details.email?.trim().toLowerCase() || null,
    phone: details.phone?.trim() || null, source_note: details.source_note.trim(),
    target_zips: zips.trim() === '' ? [] : zips.trim().split(/[\s,]+/),
    min_price_cents: buyerDollars(amounts.min_price_cents), max_price_cents: buyerDollars(amounts.max_price_cents),
    max_repairs_cents: buyerDollars(amounts.max_repairs_cents), close_speed_days: amounts.close_speed_days === '' ? null : Number(amounts.close_speed_days) };
}
