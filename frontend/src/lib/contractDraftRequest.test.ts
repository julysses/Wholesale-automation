import { describe, expect, it } from 'vitest';
import { clearConfirmedContractDraft, clearRejectedContractDraft, readExistingContractDrafts, preserveContractDraft, readContractDraft, readContractSellers, type PendingContractDraft } from './contractDraftRequest';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const pending: PendingContractDraft = { version: 1, context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4) },
  savedAt: '2026-10-31T22:00:00Z', request: { id: id(5), offer_id: id(6), offer_sequence: 2, owner_relationship_id: id(7), name: 'Property draft' } };
const receipt = { deal_id: id(5), version: 1, status: 'draft', duplicate: true, execution_authorized: false };
function storage(): Storage { const rows = new Map<string, string>(); return { getItem: key => rows.get(key) ?? null,
  setItem: (key, value) => { rows.set(key, value); }, removeItem: key => { rows.delete(key); }, clear: () => rows.clear(),
  key: n => [...rows.keys()][n] ?? null, get length() { return rows.size; } }; }
const read = (saved: Storage) => readContractDraft(saved, id(1), id(2));

describe('contract draft recovery', () => {
  it('retains exact request across reload and refuses a replacement offer', () => {
    const saved = storage(); preserveContractDraft(saved, pending); expect(read(saved)).toEqual(pending);
    expect(() => preserveContractDraft(saved, { ...pending, request: { ...pending.request, offer_id: id(9) } })).toThrow();
    expect(read(saved)).toEqual(pending);
  });
  it('never clears mismatched, unconfirmed or execution-granting replies', () => {
    const saved = storage(); preserveContractDraft(saved, pending);
    for (const response of [null, {}, { ...receipt, deal_id: id(9) }, { ...receipt, duplicate: 'true' },
      { ...receipt, execution_authorized: true }, { ...receipt, status: 'executed' }, { ...receipt, private: 'hidden' }]) {
      expect(() => clearConfirmedContractDraft(saved, pending, response)).toThrow(); expect(read(saved)).toEqual(pending);
    }
    clearConfirmedContractDraft(saved, pending, receipt); expect(read(saved)).toBeNull();
  });
  it('separates workspace and user recovery and rejects a tampered scope', () => {
    const saved = storage(); preserveContractDraft(saved, pending);
    expect(readContractDraft(saved, id(9), id(2))).toBeNull(); expect(readContractDraft(saved, id(1), id(9))).toBeNull();
    saved.setItem(saved.key(0)!, JSON.stringify({ ...pending, context: { ...pending.context, userId: id(9) } }));
    expect(() => read(saved)).toThrow(); expect(saved.length).toBe(1);
  });
  it('preserves corrupted state and rejects unavailable or silently failed storage', () => {
    const saved = storage(); preserveContractDraft(saved, pending); saved.setItem(saved.key(0)!, 'bad JSON');
    expect(() => read(saved)).toThrow(); expect(saved.length).toBe(1);
    const unavailable = storage(); unavailable.setItem = () => {}; expect(() => preserveContractDraft(unavailable, pending)).toThrow();
    unavailable.getItem = () => { throw new Error('blocked'); }; expect(() => read(unavailable)).toThrow();
  });
  it('refuses to clear a changed request after a matching response', () => {
    const saved = storage(); preserveContractDraft(saved, pending);
    saved.setItem(saved.key(0)!, JSON.stringify({ ...pending, request: { ...pending.request, name: 'Changed' } }));
    expect(() => clearConfirmedContractDraft(saved, pending, receipt)).toThrow(); expect(saved.length).toBe(1);
  });
  it('checks property seller choices and refuses verified-title claims', () => {
    const row = { id: id(7), workspace_id: id(2), lead_id: id(3), property_id: id(4), owner_id: id(8),
      relationship: 'reported_owner', verification_status: 'unverified', seller: { display_name: 'Synthetic Seller' } };
    const page = { items: [row], next_after: id(7), ownership_verified: false, execution_authorized: false };
    expect(readContractSellers(page, pending.context).items[0].seller.display_name).toBe('Synthetic Seller');
    for (const value of [{ ...page, ownership_verified: true }, { ...page, next_after: id(9) },
      { ...page, items: [{ ...row, property_id: id(9) }] }, { ...page, items: [row, row] },
      { ...page, items: [{ ...row, seller: null }] }]) expect(() => readContractSellers(value, pending.context)).toThrow();
  });
});

it('never discards an uncertain draft on a subsequent rejection', () => {
  const saved = storage(); preserveContractDraft(saved, pending);
  expect(() => clearRejectedContractDraft(saved, pending, false, true)).toThrow();
  expect(() => clearRejectedContractDraft(saved, pending, true, false)).toThrow();
  expect(read(saved)).toEqual(pending);
  clearRejectedContractDraft(saved, pending, true, true); expect(read(saved)).toBeNull();
});
it('fails closed on malformed or foreign draft history', () => {
  const row = { id: id(5), workspace_id: id(2), lead_id: id(3), deal_name: 'Existing draft', acquisition_status: 'draft', acquisition_version: 1,
    acquisition_property_id: id(4), acquisition_owner_relationship_id: id(7), acquisition_offer_id: id(6), acquisition_offer_sequence: 2,
    created_by: id(1), created_at: '2026-10-31T22:00:00Z' };
  const page = { items: [row], next_after: null, execution_authorized: false };
  expect(readExistingContractDrafts(page, pending.context).items).toHaveLength(1);
  for (const value of [{ ...page, items: [{ ...row, workspace_id: id(9) }] }, { ...page, items: [row, row] },
    { ...page, next_after: id(9) }, { ...page, execution_authorized: true }]) expect(() => readExistingContractDrafts(value, pending.context)).toThrow();
});
