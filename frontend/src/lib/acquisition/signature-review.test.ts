import { afterEach, expect, it } from 'vitest';
import { clearConfirmedSignature, clearRejectedSignature, preserveSignature, readPendingSignature, signatureKey, type PendingSignature } from './signature-review';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const saved: PendingSignature = { version: 1, context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 1 }, request: { id: id(7), expected_sequence: 0, status: 'approved', basis_review_id: id(8), policy_id: id(10), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true, note: 'Exact original human review decision for synthetic property.' } };
const receipt = { workspace_id: id(2), contract_id: id(6), contract_version: 1, review_id: id(7), sequence: 1, status: 'approved', duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false };
afterEach(() => sessionStorage.clear());
it('preserves expired exact recovery and only clears its own confirmation', () => {
  preserveSignature(sessionStorage, saved); expect(readPendingSignature(sessionStorage, id(1), id(2))).toEqual(saved);
  expect(readPendingSignature(sessionStorage, id(11), id(2))).toBeNull();
  expect(() => preserveSignature(sessionStorage, { ...saved, request: { ...saved.request, note: 'Changed original human decision must never replace saved bytes.' } })).toThrow();
  for (const patch of [{ review_id: id(11) }, { contract_version: 2 }, { approval_current: true }, { execution_authorized: true }, { sequence: 2 }])
    expect(() => clearConfirmedSignature(sessionStorage, saved, { ...receipt, ...patch })).toThrow();
  expect(() => clearRejectedSignature(sessionStorage, saved, true, false)).toThrow();
  clearConfirmedSignature(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('preserves malformed recovery and rejects unavailable storage before sending', () => {
  sessionStorage.setItem(signatureKey(id(1), id(2)), '{broken');
  expect(() => preserveSignature(sessionStorage, saved)).toThrow();
  expect(sessionStorage.getItem(signatureKey(id(1), id(2)))).toBe('{broken');
  sessionStorage.clear();
  const broken = { getItem: () => null, setItem: () => { throw new Error('Storage unavailable'); } } as unknown as Storage;
  expect(() => preserveSignature(broken, saved)).toThrow();
});

import { parseSignatureCandidate } from './signature-review';
import { signatureChoice, sigContext } from '../../../tests/fixtures/signature-review';
it('keeps a new approval basis separate from the original withdrawal', () => {
  const value = parseSignatureCandidate(signatureChoice(true), sigContext);
  expect(value.candidate!.basis_review_id).not.toBe(value.withdrawal!.basis_review_id);
});
it.each(['scope', 'time', 'source', 'cursor', 'withdrawal', 'authority', 'deadline', 'hold'])('rejects unsafe candidate %s', fault => {
  const value = signatureChoice(true);
  if (fault === 'scope') value.current_review.contract_id = id(20);
  if (fault === 'time') value.checked_at = value.current_review.checked_at = '2020-01-01T00:00:00Z';
  if (fault === 'source') value.candidate!.source_version = 3;
  if (fault === 'cursor') value.candidate!.expected_sequence = 0;
  if (fault === 'withdrawal') value.withdrawal!.basis_review_id = id(20);
  if (fault === 'authority') value.execution_authorized = true;
  if (fault === 'deadline') value.candidate!.max_expires_at = '2020-01-01T00:00:00Z';
  if (fault === 'hold') value.status = 'paused';
  expect(() => parseSignatureCandidate(value, sigContext)).toThrow();
});
