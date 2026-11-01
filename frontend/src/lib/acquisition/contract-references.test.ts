import { expect, it } from 'vitest';
import { parseReferences } from './contract-references';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
const now = Date.now(), checked = new Date(now).toISOString();
const row = { workspace_id: id(2), contract_id: id(6), contract_version: 2, artifact_id: id(7), purpose: 'purchase_contract', source_version: 1,
  reference_type: 'term_source', link_id: null, sha256: 'a'.repeat(64), verification_id: id(8), source_created_at: new Date(now - 1000).toISOString(), checked_at: checked,
  status: 'available_for_review', review_approved: false, execution_authorized: false };
const page = { workspace_id: id(2), contract_id: id(6), contract_version: 2, purpose: 'purchase_contract', items: [row], next_after: null, checked_at: checked, execution_authorized: false };
const parse = (value: unknown) => parseReferences(value, context, 'purchase_contract', null, now);
it('preserves original source without implying approval', () => { expect(parse(page).items[0].source_version).toBe(1); expect(parse(page).execution_authorized).toBe(false); });
it.each([{ workspace_id: id(9) }, { contract_version: 3 }, { source_version: 3 }, { reference_type: 'native' }, { link_id: id(9) },
  { verification_id: null }, { review_approved: true }, { status: 'reference_withdrawn' }, { checked_at: new Date(now - 40000).toISOString() }, { source_created_at: new Date(now + 1000).toISOString() }])('rejects inconsistent source %j', change => { expect(() => parse({ ...page, items: [{ ...row, ...change }] })).toThrow(); });
it('retains withdrawn links without verification authority', () => {
  expect(parse({ ...page, items: [{ ...row, reference_type: 'linked', link_id: id(9), status: 'reference_withdrawn', verification_id: null }] }).items[0].status).toBe('reference_withdrawn');
});
it('rejects duplicate, stale and invalid cursor pages', () => {
  for (const value of [{ ...page, items: [row, row] }, { ...page, checked_at: new Date(now - 40000).toISOString() }, { ...page, next_after: id(7) }]) expect(() => parse(value)).toThrow();
  expect(() => parseReferences(page, context, 'purchase_contract', id(7), now)).toThrow();
});
