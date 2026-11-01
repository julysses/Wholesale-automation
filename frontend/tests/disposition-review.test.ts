import { beforeEach, expect, it } from 'vitest';
import { dispositionFindingsSchema, dispositionRequestSchema, parseDispositionCandidate, pendingDispositionSchema, preserveDisposition,
  readPendingDisposition, clearConfirmedDisposition, clearRejectedDisposition, dispositionKey, dispositionEntries } from '../src/lib/acquisition/disposition-review';
import { dispositionId as id, dispositionContext as context, dispositionScope as scope, dispositionFindings, dispositionChoice } from './fixtures/disposition-review';
beforeEach(() => sessionStorage.clear());
const request = () => ({ id: id(7), expected_version: 2, expected_sequence: 0, status: 'approved', plan_id: id(11), original_review_id: null,
  policy_id: id(10), expires_at: new Date(Date.now() + 60000).toISOString(), personally_reviewed: true, note: 'Personally reviewed this original disposition and requirements.', findings: dispositionFindings() });
it('retains unknown findings and required actions without approving them', () => {
  const findings = dispositionFindings(); findings.assignment!.legal_basis = { finding: 'unknown', note: 'The original legal basis still needs counsel review.', required_action: null, sources: [] };
  expect(dispositionFindingsSchema.safeParse(findings).success).toBe(false);
  findings.assignment!.legal_basis.required_action = 'Obtain counsel review of the original assignment provisions.';
  expect(dispositionFindingsSchema.parse(findings).assignment!.legal_basis.finding).toBe('unknown');
  expect(dispositionRequestSchema.safeParse({ ...request(), findings }).success).toBe(false);
  expect(dispositionRequestSchema.safeParse({ ...request(), findings, status: 'requires_resolution', expires_at: null }).success).toBe(true);
});
it('separates exits and rejects conflicting duplicate or future citations', () => {
  expect(dispositionEntries(dispositionFindings(false))).toHaveLength(3); expect(dispositionEntries(dispositionFindings())).toHaveLength(7);
  expect(dispositionFindingsSchema.safeParse({ ...dispositionFindings(), assignment: null }).success).toBe(false);
  const conflicting = dispositionFindings(); conflicting.assignment!.legal_basis.sources[0].sha256 = 'b'.repeat(64);
  expect(dispositionFindingsSchema.safeParse(conflicting).success).toBe(false);
  const future = request(); future.findings.contractual_interest.sources[0].artifact_version = 3;
  expect(dispositionRequestSchema.safeParse(future).success).toBe(false);
  const duplicate = dispositionFindings(); duplicate.contractual_interest.sources.push(duplicate.contractual_interest.sources[0]);
  expect(dispositionFindingsSchema.safeParse(duplicate).success).toBe(false);
});
it('requires exact original withdrawal without replacement findings', () => {
  const value = { ...request(), expected_sequence: 1, status: 'withdrawn', original_review_id: id(55), personally_reviewed: false, expires_at: null, findings: null };
  expect(dispositionRequestSchema.safeParse(value).success).toBe(true);
  for (const patch of [{ original_review_id: null }, { original_review_id: value.id }, { expected_sequence: 0 }, { personally_reviewed: true }, { findings: dispositionFindings() }]) expect(dispositionRequestSchema.safeParse({ ...value, ...patch }).success).toBe(false);
});
it.each([true, false])('accepts exact fresh original choices assignment=%s', assignment => {
  const c = parseDispositionCandidate(dispositionChoice(assignment), context); expect(c.candidate!.executed_source.source_version).toBe(1); expect(c.execution_authorized).toBe(false);
});
it.each(['scope', 'stale', 'sequence', 'root', 'legal', 'title', 'expiry', 'policy', 'version', 'full_history', 'legal_hold'])('rejects contradictory choice %s', kind => {
  const c = dispositionChoice();
  if (kind === 'scope') c.workspace_id = id(80);
  if (kind === 'stale') c.checked_at = new Date(Date.now() - 31000).toISOString();
  if (kind === 'sequence') c.resolution.expected_sequence = 2;
  if (kind === 'root') c.resolution.executed_source.purpose = 'title_report';
  if (kind === 'legal') c.resolution.legal_source!.sha256 = 'b'.repeat(64);
  if (kind === 'title') c.candidate.title_status = 'requires_resolution';
  if (kind === 'expiry') c.candidate.max_expires_at = new Date(Date.now() - 1000).toISOString();
  if (kind === 'policy') c.candidate.policy_id = id(80);
  if (kind === 'version') c.resolution.executed_source.source_version = 3;
  const raw = kind === 'full_history' ? { ...c, status: 'history_limit_reached', candidate: null, resolution: null }
    : kind === 'legal_hold' ? { ...c, status: 'legal_evidence_required', candidate: null } : c;
  expect(() => parseDispositionCandidate(raw, context)).toThrow();
});
it('retains original withdrawal independently of a new proposal or pause', () => {
  const c = dispositionChoice(), withdrawal = { review_id: id(70), plan_id: id(71), exit_type: 'principal_acquisition', policy_id: id(72), expected_sequence: 1, original_status: 'approved' };
  const paused = { ...c, status: 'paused', candidate: null, resolution: null, withdrawal, current_review: { ...c.current_review, review_id: id(70), sequence: 1, status: 'requires_review' } };
  expect(parseDispositionCandidate(paused, context).withdrawal!.plan_id).toBe(id(71));
  expect(() => parseDispositionCandidate({ ...paused, withdrawal: { ...withdrawal, review_id: id(88) } }, context)).toThrow();
});
it.each([-31, -30, 5, 6])('checks fixed request-time offset %s', offset => {
  const now = Date.now(), c = dispositionChoice(true, now); c.checked_at = c.current_review.checked_at = new Date(now + offset * 1000).toISOString();
  if (offset === -30 || offset === 5) expect(() => parseDispositionCandidate(c, context, now)).not.toThrow();
  else expect(() => parseDispositionCandidate(c, context, now)).toThrow();
});
it('preserves exact requests after reload or later rejection until matching receipt', () => {
  const saved = pendingDispositionSchema.parse({ version: 1, context, request: request() }); preserveDisposition(sessionStorage, saved);
  expect(readPendingDisposition(sessionStorage, id(1), id(2))).toEqual(saved);
  expect(() => preserveDisposition(sessionStorage, { ...saved, request: { ...saved.request, plan_id: id(80) } })).toThrow();
  expect(() => clearRejectedDisposition(sessionStorage, saved, true, false)).toThrow(); expect(() => clearRejectedDisposition(sessionStorage, saved, false, true)).toThrow();
  const receipt = { ...scope, kind: 'disposition_findings', review_id: saved.request.id, sequence: 1, status: 'approved', duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false };
  for (const patch of [{ contract_version: 3 }, { review_id: id(80) }, { status: 'withdrawn' }, { approval_current: true }]) expect(() => clearConfirmedDisposition(sessionStorage, saved, { ...receipt, ...patch })).toThrow();
  expect(sessionStorage.length).toBe(1); clearConfirmedDisposition(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('clears only a definite first rejection of an unchanged original request', () => {
  const saved = pendingDispositionSchema.parse({ version: 1, context, request: request() }); preserveDisposition(sessionStorage, saved);
  clearRejectedDisposition(sessionStorage, saved, true, true); expect(sessionStorage.length).toBe(0);
  preserveDisposition(sessionStorage, saved); sessionStorage.setItem(dispositionKey(id(1), id(2)), JSON.stringify({ ...saved, request: { ...saved.request, plan_id: id(90) } }));
  expect(() => clearRejectedDisposition(sessionStorage, saved, true, true)).toThrow();
});
it('holds corrupt oversized cross-scope and mismatched-version recovery', () => {
  for (const raw of ['{broken', 'x'.repeat(100001), JSON.stringify({ version: 1, context: { ...context, userId: id(88) }, request: request() }), JSON.stringify({ version: 1, context: { ...context, contractVersion: 3 }, request: request() })]) {
    sessionStorage.setItem(dispositionKey(id(1), id(2)), raw); expect(() => readPendingDisposition(sessionStorage, id(1), id(2))).toThrow();
  }
});
