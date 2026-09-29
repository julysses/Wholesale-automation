import { expect, it } from 'vitest';
import { retentionBadge } from '@/lib/retention';

const now = new Date('2026-09-29T12:00:00Z');
const base = { retention_reason: 'why' };

it('labels DNC as keep forever and never as deletable', () => {
  const b = retentionBadge({ ...base, retention_rule: 'dnc', retention_action: 'keep', retention_due_at: null, retention_deletable: false }, now);
  expect(b?.label).toBe('Keep forever');
});

it('shows Delete now once a deletable lead is past its due date', () => {
  const b = retentionBadge({ ...base, retention_rule: 'not_real_estate', retention_action: 'hold', retention_due_at: '2026-07-05T00:00:00Z', retention_deletable: true }, now);
  expect(b).toMatchObject({ label: 'Delete now', tone: 'red' });
});

it('counts down to deletion for work-now leads that are not due yet', () => {
  const soon = retentionBadge({ ...base, retention_rule: 'stale_cold', retention_action: 'hold', retention_due_at: '2026-10-09T12:00:00Z', retention_deletable: true }, now);
  expect(soon).toMatchObject({ label: 'Hold', sub: 'delete in 10d', tone: 'amber' });
  const later = retentionBadge({ ...base, retention_rule: 'stale_warm', retention_action: 'work', retention_due_at: '2027-01-01T00:00:00Z', retention_deletable: true }, now);
  expect(later?.label).toBe('Work now');
  expect(later?.sub).toMatch(/^delete after /);
});

it('holds contacted leads for their review window without offering delete', () => {
  const b = retentionBadge({ ...base, retention_rule: 'worked', retention_action: 'hold', retention_due_at: '2027-09-29T00:00:00Z', retention_deletable: false }, now);
  expect(b?.label).toBe('Hold');
  expect(b?.sub).toMatch(/then archive/);
});

it('returns nothing for leads that have not been evaluated yet', () => {
  expect(retentionBadge({ retention_rule: null, retention_action: null, retention_due_at: null, retention_deletable: false, retention_reason: null }, now)).toBeNull();
});
