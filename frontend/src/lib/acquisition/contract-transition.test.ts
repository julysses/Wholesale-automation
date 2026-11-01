import { beforeEach, expect, it } from 'vitest';
import { transitionChoice, transitionContext as context, transitionId as id } from '../../../tests/fixtures/contract-transition';
import { parseTransitionChoice, preserveTransition, readPendingTransition, clearConfirmedTransition, clearRejectedTransition, transitionKey } from './contract-transition';
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
