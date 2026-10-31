import { z } from 'zod';

const version = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/);
const shortText = z.string().min(1).max(200).refine(value => value.trim().length > 0);
const identity = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const phone = z.string().min(7).max(40).refine(value => {
  if (!/^\+?[0-9 ().-]+$/.test(value)) return false;
  const digits = value.replace(/\D/g, '');
  const normalized = value.startsWith('+') ? '+' + digits
    : digits.length === 10 ? '+1' + digits : digits.length === 11 && digits.startsWith('1') ? '+' + digits : '';
  return /^\+[1-9][0-9]{7,14}$/.test(normalized);
});

export const sellerDefinitionSchema = z.object({
  form_key: version, version,
  privacy_acknowledged: z.string().min(1).max(4000),
  human_callback_requested: z.string().min(1).max(4000),
  email_reply_requested: z.string().min(1).max(4000),
}).strict();
export const sellerDisplaySchema = z.object({
  definition: sellerDefinitionSchema,
  bot_site_key: z.string().regex(/^[A-Za-z0-9_-]{1,200}$/),
}).strict();

export const sellerInquirySchema = z.object({
  submission_id: identity,
  form_version: version,
  seller: z.object({
    name: shortText,
    phone: phone.nullable().optional(),
    email: z.string().min(3).max(254).regex(/^[^\s@]+@[^\s@]+\.[^\s@]+$/).nullable().optional(),
  }).strict().refine(value => !!(value.phone || value.email), 'Provide a phone number or email address.'),
  property: z.object({
    address: shortText, city: shortText, state: z.string().regex(/^[A-Z]{2}$/),
    postal_code: z.string().regex(/^\d{5}(?:-\d{4})?$/),
    authority: z.enum(['owner', 'authorized_representative', 'not_authorized', 'unsure']),
    condition: z.enum(['move_in_ready', 'cosmetic_repairs', 'major_repairs', 'unsure']),
    occupancy: z.enum(['owner_occupied', 'tenant_occupied', 'vacant', 'other', 'unsure']),
    timeline: z.enum(['within_30_days', 'one_to_three_months', 'three_to_six_months', 'flexible', 'unsure']),
    motivation: z.string().min(1).max(2000).refine(value => value.trim().length > 0),
    asking_price: z.string().regex(/^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$/)
      .refine(value => Number(value) <= 1000000000).nullable().optional(),
  }).strict(),
  selections: z.object({
    privacy_acknowledged: z.literal(true),
    human_callback_requested: z.boolean().optional(),
    email_reply_requested: z.boolean().optional(),
  }).strict(),
}).strict().superRefine((value, context) => {
  if (value.selections.human_callback_requested && !value.seller.phone) {
    context.addIssue({ code: 'custom', path: ['seller', 'phone'], message: 'Add a phone number to request a callback.' });
  }
  if (value.selections.email_reply_requested && !value.seller.email) {
    context.addIssue({ code: 'custom', path: ['seller', 'email'], message: 'Add an email address to request an email reply.' });
  }
});

const pendingSchema = z.object({
  version: z.literal(1),
  formKey: version,
  savedAt: z.string().datetime({ offset: true }),
  definition: sellerDefinitionSchema,
  inquiry: sellerInquirySchema,
}).strict().refine(value => value.formKey === value.definition.form_key
  && value.definition.version === value.inquiry.form_version, 'Saved form identity changed.');
const receiptSchema = z.object({ submission_id: identity, status: z.literal('received'), duplicate: z.boolean() }).strict();

export type SellerInquiry = z.infer<typeof sellerInquirySchema>;
export type SellerDefinition = z.infer<typeof sellerDefinitionSchema>;
export type SellerDisplay = z.infer<typeof sellerDisplaySchema>;
export type PendingSellerInquiry = z.infer<typeof pendingSchema>;
export const UNCONFIRMED_SELLER_REQUEST = 'We could not confirm your request. Your saved details are unchanged. Retry this request to avoid creating another inquiry.';
const storageKey = (formKey: string) => 'hilltop.offer.pending:' + version.parse(formKey);

export function readSellerInquiry(storage: Pick<Storage, 'getItem'>, formKey: string): PendingSellerInquiry | null {
  const raw = storage.getItem(storageKey(formKey));
  if (raw === null) return null;
  if (raw.length > 65536) throw new Error('Saved request is invalid.');
  const result = pendingSchema.parse(JSON.parse(raw));
  if (result.formKey !== formKey) throw new Error('Saved request belongs to another form.');
  return result;
}

export function preserveSellerInquiry(storage: Storage, value: PendingSellerInquiry): PendingSellerInquiry {
  const pending = pendingSchema.parse(value);
  const key = storageKey(pending.formKey);
  if (storage.getItem(key) !== null) throw new Error('A request is already awaiting confirmation.');
  const serialized = JSON.stringify(pending);
  if (serialized.length > 65536) throw new Error('Saved request is too large.');
  storage.setItem(key, serialized);
  if (storage.getItem(key) !== serialized) throw new Error('Your request could not be saved for recovery.');
  return pending;
}

export function matchesSellerReceipt(receipt: unknown, pending: PendingSellerInquiry): boolean {
  const parsed = receiptSchema.safeParse(receipt);
  return parsed.success && parsed.data.submission_id === pending.inquiry.submission_id;
}

export function clearSellerInquiry(storage: Storage, pending: PendingSellerInquiry, receipt: unknown): void {
  if (!matchesSellerReceipt(receipt, pending)) throw new Error(UNCONFIRMED_SELLER_REQUEST);
  const current = readSellerInquiry(storage, pending.formKey);
  if (JSON.stringify(current) !== JSON.stringify(pendingSchema.parse(pending))) {
    throw new Error('Saved request changed.');
  }
  storage.removeItem(storageKey(pending.formKey));
  if (storage.getItem(storageKey(pending.formKey)) !== null) throw new Error('Confirmed request could not be cleared.');
}
