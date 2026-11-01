import { beforeEach, expect, it } from 'vitest';
import { buyerDetailsSchema, buyerDollars, buyerKey, clearConfirmedBuyer, clearRejectedBuyer, parseBuyerPage, parseBuyerProfile, preserveBuyer, readPendingBuyer, type BuyerDetails } from './buyers';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const details = (): BuyerDetails => ({ first_name: 'Sample', last_name: 'Buyer', company: null, email: null, phone: null,
  target_zips: ['75201'], property_types: ['SFR'], strategies: ['fix_flip'], min_price_cents: null,
  max_price_cents: null, max_repairs_cents: null, close_speed_days: null, active: true, source_note: 'Self-reported preferences awaiting independent review.' });
const saved = () => ({ version: 1 as const, context: { userId: id(1), workspaceId: id(2) }, request: { id: id(3), buyer_id: id(4), expected_revision: 0, details: details() } });
const receipt = () => ({ request_id: id(3), workspace_id: id(2), buyer_id: id(4), revision: 1, details: details(), duplicate: true, profile_recorded: true, buyer_verified: false, contact_authorized: false, execution_authorized: false });
const projection = () => ({ workspace_id: id(2), checked_at: new Date().toISOString(), can_save: true, contact_authorized: false, execution_authorized: false });
const summary = (n = 4) => ({ buyer_id: id(n), revision: 1, first_name: 'Sample', last_name: 'Buyer', company: null, active: true, buyer_verified: false });
beforeEach(() => sessionStorage.clear());
it('preserves unknown budgets and exact cents without rounding', () => {
  expect(buyerDollars('')).toBeNull(); expect(buyerDollars('0')).toBe(0); expect(buyerDollars('0.29')).toBe(29);
  expect(buyerDollars('9999999999.99')).toBe(999999999999);
  for (const value of ['10000000000', '-1', '1.001', '1e3', '01', ' 2 ', 'NaN']) expect(() => buyerDollars(value)).toThrow();
});
it('rejects invented verification authority and invalid preferences', () => {
  for (const patch of [{ buyer_verified: true }, { email: 'Buyer@Example.test' }, { phone: '2145550123' },
    { target_zips: ['75201', '75201'] }, { min_price_cents: 2, max_price_cents: 1 }, { source_note: 'Short' }, { first_name: ' Sample' }]) {
    expect(() => buyerDetailsSchema.parse({ ...details(), ...patch })).toThrow();
  }
});
it('recovers identical requests after reload without overwrite or cross-workspace recovery', () => {
  const original = preserveBuyer(sessionStorage, saved());
  expect(readPendingBuyer(sessionStorage, id(1), id(2))).toEqual(original);
  expect(preserveBuyer(sessionStorage, original)).toEqual(original);
  expect(() => preserveBuyer(sessionStorage, { ...saved(), request: { ...saved().request, id: id(9) } })).toThrow();
  sessionStorage.setItem(buyerKey(id(1), id(2)), JSON.stringify({ ...saved(), context: { userId: id(1), workspaceId: id(9) } }));
  expect(() => readPendingBuyer(sessionStorage, id(1), id(2))).toThrow();
});
it('retains uncertain saves until the exact historical receipt is confirmed', () => {
  const original = preserveBuyer(sessionStorage, saved());
  for (const patch of [{ revision: 2 }, { buyer_id: id(9) }, { workspace_id: id(9) }, { request_id: id(9) },
    { details: { ...details(), max_price_cents: 0 } }, { buyer_verified: true }, { contact_authorized: true }, { execution_authorized: true }]) {
    expect(() => clearConfirmedBuyer(sessionStorage, original, { ...receipt(), ...patch })).toThrow();
    expect(readPendingBuyer(sessionStorage, id(1), id(2))).toEqual(original);
  }
  expect(() => clearRejectedBuyer(sessionStorage, original, true, false)).toThrow();
  expect(() => clearRejectedBuyer(sessionStorage, original, false, true)).toThrow();
  clearConfirmedBuyer(sessionStorage, original, receipt()); expect(sessionStorage.length).toBe(0);
});
it('allows only current first-attempt definitive rejection to clear recovery', () => {
  const original = preserveBuyer(sessionStorage, saved());
  clearRejectedBuyer(sessionStorage, original, true, true); expect(sessionStorage.length).toBe(0);
  preserveBuyer(sessionStorage, { ...saved(), request: { ...saved().request, id: id(9) } });
  expect(() => clearConfirmedBuyer(sessionStorage, original, receipt())).toThrow();
});
it('rejects unsafe storage and corrupt saved requests', () => {
  const broken = { getItem: () => null, setItem: () => undefined } as unknown as Storage;
  expect(() => preserveBuyer(broken, saved())).toThrow();
  sessionStorage.setItem(buyerKey(id(1), id(2)), '{broken');
  expect(() => readPendingBuyer(sessionStorage, id(1), id(2))).toThrow();
});
it('requires fresh ordered pages without private contacts or foreign workspace data', () => {
  const page = { ...projection(), items: [summary()], next_cursor: null };
  expect(parseBuyerPage(page, id(2)).items).toHaveLength(1);
  for (const patch of [{ workspace_id: id(9) }, { checked_at: '2000-01-01T00:00:00Z' }, { items: [summary(), summary()] },
    { items: [summary(5), summary(4)] }, { next_cursor: id(4) }, { items: [{ ...summary(), email: 'private@example.test' }] }]) {
    expect(() => parseBuyerPage({ ...page, ...patch }, id(2))).toThrow();
  }
  expect(() => parseBuyerPage(page, id(2), id(4))).toThrow();
  expect(parseBuyerPage({ ...page, next_cursor: id(4) }, id(2), null, 1).next_cursor).toBe(id(4));
});
it('retains paused profiles read-only while rejecting stale or mismatched identities', () => {
  const profile = { ...projection(), buyer_id: id(4), revision: 3, details: details(), buyer_verified: false, can_save: false };
  expect(parseBuyerProfile(profile, id(2), id(4)).can_save).toBe(false);
  expect(() => parseBuyerProfile(profile, id(2), id(9))).toThrow();
  expect(() => parseBuyerProfile(profile, id(2), id(4), Date.now() + 31000)).toThrow();
  expect(() => parseBuyerProfile(profile, id(2), id(4), NaN)).toThrow();
});
