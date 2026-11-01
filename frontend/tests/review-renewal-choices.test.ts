import { expect, it } from 'vitest';
import { parseRenewalChoice, parseRenewalIndex } from '../src/lib/acquisition/review-renewal-choices';
import { id, context, now, choice, index } from './review-renewal-fixture';
it('allows a new bounded personal review of expired original findings without changing them', () => {
  const raw = choice(), before = structuredClone(raw);
  expect(parseRenewalChoice(raw, context, id(7), now).original.findings).toEqual(raw.original.findings);
  expect(raw).toEqual(before); expect(parseRenewalIndex(index(), context, now).items).toHaveLength(1);
});
it.each([{ workspace_id: id(20) }, { contract_id: id(20) }, { contract_version: 3 }, { execution_authorized: true },
  { checked_at: '2026-11-01T11:59:29Z' }, { checked_at: '2026-11-01T12:00:06Z' }, { private_policy: {} },
  { deadline_term: 'effective' }, { status: 'paused' }, { current_review: null }])('holds wrong or stale choices %j', patch => {
  expect(() => parseRenewalChoice({ ...choice(), ...patch }, context, id(7), now)).toThrow();
});
it('holds unsupported dependencies, changed predecessors, future sources and expired source caps', () => {
  const c = choice();
  for (const patch of [{ previous_review_id: id(20) }, { max_expires_at: '2026-11-01T12:03:00Z' },
    { sources: [{ ...c.candidate.sources[0], source_version: 3 }] }, { sources: [c.candidate.sources[0], c.candidate.sources[0]] }]) {
    expect(() => parseRenewalChoice({ ...c, candidate: { ...c.candidate, ...patch } }, context, id(7), now)).toThrow();
  }
  expect(() => parseRenewalChoice({ ...c, dependencies: [{ ...c.current_review, root_review_id: id(20), kind: 'executed_contract', deadline_term: null }] }, context, id(7), now)).toThrow();
  expect(() => parseRenewalChoice(c, context, id(20), now)).toThrow();
});
it('holds duplicate streams, expired current claims and choices that expire in transit', () => {
  const i = index();
  expect(() => parseRenewalIndex({ ...i, items: [...i.items, ...i.items] }, context, now)).toThrow();
  expect(() => parseRenewalIndex({ ...i, items: [i.items[0], { ...i.items[0], root_review_id: id(20) }] }, context, now)).toThrow();
  expect(() => parseRenewalIndex({ ...i, items: [{ ...i.items[0], current_review: { ...i.items[0].current_review, approval_current: true } }] }, context, now)).toThrow();
  const c = choice(); c.candidate.max_expires_at = '2026-11-01T12:00:01Z';
  expect(() => parseRenewalChoice(c, context, id(7), now + 2000)).toThrow();
});
