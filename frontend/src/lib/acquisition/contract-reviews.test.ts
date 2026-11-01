import { expect, it } from 'vitest';
import { parseContractReview, reviewIsFresh } from './contract-reviews';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 1 };
const now = Date.parse('2026-10-31T12:00:00Z');
const current = { workspace_id: id(2), contract_id: id(6), contract_version: 1, kind: 'contract_review', sequence: 1, review_id: id(7),
  status: 'approved', approval_current: true, expires_at: '2026-10-31T12:01:00Z', checked_at: '2026-10-31T12:00:00Z', execution_authorized: false };
it('expires displayed approval on freshness or approval expiry', () => {
  const value = parseContractReview(current, context, 'contract_review', now);
  expect(value.execution_authorized).toBe(false);
  expect(reviewIsFresh(value, now + 30001)).toBe(false);
  expect(reviewIsFresh({ ...value, expires_at: '2026-10-31T12:00:05Z' }, now + 5000)).toBe(false);
});
it.each([{ workspace_id: id(9) }, { contract_id: id(9) }, { contract_version: 2 }, { kind: 'title_review' },
  { checked_at: '2026-10-31T11:59:29Z' }, { checked_at: '2026-10-31T12:00:06Z' }, { expires_at: '2026-10-31T12:00:00Z' },
  { expires_at: null }, { review_id: null }, { sequence: 0 }, { sequence: true }, { status: 'withdrawn' },
  { approval_current: false }, { execution_authorized: true }, { private_url: 'secret' }])('rejects inconsistent review %j', patch => {
  expect(() => parseContractReview({ ...current, ...patch }, context, 'contract_review', now)).toThrow();
});
it.each(['withdrawn', 'requires_review', 'not_reviewed'])('preserves %s without authority', status => {
  const value = { ...current, status, approval_current: false, expires_at: null, ...(status === 'not_reviewed' ? { sequence: 0, review_id: null } : {}) };
  expect(parseContractReview(value, context, 'contract_review', now).approval_current).toBe(false);
  expect(() => parseContractReview({ ...value, expires_at: current.expires_at }, context, 'contract_review', now)).toThrow();
});

import { parseReviewCandidate } from './contract-reviews';
const choice = () => ({ workspace_id: id(2), contract_id: id(6), contract_version: 1, kind: 'contract_review', artifact_id: id(8),
  purpose: 'purchase_contract', status: 'ready_for_human_review', candidate: { artifact_id: id(8), verification_id: id(9), sha256: 'a'.repeat(64), policy_id: id(10), expected_sequence: 1, max_expires_at: '2026-10-31T12:02:00Z' },
  withdrawal: { review_id: id(7), artifact_id: id(8), verification_id: id(9), policy_id: id(10), expected_sequence: 1 },
  current_review: current, checked_at: current.checked_at, execution_authorized: false });
it('binds approval and withdrawal choices to the current document and sequence', () => {
  expect(parseReviewCandidate(choice(), context, 'contract_review', id(8), now).candidate?.policy_id).toBe(id(10));
  const held = { ...choice(), status: 'paused', candidate: null, current_review: { ...current, status: 'requires_review', approval_current: false, expires_at: null } };
  expect(parseReviewCandidate(held, context, 'contract_review', id(8), now).withdrawal?.review_id).toBe(id(7));
});
it.each([{ artifact_id: id(9) }, { purpose: 'title_report' }, { status: 'paused' }, { execution_authorized: true },
  { checked_at: '2026-10-31T12:00:01Z' }, { current_review: { ...current, sequence: 2 } },
  { candidate: { ...choice().candidate, max_expires_at: '2026-10-31T11:59:59Z' } },
  { candidate: { ...choice().candidate, max_expires_at: '2026-11-02T12:00:00Z' } },
  { withdrawal: { ...choice().withdrawal, review_id: id(11) } }])('rejects invalid choices %j', patch => {
  expect(() => parseReviewCandidate({ ...choice(), ...patch }, context, 'contract_review', id(8), now)).toThrow();
});
