import { titleChoice, titleReference, titleScope, titleId, titleHistoryRecord, titleHistorySummary, titleHistoryEnvelope } from '../fixtures/title-review';
import { titleSources } from '../../src/lib/acquisition/title-review';
import type { PendingTitle } from '../../src/lib/acquisition/title-review';
export class ApiError extends Error { rejectedTitle = false; }
const key = 'synthetic-title-decisions';
let lose = false;
export function loseNextReply() { lose = true; }
export async function apiFetch(path: string, init?: RequestInit) {
  const entries = JSON.parse(sessionStorage.getItem(key) ?? '[]') as PendingTitle['request'][];
  const stamp = new Date().toISOString(), last = entries.at(-1);
  if (path.includes('/title-review/history')) {
    const records = entries.map((r, i) => ({ ...titleHistoryRecord(i + 1, r.status), id: r.id, note: r.note, artifact_id: r.artifact_id,
      verification_id: r.verification_id, personally_reviewed: r.personally_reviewed, expires_at: r.expires_at,
      created_at: new Date(Date.now() - 60000).toISOString(), title_findings: r.findings,
      title_original_review_id: r.status === 'withdrawn' ? entries[i - 1]?.id : null,
      title_original_status: r.status === 'withdrawn' ? entries[i - 1]?.status : null,
      title_sources: r.findings ? [...new Map([{ artifact_id: r.artifact_id, artifact_version: 2, sha256: 'a'.repeat(64), locator: 'Original report' }, ...titleSources(r.findings)].map(s => [s.artifact_id, s])).values()].map(s => ({ artifact_id: s.artifact_id, source_version: s.artifact_version, verification_id: r.verification_id, sha256: s.sha256, purpose: 'title_report', expires_at: new Date(Date.now() + 3600000).toISOString() })) : null }));
    const url = new URL(path, 'http://local'), target = url.pathname.split('/history/')[1];
    if (target) { const record = records.find(r => r.id === target); if (!record) throw new Error('Synthetic original missing'); return { json: async () => ({ ...titleHistoryEnvelope, record }) }; }
    const before = Number(url.searchParams.get('before') ?? 2147483647), all = records.filter(r => r.sequence < before).reverse(), fields = Object.keys(titleHistorySummary());
    return { json: async () => ({ ...titleHistoryEnvelope, items: all.slice(0, 20).map(r => Object.fromEntries(fields.map(key => [key, r[key as keyof typeof r]]))), next_before: all.length > 20 ? all[19].sequence : null }) };
  }
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
