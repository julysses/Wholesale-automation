import { beforeEach, expect, it } from 'vitest';
import { renewalRequestSchema, pendingRenewalSchema, preserveRenewal, readPendingRenewal, renewalKey,
  clearConfirmedRenewal, clearRejectedRenewal, type PendingRenewal } from '../src/lib/acquisition/review-renewal';
const id = (n: number) => `af139000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
const pending = (): PendingRenewal => ({ version: 1, context, request: { id: id(7), expected_version: 2, expected_sequence: 3,
  kind: 'title_findings', deadline_term: null, root_review_id: id(8), previous_review_id: id(9), policy_id: id(10),
  expected_snapshot_sha256: 'a'.repeat(64), expires_at: '2026-01-01T00:00:00Z', personally_reviewed: true,
  note: '  Personally reviewed the unchanged original facts and current evidence.  ' } });
const receipt = () => ({ workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2,
  kind: 'title_findings', deadline_term: null, review_id: id(7), root_review_id: id(8), previous_review_id: id(9),
  sequence: 4, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false });
beforeEach(() => sessionStorage.clear());
it('retains exact expired requests and notes across reload, then clears only confirmed history', () => {
  const saved = preserveRenewal(sessionStorage, pending());
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toEqual(saved);
  expect(preserveRenewal(sessionStorage, saved)).toEqual(saved); expect(saved.request.note).toBe(pending().request.note);
  expect(() => preserveRenewal(sessionStorage, { ...saved, request: { ...saved.request, id: id(11) } })).toThrow();
  expect(() => preserveRenewal(sessionStorage, { ...saved, context: { ...context, contractId: id(11) } })).toThrow();
  clearConfirmedRenewal(sessionStorage, saved, receipt());
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toBeNull();
});
it.each([{ personally_reviewed: false }, { root_review_id: id(7) }, { previous_review_id: id(7) }, { deadline_term: 'effective' },
  { kind: 'deadline_resolution' }, { expected_sequence: 0 }, { expires_at: '2026-01-01' }, { expected_snapshot_sha256: 'A'.repeat(64) },
  { findings: {} }, { sources: [] }, { note: ' '.repeat(30) }, { actor_id: id(1) }])('rejects invalid or replacement data %j', change => {
  expect(renewalRequestSchema.safeParse({ ...pending().request, ...change }).success).toBe(false);
});
it('requires the exact date term and matching contract version', () => {
  expect(renewalRequestSchema.safeParse({ ...pending().request, kind: 'deadline_resolution', deadline_term: 'closing_deadline' }).success).toBe(true);
  expect(pendingRenewalSchema.safeParse({ ...pending(), context: { ...context, contractVersion: 3 } }).success).toBe(false);
});
it.each([{ workspace_id: id(11) }, { contract_id: id(11) }, { contract_version: 3 }, { root_review_id: id(11) },
  { previous_review_id: id(11) }, { review_id: id(11) }, { kind: 'executed_contract' }, { sequence: 5 },
  { approval_current: true }, { execution_authorized: true }, { review_recorded: false }, { unexpected: true }])('holds a mismatched receipt %j', change => {
  const saved = preserveRenewal(sessionStorage, pending());
  expect(() => clearConfirmedRenewal(sessionStorage, saved, { ...receipt(), ...change })).toThrow();
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toEqual(saved);
});
it('does not discard an uncertain save when a later retry is rejected', () => {
  const saved = preserveRenewal(sessionStorage, pending());
  expect(() => clearRejectedRenewal(sessionStorage, saved, true, false)).toThrow();
  expect(() => clearRejectedRenewal(sessionStorage, saved, false, true)).toThrow();
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toEqual(saved);
  clearRejectedRenewal(sessionStorage, saved, true, true);
  expect(readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toBeNull();
});
it('holds corrupt, oversized or cross-user data and refuses silent storage loss', () => {
  const key = renewalKey(context.userId, context.workspaceId);
  for (const raw of ['broken', ' '.repeat(20001), JSON.stringify({ ...pending(), context: { ...context, userId: id(11) } })]) {
    sessionStorage.setItem(key, raw); expect(() => readPendingRenewal(sessionStorage, context.userId, context.workspaceId)).toThrow();
    expect(sessionStorage.getItem(key)).toBe(raw);
  }
  const missingStorage = { getItem: () => null, setItem: () => undefined } as unknown as Storage;
  expect(() => preserveRenewal(missingStorage, pending())).toThrow('Renewal recovery unavailable');
});
