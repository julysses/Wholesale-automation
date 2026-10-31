import { describe, expect, it } from 'vitest';
import { clearSellerInquiry, matchesSellerReceipt, preserveSellerInquiry, readSellerInquiry, sellerInquirySchema, sellerDisplaySchema, type PendingSellerInquiry } from './sellerOfferRequest';

const pending: PendingSellerInquiry = {
  version: 1, formKey: 'synthetic', savedAt: '2026-10-31T21:00:00Z',
  definition: { form_key: 'synthetic', version: 'v1', privacy_acknowledged: 'Review this wording', human_callback_requested: 'Optional callback', email_reply_requested: 'Optional email' },
  inquiry: { submission_id: 'fd000000-0000-4000-8000-000000000001', form_version: 'v1',
    seller: { name: 'Synthetic seller', email: 'seller@example.test' },
    property: { address: '123 Synthetic St', city: 'Dallas', state: 'TX', postal_code: '75201', authority: 'owner',
      condition: 'unsure', occupancy: 'vacant', timeline: 'flexible', motivation: 'Synthetic request', asking_price: null },
    selections: { privacy_acknowledged: true, email_reply_requested: false } },
};
const receipt = { submission_id: pending.inquiry.submission_id, status: 'received', duplicate: true };
function storage(): Storage {
  const rows = new Map<string, string>();
  return { getItem: key => rows.get(key) ?? null, setItem: (key, value) => { rows.set(key, value); },
    removeItem: key => { rows.delete(key); }, clear: () => rows.clear(), key: index => [...rows.keys()][index] ?? null,
    get length() { return rows.size; } };
}

describe('seller inquiry exact recovery', () => {
  it('preserves wording, original identity, null price and explicit false across a reload', () => {
    const saved = storage();
    preserveSellerInquiry(saved, pending);
    expect(readSellerInquiry(saved, 'synthetic')).toEqual(pending);
    expect(() => preserveSellerInquiry(saved, { ...pending, inquiry: { ...pending.inquiry, submission_id: 'fd000000-0000-4000-8000-000000000002' } })).toThrow();
    expect(readSellerInquiry(saved, 'synthetic')).toEqual(pending);
  });
  it('cannot clear an uncertain or mismatched receipt', () => {
    const saved = storage(); preserveSellerInquiry(saved, pending);
    for (const response of [null, {}, { ...receipt, status: 'pending' }, { ...receipt, duplicate: 'true' },
      { ...receipt, submission_id: 'fd000000-0000-4000-8000-000000000002' }, { ...receipt, lead_id: 'private' }]) {
      expect(matchesSellerReceipt(response, pending)).toBe(false);
      expect(() => clearSellerInquiry(saved, pending, response)).toThrow();
      expect(readSellerInquiry(saved, 'synthetic')).toEqual(pending);
    }
    clearSellerInquiry(saved, pending, receipt);
    expect(readSellerInquiry(saved, 'synthetic')).toBeNull();
  });
  it('does not clear a replaced inquiry after a response arrives', () => {
    const saved = storage(); preserveSellerInquiry(saved, pending);
    saved.setItem('hilltop.offer.pending:synthetic', JSON.stringify({ ...pending, savedAt: '2026-11-01T21:00:00Z' }));
    expect(() => clearSellerInquiry(saved, pending, receipt)).toThrow();
    expect(saved.length).toBe(1);
  });
  it('fails closed on disabled or silently failing browser storage', () => {
    const saved = storage(); saved.setItem = () => {};
    expect(() => preserveSellerInquiry(saved, pending)).toThrow();
    saved.getItem = () => { throw new Error('Storage unavailable'); };
    expect(() => readSellerInquiry(saved, 'synthetic')).toThrow();
  });
  it('keeps corrupted recovery and rejects extra token or routing fields', () => {
    const saved = storage();
    for (const value of ['bad JSON', JSON.stringify({ ...pending, bot_token: 'secret' }),
      JSON.stringify({ ...pending, formKey: 'different' }), JSON.stringify({ ...pending, savedAt: 'yesterday' })]) {
      saved.setItem('hilltop.offer.pending:synthetic', value);
      expect(() => readSellerInquiry(saved, 'synthetic')).toThrow();
      expect(saved.getItem('hilltop.offer.pending:synthetic')).toBe(value);
    }
  });
  it('requires a contact and affirmative acknowledgement without inferring permission', () => {
    expect(sellerInquirySchema.safeParse({ ...pending.inquiry, seller: { name: 'Seller' } }).success).toBe(false);
    expect(sellerInquirySchema.safeParse({ ...pending.inquiry, selections: { privacy_acknowledged: false } }).success).toBe(false);
    expect(sellerInquirySchema.safeParse({ ...pending.inquiry, selections: { privacy_acknowledged: true, human_callback_requested: true } }).success).toBe(false);
    expect(sellerInquirySchema.safeParse({ ...pending.inquiry, workspace_id: 'other' }).success).toBe(false);
  });
  it('rejects private display fields and malformed asking prices', () => {
    expect(sellerDisplaySchema.safeParse({ definition: pending.definition, bot_site_key: 'public-key', mao: 123 }).success).toBe(false);
    for (const asking_price of [-1, 0, 'NaN', '1000000001', '12,000', '01', '1.001']) {
      expect(sellerInquirySchema.safeParse({ ...pending.inquiry, property: { ...pending.inquiry.property, asking_price } }).success).toBe(false);
    }
  });
});
