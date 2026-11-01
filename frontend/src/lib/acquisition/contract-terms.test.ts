import { beforeEach, expect, it } from 'vitest';
import { clearConfirmedTerms, clearRejectedTerms, preserveTerms, readPendingTerms, termsKey, termsSchema, dateTerm, dollarsToCents, centsToDollars, parseTermsVersion, emptyTerms } from './contract-terms';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), contractId: id(3), contractVersion: 1, leadId: id(4), propertyId: id(5), offerId: id(6) };
const unknown = () => ({ ...emptyTerms(), note: 'No contract terms have been established yet.' });
const saved = () => ({ version: 1 as const, context, request: { id: id(7), expected_version: 1, terms: unknown() } });
const receipt = () => ({ request_id: id(7), workspace_id: id(2), contract_id: id(3), version: 2, status: 'draft', duplicate: true, execution_authorized: false });
beforeEach(() => sessionStorage.clear());
it('preserves unknown amounts and exact cent boundaries without floating point rounding', () => {
  expect(dollarsToCents('')).toBeNull(); expect(dollarsToCents('0')).toBe(0); expect(dollarsToCents('0.29')).toBe(29);
  expect(dollarsToCents('90071992547409.91')).toBe(Number.MAX_SAFE_INTEGER); expect(centsToDollars(Number.MAX_SAFE_INTEGER)).toBe('90071992547409.91');
  for (const input of ['1.001', '-1', '1e3', '01', ' 1 ', '90071992547409.92', 'NaN']) expect(() => dollarsToCents(input)).toThrow();
});
it('requires original citations and assignment provision text while allowing all unknowns', () => {
  expect(termsSchema.parse(unknown()).purchase_price_cents).toBeNull();
  expect(() => termsSchema.parse({ ...unknown(), earnest_money_cents: 0 })).toThrow();
  const source = { term: 'earnest_money', artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64), locator: 'Page 2, clause 5' };
  expect(termsSchema.parse({ ...unknown(), earnest_money_cents: 0, sources: [source] }).earnest_money_cents).toBe(0);
  expect(() => termsSchema.parse({ ...unknown(), sources: [source, source] })).toThrow();
  expect(() => termsSchema.parse({ ...unknown(), assignment_allowed: false, sources: [{ ...source, term: 'assignment' }] })).toThrow();
});
it('retains calendar precision and rejects inferred zones and invalid dates', () => {
  expect(dateTerm.parse({ precision: 'date', calendar_date: '2028-02-29', instant: null }).instant).toBeNull();
  for (const calendar_date of ['2026-02-29', '2026-04-31', '0000-01-01']) expect(() => dateTerm.parse({ precision: 'date', calendar_date, instant: null })).toThrow();
  for (const instant of ['2026-11-20T17:00:00', '2026-02-30T17:00:00Z', '2026-11-20']) expect(() => dateTerm.parse({ precision: 'instant', calendar_date: null, instant })).toThrow();
  expect(dateTerm.parse({ precision: 'instant', calendar_date: null, instant: '2026-11-20T17:00:00-06:00' }).instant).toBe('2026-11-20T17:00:00-06:00');
});
it('keeps the exact request across reloads and rejects competing requests or scopes', () => {
  const original = preserveTerms(sessionStorage, saved());
  expect(readPendingTerms(sessionStorage, id(1), id(2))).toEqual(original);
  expect(() => preserveTerms(sessionStorage, { ...saved(), request: { ...saved().request, id: id(10) } })).toThrow();
  sessionStorage.setItem(termsKey(id(1), id(2)), JSON.stringify({ ...saved(), context: { ...context, workspaceId: id(10) } }));
  expect(() => readPendingTerms(sessionStorage, id(1), id(2))).toThrow();
});
it('only clears an exact non-executing receipt or a first-attempt definitive rejection', () => {
  const original = preserveTerms(sessionStorage, saved());
  for (const patch of [{ version: 3 }, { contract_id: id(10) }, { execution_authorized: true }, { request_id: id(10) }]) {
    expect(() => clearConfirmedTerms(sessionStorage, original, { ...receipt(), ...patch })).toThrow(); expect(sessionStorage.length).toBe(1);
  }
  expect(() => clearRejectedTerms(sessionStorage, original, true, false)).toThrow();
  clearConfirmedTerms(sessionStorage, original, receipt()); expect(sessionStorage.length).toBe(0);
});
it('rejects future sources and mismatched saved context', () => {
  expect(() => preserveTerms(sessionStorage, { ...saved(), context: { ...context, contractVersion: 2 } })).toThrow();
  expect(() => preserveTerms(sessionStorage, { ...saved(), request: { ...saved().request, terms: { ...unknown(), sources: [{ term: 'effective', artifact_id: id(8), artifact_version: 2, sha256: 'a'.repeat(64), locator: 'Page 1' }] } } })).toThrow();
});
it('binds history to the current target and rejects a newer successor', () => {
  const row = { id: id(9), workspace_id: id(2), deal_id: id(3), version: 1, status: 'draft', previous_version: null, terms: null, actor_id: id(1), created_at: '2026-10-31T22:00:00Z' };
  const page = { workspace_id: id(2), contract_id: id(3), items: [row], next_after: null, execution_authorized: false };
  expect(parseTermsVersion(page, context).terms).toBeNull();
  expect(() => parseTermsVersion({ ...page, next_after: 1 }, context)).toThrow();
  expect(() => parseTermsVersion({ ...page, items: [{ ...row, deal_id: id(10) }] }, context)).toThrow();
});
