import { beforeEach, expect, it } from 'vitest';
import { titleFindingsSchema, titleRequestSchema, parseTitleCandidate, titleApprovalExpiry, pendingTitleSchema, preserveTitle, readPendingTitle, clearConfirmedTitle, clearRejectedTitle, titleKey } from '../src/lib/acquisition/title-review';
import { parseReference } from '../src/lib/acquisition/contract-references';
import { titleId as id, titleContext as context, titleScope as scope, titleFindings, titleChoice, titleReference } from './fixtures/title-review';
beforeEach(() => sessionStorage.clear());
const request = () => ({ id: id(7), expected_version: 2, expected_sequence: 0, status: 'approved', artifact_id: id(8), verification_id: id(9), policy_id: id(10), expires_at: new Date(Date.now() + 60000).toISOString(), personally_reviewed: true, note: 'Personally reviewed the synthetic title findings.', findings: titleFindings() });
it('requires specific next actions and citations without converting unknown findings', () => {
  const f = titleFindings(); f.ownership = { finding: 'unknown', note: 'Ownership has not been confirmed in this report.', required_action: null, sources: [] };
  expect(titleFindingsSchema.safeParse(f).success).toBe(false);
  f.ownership.required_action = 'Ask title counsel to resolve the ownership gap.';
  expect(titleFindingsSchema.parse(f).ownership.finding).toBe('unknown');
  expect(titleRequestSchema.safeParse({ ...request(), findings: f }).success).toBe(false);
  expect(titleRequestSchema.safeParse({ ...request(), findings: f, status: 'requires_resolution', expires_at: null }).success).toBe(true);
});
it('rejects conflicting, duplicate, future or unrelated report originals', () => {
  const f = titleFindings(); f.ownership.sources[0] = { ...f.ownership.sources[0], sha256: 'b'.repeat(64) };
  expect(titleFindingsSchema.safeParse(f).success).toBe(false);
  const duplicate = titleFindings(); duplicate.ownership.sources.push(duplicate.ownership.sources[0]);
  expect(titleFindingsSchema.safeParse(duplicate).success).toBe(false);
  expect(titleRequestSchema.safeParse({ ...request(), expected_version: 1 }).success).toBe(false);
  expect(titleRequestSchema.safeParse({ ...request(), artifact_id: id(99) }).success).toBe(false);
});
it('retains original date precision and rejects unsupported, future or expired policies', () => {
  const now = Date.parse('2026-11-01T06:30:00Z'), f = titleFindings(now), c = parseTitleCandidate(titleChoice(id(8), now), context, id(8), now).candidate!;
  f.report_as_of = { precision: 'date', calendar_date: '2026-11-01', instant: null };
  c.available_until = c.max_expires_at = '2026-11-02T08:00:00Z';
  expect(new Date(titleApprovalExpiry(f, c, now)).toISOString()).toBe('2026-11-02T06:00:00.000Z'); // 25-hour Chicago day
  expect(f.report_as_of.instant).toBeNull();
  c.report_policy.max_age_days = null; c.report_policy.timezone = null;
  expect(() => titleApprovalExpiry(f, c, now)).toThrow();
  const exact = titleFindings(now); exact.report_as_of.instant = '2026-11-01T06:31:00Z';
  expect(() => titleApprovalExpiry(exact, c, now)).toThrow(/future/);
  exact.report_as_of.instant = '2026-10-31T06:00:00Z'; expect(() => titleApprovalExpiry(exact, c, now)).toThrow(/expired/);
});
it.each(['scope', 'stale', 'scan', 'authority', 'expiry'])('rejects inconsistent candidate %s', kind => {
  const c = titleChoice();
  if (kind === 'scope') c.workspace_id = id(88);
  if (kind === 'stale') c.checked_at = new Date(Date.now() - 31000).toISOString();
  if (kind === 'scan') c.candidate!.verification_id = id(88);
  if (kind === 'authority') c.execution_authorized = true;
  if (kind === 'expiry') c.candidate!.max_expires_at = new Date(Date.now() - 1000).toISOString();
  expect(() => parseTitleCandidate(c, context, id(8))).toThrow();
});
it('preserves uncertain exact requests and only clears exact confirmed receipts', () => {
  const saved = pendingTitleSchema.parse({ version: 1, context, request: request() }); preserveTitle(sessionStorage, saved);
  expect(readPendingTitle(sessionStorage, id(1), id(2))).toEqual(saved);
  expect(() => preserveTitle(sessionStorage, { ...saved, request: { ...saved.request, note: 'This changed decision must not overwrite recovery.' } })).toThrow();
  expect(() => clearRejectedTitle(sessionStorage, saved, true, false)).toThrow();
  const receipt = { ...scope, kind: 'title_findings', review_id: saved.request.id, sequence: 1, status: 'approved', duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false };
  expect(() => clearConfirmedTitle(sessionStorage, saved, { ...receipt, contract_version: 3 })).toThrow();
  expect(sessionStorage.length).toBe(1); clearConfirmedTitle(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('holds corrupt, cross-scope and oversized recovery', () => {
  for (const raw of ['{broken', 'x'.repeat(100001), JSON.stringify({ version: 1, context: { ...context, userId: id(88) }, request: request() })]) {
    sessionStorage.setItem(titleKey(id(1), id(2)), raw); expect(() => readPendingTitle(sessionStorage, id(1), id(2))).toThrow();
  }
});
it('requires exact fresh reference scope and original source invariants', () => {
  expect(parseReference(titleReference(), context, id(8)).source_version).toBe(2);
  for (const patch of [{ workspace_id: id(88) }, { artifact_id: id(88) }, { checked_at: new Date(Date.now() - 31000).toISOString() }, { source_version: 1 }, { verification_id: null }]) expect(() => parseReference({ ...titleReference(), ...patch }, context, id(8))).toThrow();
});
