import { titleChoice, titleReference, titleScope, titleId } from '../fixtures/title-review';
import type { PendingTitle } from '../../src/lib/acquisition/title-review';
export class ApiError extends Error { rejectedTitle = false; }
const key = 'synthetic-title-decisions';
let lose = false;
export function loseNextReply() { lose = true; }
export async function apiFetch(path: string, init?: RequestInit) {
  const entries = JSON.parse(sessionStorage.getItem(key) ?? '[]') as PendingTitle['request'][];
  const stamp = new Date().toISOString(), last = entries.at(-1);
  if (init?.method === 'POST') {
    const request = JSON.parse(init.body as string) as PendingTitle['request'];
    const prior = entries.find(row => row.id === request.id);
    if (prior && JSON.stringify(prior) !== JSON.stringify(request)) throw new Error('Synthetic retry changed');
    if (!prior && request.expected_sequence !== entries.length) throw new Error('Synthetic sequence changed');
    if (!prior) sessionStorage.setItem(key, JSON.stringify([...entries, request]));
    if (lose) { lose = false; throw new Error('Synthetic lost reply after commit'); }
    return { json: async () => ({ ...titleScope, kind: 'title_findings', review_id: request.id, sequence: request.expected_sequence + 1, status: request.status, duplicate: !!prior, review_recorded: true, approval_current: false, execution_authorized: false }) };
  }
  if (path.includes('/references?')) {
    const purpose = new URL(path, 'http://local').searchParams.get('purpose');
    return { json: async () => ({ ...titleScope, purpose, items: purpose === 'title_report' ? [titleReference(Date.parse(stamp))] : [], next_after: null, checked_at: stamp, execution_authorized: false }) };
  }
  if (path.includes('/references/')) return { json: async () => titleReference() };
  const c = titleChoice(path.includes('artifact_id=') ? titleId(8) : null);
  if (c.resolution) c.resolution.expected_sequence = entries.length;
  if (c.candidate) c.candidate.expected_sequence = entries.length;
  return { json: async () => ({ ...c, withdrawal: last && last.status !== 'withdrawn' ? { review_id: last.id, artifact_id: last.artifact_id, source_version: 2, verification_id: last.verification_id, policy_id: last.policy_id, expected_sequence: entries.length, original_status: last.status } : null,
    current_review: { ...c.current_review, review_id: last?.id ?? null, sequence: entries.length, status: last?.status ?? 'not_reviewed', approval_current: last?.status === 'approved', expires_at: last?.status === 'approved' ? last.expires_at : null } }) };
}
