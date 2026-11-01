import { beforeEach, expect, it } from 'vitest';
import { clearConfirmedPlan, clearRejectedPlan, parsePlanState, planKey, preservePlan, readPendingPlan } from '../src/lib/acquisition/disposition-plan';
import { context, id, pending, receipt, planState } from './fixtures/disposition-plan';
beforeEach(() => sessionStorage.clear());
it('preserves exact original scope and refuses replacing a pending request', () => {
  preservePlan(sessionStorage, pending); expect(readPendingPlan(sessionStorage, context.userId, context.workspaceId)).toEqual(pending);
  expect(() => preservePlan(sessionStorage, { ...pending, request: { ...pending.request, exit_type: 'wholesale_assignment' } })).toThrow();
  expect(() => clearRejectedPlan(sessionStorage, pending, true, false)).toThrow();
  expect(() => clearRejectedPlan(sessionStorage, pending, false, true)).toThrow();
  expect(sessionStorage.length).toBe(1); clearConfirmedPlan(sessionStorage, pending, receipt()); expect(sessionStorage.length).toBe(0);
});
it.each([{ workspace_id: id(90) }, { contract_id: id(90) }, { contract_version: 1 }, { plan_id: id(90) }, { sequence: 2 },
  { status: 'withdrawn' }, { exit_type: 'wholesale_assignment' }, { original_plan_id: id(90) }, { disposition_approved: true }, { execution_authorized: true }])('rejects mismatched receipt %j without clearing recovery', change => {
  preservePlan(sessionStorage, pending); expect(() => clearConfirmedPlan(sessionStorage, pending, { ...receipt(), ...change })).toThrow(); expect(sessionStorage.length).toBe(1);
});
it.each([{ workspace_id: id(90) }, { contract_id: id(90) }, { contract_version: 1 }, { current_version: 1 }, { sequence: 1 },
  { current_status: 'draft' }, { readiness: 'history_limit_reached' }, { disposition_approved: true }, { execution_authorized: true },
  { checked_at: new Date(0).toISOString() }, { checked_at: '2026-11-01' }])('rejects inconsistent current state %j', change => {
  expect(() => parsePlanState({ ...planState(), ...change }, context)).toThrow();
});
it('preserves original withdrawal during pause but rejects changed identity', () => {
  const state = planState(true, true); expect(parsePlanState(state, context).withdrawal?.plan_id).toBe(pending.request.id);
  expect(() => parsePlanState({ ...state, withdrawal: { ...state.withdrawal, exit_type: 'wholesale_assignment' } }, context)).toThrow();
});
it('holds corrupt or foreign recovery', () => {
  sessionStorage.setItem(planKey(context.userId, context.workspaceId), '{broken'); expect(() => readPendingPlan(sessionStorage, context.userId, context.workspaceId)).toThrow();
  sessionStorage.setItem(planKey(context.userId, context.workspaceId), JSON.stringify({ ...pending, context: { ...context, userId: id(80) } }));
  expect(() => readPendingPlan(sessionStorage, context.userId, context.workspaceId)).toThrow();
});
