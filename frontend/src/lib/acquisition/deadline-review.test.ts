import { afterEach, expect, it } from 'vitest';
import { clearConfirmedDeadline, clearRejectedDeadline, deadlineKey, parseDeadlineCandidate, preserveDeadline, readPendingDeadline, resolutionSchema, type PendingDeadline } from './deadline-review';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
const resolution = { term: 'closing_deadline' as const, calendar_date: '2026-11-01', local_time: '01:30:00', time_zone: 'America/Chicago', resolved_instant: '2026-11-01T01:30:00-05:00', basis: 'explicit_document_time' as const,
  source: { term: 'closing_deadline' as const, artifact_id: id(8), artifact_version: 1, sha256: 'b'.repeat(64), locator: 'Closing clause, page 4' }, rationale: 'Synthetic reviewer supplied explicit source interpretation.' };
const saved: PendingDeadline = { version: 1, context, request: { id: id(7), expected_version: 2, expected_sequence: 4, status: 'approved', artifact_id: id(8), verification_id: id(9), policy_id: id(10), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true,
  note: 'Synthetic exact personal date interpretation for recovery.', term: 'closing_deadline', resolution, original_review_id: null } };
const receipt = { workspace_id: id(2), contract_id: id(6), contract_version: 2, kind: 'deadline_resolution', term: 'closing_deadline', review_id: id(7), interpretation_review_id: id(7), sequence: 5, status: 'approved', duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false };
afterEach(() => sessionStorage.clear());
it('accepts both explicit DST fold offsets without choosing one', () => {
  expect(resolutionSchema.parse(resolution)).toEqual(resolution);
  expect(resolutionSchema.parse({ ...resolution, resolved_instant: '2026-11-01T01:30:00-06:00' }).resolved_instant).toContain('-06:00');
});
it.each([{ resolved_instant: '2026-11-01T01:30:00-04:00' }, { time_zone: 'No/Such_Zone' }, { calendar_date: '2026-02-30' },
  { calendar_date: '2026-03-08', local_time: '02:30:00', resolved_instant: '2026-03-08T02:30:00-06:00' }, { resolved_instant: '2026-11-01T01:30:00.0001-05:00' }, { term: 'effective' }, { resolved_instant: '2026-11-01T01:30:00' }])('rejects mismatched or inferred times %j', patch => expect(() => resolutionSchema.parse({ ...resolution, ...patch })).toThrow());
it('retains expired requests and rejects mixed receipts or later rejection', () => {
  preserveDeadline(sessionStorage, saved); expect(readPendingDeadline(sessionStorage, id(1), id(2))).toEqual(saved);
  for (const patch of [{ interpretation_review_id: id(20) }, { term: 'effective' }, { sequence: 6 }, { approval_current: true }, { contract_version: 1 }]) expect(() => clearConfirmedDeadline(sessionStorage, saved, { ...receipt, ...patch })).toThrow();
  expect(() => clearRejectedDeadline(sessionStorage, saved, true, false)).toThrow();
  expect(() => clearRejectedDeadline(sessionStorage, saved, false, true)).toThrow();
  clearConfirmedDeadline(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('keeps original withdrawal identity independent of shared sequence', () => {
  const withdrawn: PendingDeadline = { ...saved, request: { ...saved.request, id: id(11), expected_sequence: 8, status: 'withdrawn', personally_reviewed: false, expires_at: null, resolution: null, original_review_id: id(7) } };
  preserveDeadline(sessionStorage, withdrawn); const response = { ...receipt, review_id: id(11), sequence: 9, status: 'withdrawn' };
  expect(() => clearConfirmedDeadline(sessionStorage, withdrawn, { ...response, interpretation_review_id: id(11) })).toThrow();
  clearConfirmedDeadline(sessionStorage, withdrawn, response); expect(sessionStorage.length).toBe(0);
});
it('preserves corrupt recovery', () => {
  const key = deadlineKey(id(1), id(2)); sessionStorage.setItem(key, '{broken');
  expect(() => preserveDeadline(sessionStorage, saved)).toThrow(); expect(sessionStorage.getItem(key)).toBe('{broken');
});
function candidate() {
  const now = new Date().toISOString(), expiry = new Date(Date.now() + 300000).toISOString();
  return { workspace_id: id(2), contract_id: id(6), contract_version: 2, term: 'closing_deadline', artifact_id: id(12), status: 'evidence_review_required', candidate: null,
    withdrawal: { review_id: id(7), artifact_id: id(8), source_version: 1, verification_id: id(9), policy_id: id(10), expected_sequence: 8 }, original_source: { ...resolution.source, verification_id: id(9) },
    current_review: { workspace_id: id(2), contract_id: id(6), contract_version: 2, kind: 'deadline_resolution', term: 'closing_deadline', sequence: 8, review_sequence: 5, review_id: id(7), interpretation_review_id: id(7), original_term: { precision: 'date', calendar_date: '2026-11-01', instant: null }, resolution,
      status: 'approved', approval_current: true, expires_at: expiry, checked_at: now, execution_authorized: false }, checked_at: now, execution_authorized: false };
}
it('preserves original withdrawal when another document is selected', () => expect(parseDeadlineCandidate(candidate(), context, 'closing_deadline', id(12)).withdrawal?.expected_sequence).toBe(8));
it.each(['term', 'scope', 'cursor', 'source', 'time', 'identity', 'expiry'])('rejects unsafe deadline choices %s', fault => {
  const v = candidate();
  if (fault === 'term') v.current_review.term = 'effective';
  if (fault === 'scope') v.contract_id = id(22);
  if (fault === 'cursor') v.withdrawal.expected_sequence = 5;
  if (fault === 'source') v.withdrawal.artifact_id = id(12);
  if (fault === 'time') v.checked_at = v.current_review.checked_at = '2020-01-01T00:00:00Z';
  if (fault === 'identity') v.current_review.interpretation_review_id = id(22);
  if (fault === 'expiry') v.current_review.expires_at = '2020-01-01T00:00:00Z';
  expect(() => parseDeadlineCandidate(v, context, 'closing_deadline', id(12))).toThrow();
});
