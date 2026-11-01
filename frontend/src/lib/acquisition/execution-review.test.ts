import { afterEach, expect, it } from 'vitest';
import { emptyTerms } from './contract-terms';
import { clearConfirmedExecution, clearRejectedExecution, executionKey, parseExecutionCandidate,
  pendingExecutionSchema, preserveExecution, readPendingExecution, type PendingExecution } from './execution-review';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 2 };
const finding = { finding: 'confirmed' as const, locator: 'Page 4, signature block', note: 'Synthetic personal finding preserved exactly for recovery.' };
const terms = { ...emptyTerms(), note: 'Synthetic terms require completion and separate source verification.' };
const saved: PendingExecution = { version: 1, context, request: { id: id(7), expected_version: 2, expected_sequence: 0, status: 'approved',
  artifact_id: id(8), verification_id: id(9), policy_id: id(10), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true,
  note: 'Exact original execution review decision for synthetic property.', findings: { seller_signatures: finding, buyer_signatures: finding,
    signing_authority: finding, complete_agreement: finding, terms } } };
const receipt = { workspace_id: id(2), contract_id: id(6), contract_version: 2, kind: 'executed_contract', review_id: id(7), sequence: 1,
  status: 'approved', duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false };
afterEach(() => sessionStorage.clear());
it('preserves original findings through expiry and only clears the exact receipt', () => {
  preserveExecution(sessionStorage, saved); expect(readPendingExecution(sessionStorage, id(1), id(2))).toEqual(saved);
  expect(readPendingExecution(sessionStorage, id(11), id(2))).toBeNull();
  const changed = structuredClone(saved); changed.request.findings!.seller_signatures.locator = 'Changed source reference';
  expect(() => preserveExecution(sessionStorage, changed)).toThrow();
  for (const patch of [{ review_id: id(11) }, { contract_version: 1 }, { kind: 'contract_review' }, { approval_current: true }, { execution_authorized: true }, { sequence: 2 }])
    expect(() => clearConfirmedExecution(sessionStorage, saved, { ...receipt, ...patch })).toThrow();
  expect(() => clearRejectedExecution(sessionStorage, saved, true, false)).toThrow();
  expect(() => clearRejectedExecution(sessionStorage, saved, false, true)).toThrow();
  clearConfirmedExecution(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('preserves malformed recovery and rejects unavailable storage', () => {
  const key = executionKey(id(1), id(2)); sessionStorage.setItem(key, '{broken');
  expect(() => preserveExecution(sessionStorage, saved)).toThrow(); expect(sessionStorage.getItem(key)).toBe('{broken'); sessionStorage.clear();
  const broken = { getItem: () => null, setItem: () => { throw new Error('Storage unavailable'); } } as unknown as Storage;
  expect(() => preserveExecution(broken, saved)).toThrow();
});
it('normalizes object field order while preserving exact values', () => {
  const parsed = pendingExecutionSchema.parse({ ...saved, context: Object.fromEntries(Object.entries(context).reverse()) });
  preserveExecution(sessionStorage, parsed); clearConfirmedExecution(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('rejects changed context, unconfirmed findings and replacement findings on withdrawal', () => {
  expect(() => pendingExecutionSchema.parse({ ...saved, context: { ...context, contractVersion: 3 } })).toThrow();
  const unconfirmed = structuredClone(saved); unconfirmed.request.findings!.seller_signatures.finding = 'unknown';
  expect(() => pendingExecutionSchema.parse(unconfirmed)).toThrow();
  const withdrawn = { ...saved, request: { ...saved.request, status: 'withdrawn', personally_reviewed: false, expires_at: null } };
  expect(() => pendingExecutionSchema.parse(withdrawn)).toThrow();
  expect(pendingExecutionSchema.parse({ ...withdrawn, request: { ...withdrawn.request, findings: null } }).request.findings).toBeNull();
});
function candidate(): ReturnType<typeof parseExecutionCandidate> {
  const stamp = new Date().toISOString();
  return { workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2, artifact_id: id(8),
    status: 'ready_for_human_review', candidate: { artifact_id: id(8), source_version: 1, verification_id: id(9), sha256: 'a'.repeat(64),
      policy_id: id(10), expected_sequence: 1, max_expires_at: new Date(Date.now() + 300000).toISOString() },
    withdrawal: { review_id: id(7), artifact_id: id(12), source_version: 1, verification_id: id(13), policy_id: id(14), expected_sequence: 1 },
    prepared_terms: terms, current_review: { workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2,
      kind: 'executed_contract', review_id: id(7), sequence: 1, status: 'requires_review', approval_current: false, expires_at: null,
      checked_at: stamp, execution_authorized: false }, checked_at: stamp, execution_authorized: false };
}
it('preserves original withdrawal for another selected agreement and held choices', () => {
  const value = candidate(); expect(parseExecutionCandidate(value, context, id(8)).withdrawal!.artifact_id).toBe(id(12));
  value.status = 'paused'; value.candidate = null;
  expect(parseExecutionCandidate(value, context, id(8)).withdrawal!.review_id).toBe(id(7));
});
it.each(['scope', 'time', 'source', 'cursor', 'withdrawal', 'deadline', 'hold', 'terms'])('rejects unsafe execution choice %s', fault => {
  const value = candidate();
  if (fault === 'scope') value.current_review.contract_id = id(20);
  if (fault === 'time') value.checked_at = value.current_review.checked_at = '2020-01-01T00:00:00Z';
  if (fault === 'source') value.candidate!.source_version = 3;
  if (fault === 'cursor') value.candidate!.expected_sequence = 2;
  if (fault === 'withdrawal') value.withdrawal!.review_id = id(20);
  if (fault === 'deadline') value.candidate!.max_expires_at = new Date(Date.now() + 90000000).toISOString();
  if (fault === 'hold') value.status = 'evidence_review_required';
  if (fault === 'terms') value.prepared_terms = null;
  expect(() => parseExecutionCandidate(value, context, id(8))).toThrow();
});

it('holds unknown, date-only, changed and elapsed returned terms without inventing values', async () => {
  const { executionTerms } = await import('../../../tests/fixtures/execution-review');
  const { executionTermsHold } = await import('./execution-review');
  const now = Date.now(), prepared = executionTerms(id(8), now);
  expect(executionTermsHold(prepared, prepared, now)).toBeNull();
  expect(executionTermsHold({ ...prepared, purchase_price_cents: null }, prepared, now)).toMatch(/Complete the price/);
  expect(executionTermsHold({ ...prepared, earnest_money_cents: prepared.purchase_price_cents! + 1 }, prepared, now)).toMatch(/exceeds/);
  expect(executionTermsHold({ ...prepared, purchase_price_cents: prepared.purchase_price_cents! + 1 }, prepared, now)).toMatch(/amendment/);
  const dateOnly = { precision: 'date' as const, calendar_date: '2026-11-20', instant: null };
  expect(executionTermsHold({ ...prepared, closing_deadline: dateOnly }, prepared, now)).toMatch(/date-only/);
  expect(executionTermsHold(prepared, { ...prepared, closing_deadline: dateOnly }, now)).toMatch(/amendment/);
  expect(executionTermsHold(prepared, prepared, Date.parse(prepared.closing_deadline.instant!) + 1)).toMatch(/deadlines/);
  expect(executionTermsHold(prepared, prepared, Date.parse(prepared.effective.instant!) - 1)).toMatch(/effective time/);
});

it('preserves legacy findings and exact optional date-review references', () => {
  expect(pendingExecutionSchema.parse(saved).request.findings).not.toHaveProperty('deadline_reviews');
  const value = structuredClone(saved), findings = value.request.findings!;
  findings.terms.effective = { precision: 'date', calendar_date: '2026-11-01', instant: null };
  findings.terms.sources = [{ term: 'effective', artifact_id: id(8), artifact_version: 1, sha256: 'b'.repeat(64), locator: 'Original effective clause' }];
  findings.deadline_reviews = [{ term: 'effective', review_id: id(21) }];
  preserveExecution(sessionStorage, value);
  expect(readPendingExecution(sessionStorage, id(1), id(2))?.request.findings?.deadline_reviews).toEqual(findings.deadline_reviews);
  for (const refs of [null, [], [{ term: 'closing_deadline', review_id: id(21) }], [findings.deadline_reviews[0], findings.deadline_reviews[0]]])
    expect(() => pendingExecutionSchema.parse({ ...value, request: { ...value.request, findings: { ...findings, deadline_reviews: refs } } })).toThrow();
  expect(() => preserveExecution(sessionStorage, { ...value, request: { ...value.request, findings: { ...findings, deadline_reviews: [{ term: 'effective', review_id: id(22) }] } } })).toThrow();
});

it('binds current exact date interpretations without changing original terms', async () => {
  const { executionTerms } = await import('../../../tests/fixtures/execution-review');
  const { resolveExecutionDates, executionTermsHold } = await import('./execution-review');
  const now = Date.now(), prepared = executionTerms(id(8), now);
  const day = new Date(now + 864000000).toISOString().slice(0, 10);
  prepared.closing_deadline = { precision: 'date', calendar_date: day, instant: null };
  const state = { workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2, kind: 'deadline_resolution', term: 'closing_deadline',
    sequence: 3, review_sequence: 1, review_id: id(21), interpretation_review_id: id(21), original_term: prepared.closing_deadline,
    resolution: { term: 'closing_deadline', calendar_date: day, local_time: '17:00:00', time_zone: 'UTC', resolved_instant: `${day}T17:00:00Z`, basis: 'explicit_document_time',
      source: { term: 'closing_deadline', artifact_id: id(8), artifact_version: 1, sha256: 'a'.repeat(64), locator: 'Closing clause' }, rationale: 'Reviewed the original closing date and explicit time.' },
    status: 'approved', approval_current: true, expires_at: new Date(now + 60000).toISOString(), checked_at: new Date(now).toISOString(), execution_authorized: false };
  const before = JSON.stringify(prepared), resolved = resolveExecutionDates(prepared, prepared, context, { closing_deadline: state }, now);
  expect(resolved.bindings).toEqual([{ term: 'closing_deadline', review_id: id(21) }]); expect(resolved.maxExpiresAt).toBe(now + 60000);
  expect(executionTermsHold(resolved.compared, resolved.original, now)).toBeNull(); expect(JSON.stringify(prepared)).toBe(before);
  for (const patch of [{ workspace_id: id(30) }, { term: 'effective' }, { status: 'requires_review', approval_current: false, expires_at: null },
    { checked_at: new Date(now - 31000).toISOString() }, { expires_at: new Date(now - 1).toISOString() }])
    expect(() => resolveExecutionDates(prepared, prepared, context, { closing_deadline: { ...state, ...patch } }, now)).toThrow();
  expect(() => resolveExecutionDates(prepared, prepared, context, {}, now)).toThrow();
  const changed = { ...prepared, closing_deadline: { ...prepared.closing_deadline, calendar_date: '2099-01-01' } };
  expect(() => resolveExecutionDates(changed, prepared, context, { closing_deadline: state }, now)).toThrow();
});
