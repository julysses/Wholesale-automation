import { beforeEach, expect, it } from 'vitest';
import { transitionChoice, transitionContext as context, transitionId as id } from '../../../tests/fixtures/contract-transition';
import { parseTransitionChoice, preserveTransition, readPendingTransition, clearConfirmedTransition, clearRejectedTransition, transitionKey, pendingTransitionSchema } from './contract-transition';
const saved = { version: 1 as const, context, request: { id: id(20), expected_version: 2, expected_sequence: 0, expected_status: 'draft' as const,
  target_status: 'pending_signature' as const, reason: '  Original reviewed contract status request, preserved exactly.  ' } };
const receipt = { workspace_id: context.workspaceId, contract_id: context.contractId, contract_version: 2, request_id: saved.request.id, sequence: 1,
  previous_status: 'draft', recorded_status: 'pending_signature', duplicate: true, transition_recorded: true, execution_authorized: false };
beforeEach(() => sessionStorage.clear());
it('preserves exact recovery and clears only a matching historical receipt', () => {
  preserveTransition(sessionStorage, saved); expect(readPendingTransition(sessionStorage, context.userId, context.workspaceId)).toEqual(saved);
  expect(() => preserveTransition(sessionStorage, { ...saved, request: { ...saved.request, reason: 'Different reason cannot replace an uncertain original request.' } })).toThrow();
  expect(() => clearRejectedTransition(sessionStorage, saved, true, false)).toThrow();
  for (const change of [{ contract_version: 1 }, { request_id: id(21) }, { sequence: 2 }, { workspace_id: id(22) }, { execution_authorized: true }, { transition_recorded: false }])
    expect(() => clearConfirmedTransition(sessionStorage, saved, { ...receipt, ...change })).toThrow();
  expect(sessionStorage.length).toBe(1); clearConfirmedTransition(sessionStorage, saved, receipt); expect(sessionStorage.length).toBe(0);
});
it('keeps unreadable or differently scoped recovery intact', () => {
  const key = transitionKey(context.userId, context.workspaceId); sessionStorage.setItem(key, '{broken');
  expect(() => readPendingTransition(sessionStorage, context.userId, context.workspaceId)).toThrow(); expect(sessionStorage.getItem(key)).toBe('{broken');
  sessionStorage.setItem(key, JSON.stringify({ ...saved, request: { ...saved.request, expected_version: 1 } }));
  expect(() => readPendingTransition(sessionStorage, context.userId, context.workspaceId)).toThrow();
});
it('allows a fresh exact choice and rejects stale scope, version and cursor mismatches', () => {
  expect(parseTransitionChoice(transitionChoice(), context).candidate?.expected_sequence).toBe(0);
  for (const change of [{ workspace_id: id(21) }, { contract_id: id(22) }, { contract_version: 1 }, { current_version: 3 },
    { sequence: 1 }, { checked_at: '2020-01-01T00:00:00Z' }, { execution_authorized: true }, { status: 'paused' }])
    expect(() => parseTransitionChoice({ ...transitionChoice(), ...change }, context)).toThrow();
});
it('rejects expired and contradictory nested choices', () => {
  for (const change of [{ expected_version: 1 }, { expected_sequence: 1 }, { expires_at: '2020-01-01T00:00:00Z' }, { target_status: 'executed' }]) {
    const value = transitionChoice(); expect(() => parseTransitionChoice({ ...value, candidate: { ...value.candidate, ...change } }, context)).toThrow();
  }
});
it('holds the old version and already recorded status without offering another transition', () => {
  expect(parseTransitionChoice({ ...transitionChoice(), current_version: 3, status: 'version_changed', candidate: null }, context).candidate).toBeNull();
  expect(parseTransitionChoice({ ...transitionChoice(), current_status: 'pending_signature', sequence: 1, status: 'awaiting_signature', candidate: null }, context).candidate).toBeNull();
});

it('accepts only the matching execution review choice and lifecycle sequence', async () => {
  const { transitionChoice, transitionContext } = await import('../../../tests/fixtures/contract-transition');
  const original = transitionChoice();
  const value = { ...original, current_status: 'pending_signature', sequence: 1,
    candidate: { expected_version: 2, expected_sequence: 1, expected_status: 'pending_signature', target_status: 'executed',
      execution_review_id: original.candidate.signature_review_id, expires_at: original.candidate.expires_at } };
  expect(parseTransitionChoice(value, transitionContext).candidate?.target_status).toBe('executed');
  for (const patch of [{ expected_sequence: 0 }, { expected_status: 'draft' }, { signature_review_id: original.candidate.signature_review_id }, { target_status: 'title_review' }])
    expect(() => parseTransitionChoice({ ...value, candidate: { ...value.candidate, ...patch } }, transitionContext)).toThrow();
  expect(() => parseTransitionChoice({ ...value, status: 'execution_recorded', candidate: null }, transitionContext)).toThrow();
  expect(parseTransitionChoice({ ...value, current_status: 'executed', sequence: 2, status: 'execution_recorded', candidate: null }, transitionContext).candidate).toBeNull();
});

function dispositionChoice() {
  const original = transitionChoice();
  return { ...original, current_status: 'title_review', sequence: 3,
    candidate: { expected_version: 2, expected_sequence: 3, expected_status: 'title_review', target_status: 'disposition_review',
      disposition_review_id: id(30), plan_id: id(31), exit_type: 'principal_acquisition', title_review_id: id(32),
      execution_review_id: id(33), expires_at: original.candidate.expires_at } };
}
it('requires exact disposition roots, supported exit, fresh authority and matching lifecycle', () => {
  const choice = dispositionChoice();
  for (const exit_type of ['principal_acquisition', 'wholesale_assignment'])
    expect(parseTransitionChoice({ ...choice, candidate: { ...choice.candidate, exit_type } }, context).candidate?.target_status).toBe('disposition_review');
  for (const patch of [{ expected_sequence: 2 }, { expected_status: 'executed' }, { expected_version: 1 },
    { disposition_review_id: null }, { plan_id: undefined }, { title_review_id: undefined }, { execution_review_id: undefined },
    { exit_type: 'direct_close' }, { expires_at: choice.checked_at }, { execution_authorized: true }])
    expect(() => parseTransitionChoice({ ...choice, candidate: { ...choice.candidate, ...patch } }, context)).toThrow();
  for (const patch of [{ sequence: 4 }, { current_status: 'disposition_review' }, { workspace_id: id(35) },
    { status: 'disposition_review_required' }, { checked_at: new Date(Date.now() - 31000).toISOString() }])
    expect(() => parseTransitionChoice({ ...choice, ...patch }, context)).toThrow();
});
it('distinguishes required disposition review from a completed handoff with no action', () => {
  const held = { ...dispositionChoice(), status: 'disposition_review_required', candidate: null };
  expect(parseTransitionChoice(held, context).candidate).toBeNull();
  const done = { ...held, status: 'disposition_review_started', current_status: 'disposition_review', sequence: 4 };
  expect(parseTransitionChoice(done, context).candidate).toBeNull();
  for (const value of [{ ...held, sequence: 2 }, { ...held, current_status: 'disposition_review' },
    { ...done, sequence: 3 }, { ...done, current_status: 'title_review' }, { ...done, candidate: dispositionChoice().candidate }])
    expect(() => parseTransitionChoice(value, context)).toThrow();
});
it('retains the exact disposition command through unknown replies and clears only its own receipt', () => {
  const request = { ...saved.request, expected_status: 'title_review' as const, target_status: 'disposition_review' as const, expected_sequence: 3 };
  const pending = { ...saved, request };
  preserveTransition(sessionStorage, pending);
  expect(readPendingTransition(sessionStorage, context.userId, context.workspaceId)).toEqual(pending);
  expect(() => clearRejectedTransition(sessionStorage, pending, true, false)).toThrow();
  const confirmed = { ...receipt, previous_status: 'title_review', recorded_status: 'disposition_review', sequence: 4 };
  for (const patch of [{ recorded_status: 'title_review' }, { previous_status: 'executed' }, { sequence: 3 },
    { contract_version: 1 }, { request_id: id(35) }, { execution_authorized: true }])
    expect(() => clearConfirmedTransition(sessionStorage, pending, { ...confirmed, ...patch })).toThrow();
  expect(sessionStorage.length).toBe(1);
  clearConfirmedTransition(sessionStorage, pending, confirmed); expect(sessionStorage.length).toBe(0);
});
it('rejects skipped disposition edges and authority fields in the saved command', () => {
  for (const patch of [{ expected_status: 'executed' }, { target_status: 'closed' }, { disposition_review_id: id(30) }, { plan_id: id(31) }])
    expect(() => pendingTransitionSchema.parse({ ...saved, request: { ...saved.request, expected_status: 'title_review',
      target_status: 'disposition_review', expected_sequence: 3, ...patch } })).toThrow();
  expect(sessionStorage.length).toBe(0);
});
