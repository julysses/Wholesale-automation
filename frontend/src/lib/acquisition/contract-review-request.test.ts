import { afterEach, expect, it } from 'vitest';
import { clearConfirmedReview, clearRejectedReview, preserveReview, readPendingReview, reviewKey, type PendingReview } from './contract-review-request';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const saved: PendingReview = { version: 1, context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 1 }, kind: 'contract_review', request: { id: id(7), expected_sequence: 0, status: 'approved', artifact_id: id(8), verification_id: id(9), policy_id: id(10), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true, note: 'Exact original human review decision for synthetic property.' } };
const receipt = { workspace_id: id(2), contract_id: id(6), contract_version: 1, kind: 'contract_review', review_id: id(7), sequence: 1, status: 'approved', duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false };
afterEach(() => sessionStorage.clear());
it('preserves expired exact recovery and only clears its own confirmation', () => {
  preserveReview(sessionStorage, saved); expect(readPendingReview(sessionStorage, id(1), id(2))).toEqual(saved);
  expect(readPendingReview(sessionStorage, id(11), id(2))).toBeNull();
  expect(() => preserveReview(sessionStorage, { ...saved, request: { ...saved.request, note: 'Changed original human decision must never replace saved bytes.' } })).toThrow();
  for (const patch of [{ review_id: id(11) }, { contract_version: 2 }, { approval_current: true }, { execution_authorized: true }, { sequence: 2 }])
    expect(() => clearConfirmedReview(sessionStorage, saved, { ...receipt, ...patch })).toThrow();
  expect(() => clearRejectedReview(sessionStorage, saved, true, false)).toThrow();
  clearConfirmedReview(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('preserves malformed recovery and rejects unavailable storage before sending', () => {
  sessionStorage.setItem(reviewKey(id(1), id(2)), '{broken');
  expect(() => preserveReview(sessionStorage, saved)).toThrow();
  expect(sessionStorage.getItem(reviewKey(id(1), id(2)))).toBe('{broken');
  sessionStorage.clear();
  const broken = { getItem: () => null, setItem: () => { throw new Error('Storage unavailable'); } } as unknown as Storage;
  expect(() => preserveReview(broken, saved)).toThrow();
});
