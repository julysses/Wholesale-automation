import type { Lead } from '@/types';

export type RetentionTone = 'red' | 'amber' | 'green' | 'gray' | 'blue';
export interface RetentionBadge { label: string; sub?: string; tone: RetentionTone; title: string }

const fmt = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

/** Turns the database's retention verdict into the label shown next to each lead. */
export function retentionBadge(lead: Pick<Lead,
  'retention_rule' | 'retention_action' | 'retention_due_at' | 'retention_deletable' | 'retention_reason'>,
  now: Date = new Date()): RetentionBadge | null {
  const { retention_rule: rule, retention_action: action, retention_due_at: due, retention_deletable: deletable } = lead;
  if (!rule) return null;
  const title = lead.retention_reason || '';
  if (action === 'keep') {
    return { label: rule === 'dnc' ? 'Keep forever' : 'Keep', sub: due ? `until ${fmt(due)}` : undefined, tone: 'gray', title };
  }
  if (!deletable) {
    if (action === 'work') return { label: 'Work now', tone: 'green', title };
    return { label: 'Hold', sub: due ? `to ${fmt(due)}, then archive` : undefined, tone: 'blue', title };
  }
  if (due && new Date(due) <= now) return { label: 'Delete now', tone: 'red', title };
  const days = due ? Math.ceil((new Date(due).getTime() - now.getTime()) / 86_400_000) : null;
  return {
    label: action === 'work' ? 'Work now' : 'Hold',
    sub: due ? `delete ${days !== null && days <= 45 ? `in ${days}d` : `after ${fmt(due)}`}` : undefined,
    tone: days !== null && days <= 30 ? 'amber' : action === 'work' ? 'green' : 'blue',
    title,
  };
}

export const RETENTION_TONE_CLASS: Record<RetentionTone, string> = {
  red: 'bg-red-50 text-red-700 border-red-200',
  amber: 'bg-amber-50 text-amber-800 border-amber-200',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  blue: 'bg-blue-50 text-blue-700 border-blue-200',
  gray: 'bg-gray-50 text-gray-600 border-gray-200',
};
