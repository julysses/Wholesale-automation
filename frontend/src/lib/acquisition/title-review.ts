import { z } from 'zod';
import { id } from './mail-content';
import { contextSchema, type DocumentContext } from './contract-documents';
import { dateTerm } from './contract-terms';
export const titleLabels = { ownership: 'Ownership', legal_description: 'Legal description', liens_and_payoffs: 'Liens and payoffs', exceptions_and_encumbrances: 'Exceptions and encumbrances', occupancy_and_possession: 'Occupancy and possession' };
const timestamp = z.string().datetime({ offset: true });
const version = z.number().int().min(1).max(2147483647);
const sequence = z.number().int().min(0).max(2147483647);
const note = z.string().max(4000).refine(v => v.trim().length >= 20 && !v.includes('\0'));
export const titleFindingNames = ['ownership', 'legal_description', 'liens_and_payoffs', 'exceptions_and_encumbrances', 'occupancy_and_possession'] as const;
export const titleSourceSchema = z.object({ artifact_id: id, artifact_version: version, sha256: z.string().regex(/^[0-9a-f]{64}$/),
  locator: z.string().max(1000).refine(v => !!v.trim() && !Array.from(v).some(c => c.charCodeAt(0) < 32)) }).strict();
const finding = z.object({ finding: z.enum(['satisfactory', 'requires_resolution', 'unknown']), note,
  required_action: note.nullable(), sources: z.array(titleSourceSchema).max(3) }).strict().refine(v =>
  (v.finding === 'satisfactory' ? v.sources.length > 0 && v.required_action === null : v.required_action !== null)
  && new Set(v.sources.map(s => JSON.stringify(s))).size === v.sources.length);
export const titleFindingsSchema = z.object({ report_as_of: dateTerm.refine(v => v.instant === null || /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(v.instant)),
  report_as_of_source: titleSourceSchema.nullable(), report_note: note,
  ownership: finding, legal_description: finding, liens_and_payoffs: finding,
  exceptions_and_encumbrances: finding, occupancy_and_possession: finding }).strict().superRefine((v, ctx) => {
    if ((v.report_as_of.precision === 'unknown') !== (v.report_as_of_source === null)) ctx.addIssue({ code: 'custom', message: 'Known report cutoff needs its original citation.' });
    const originals = new Map<string, string>();
    for (const source of titleSources(v)) {
      const identity = `${source.artifact_version}:${source.sha256}`;
      if (originals.has(source.artifact_id) && originals.get(source.artifact_id) !== identity) ctx.addIssue({ code: 'custom', message: 'Original source identities conflict.' });
      originals.set(source.artifact_id, identity);
    }
  });
export type TitleFindings = z.infer<typeof titleFindingsSchema>;
export type TitleSource = z.infer<typeof titleSourceSchema>;
export function titleSources(value: { report_as_of_source: TitleSource | null } & Record<typeof titleFindingNames[number], { sources: TitleSource[] }>) {
  return [...(value.report_as_of_source ? [value.report_as_of_source] : []), ...titleFindingNames.flatMap(name => value[name].sources)];
}
export const titleRequestSchema = z.object({ id, expected_version: version, expected_sequence: sequence.max(2147483646),
  status: z.enum(['approved', 'requires_resolution', 'withdrawn']), artifact_id: id, verification_id: id, policy_id: id,
  expires_at: timestamp.nullable(), personally_reviewed: z.boolean(), note, findings: titleFindingsSchema.nullable() }).strict().refine(v => {
    if (v.status === 'withdrawn') return !v.personally_reviewed && v.expires_at === null && v.findings === null;
    if (!v.personally_reviewed || !v.findings || titleSources(v.findings).some(s => s.artifact_version > v.expected_version)
      || v.findings.report_as_of_source && v.findings.report_as_of_source.artifact_id !== v.artifact_id) return false;
    return v.status === 'approved' ? v.expires_at !== null && v.findings.report_as_of.precision !== 'unknown'
      && titleFindingNames.every(name => v.findings![name].finding === 'satisfactory') : v.expires_at === null;
  });
export const pendingTitleSchema = z.object({ version: z.literal(1), context: contextSchema, request: titleRequestSchema }).strict()
  .refine(v => v.context.contractVersion === v.request.expected_version);
export type PendingTitle = z.infer<typeof pendingTitleSchema>;
export const titleKey = (user: string, workspace: string) => `wholesale.contract.title:v1:${id.parse(user)}:${id.parse(workspace)}`;
export function readPendingTitle(storage: Pick<Storage, 'getItem'>, user: string, workspace: string) {
  const raw = storage.getItem(titleKey(user, workspace)); if (raw === null) return null;
  if (raw.length > 100000) throw new Error('Saved title review exceeds recovery limits');
  const saved = pendingTitleSchema.parse(JSON.parse(raw));
  if (saved.context.userId !== user || saved.context.workspaceId !== workspace) throw new Error('Saved title review scope changed');
  return saved;
}
export function preserveTitle(storage: Storage, value: PendingTitle) {
  const saved = pendingTitleSchema.parse(value), c = saved.context, key = titleKey(c.userId, c.workspaceId);
  const current = readPendingTitle(storage, c.userId, c.workspaceId);
  if (current && JSON.stringify(current) !== JSON.stringify(saved)) throw new Error('Another title review needs recovery');
  const raw = JSON.stringify(saved); if (raw.length > 100000) throw new Error('Saved title review exceeds recovery limits');
  storage.setItem(key, raw); if (storage.getItem(key) !== raw) throw new Error('Title review recovery unavailable'); return saved;
}
function clear(storage: Storage, value: PendingTitle) {
  const saved = pendingTitleSchema.parse(value), c = saved.context, key = titleKey(c.userId, c.workspaceId);
  if (JSON.stringify(readPendingTitle(storage, c.userId, c.workspaceId)) !== JSON.stringify(saved)) throw new Error('Saved title review changed');
  storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error('Title review recovery not cleared');
}
export function clearConfirmedTitle(storage: Storage, saved: PendingTitle, raw: unknown) {
  const receipt = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('title_findings'),
    review_id: id, sequence: sequence.min(1), status: z.enum(['approved', 'requires_resolution', 'withdrawn']), duplicate: z.boolean(),
    review_recorded: z.literal(true), approval_current: z.literal(false), execution_authorized: z.literal(false) }).strict().parse(raw);
  const c = saved.context, r = saved.request;
  if (receipt.workspace_id !== c.workspaceId || receipt.contract_id !== c.contractId || receipt.contract_version !== c.contractVersion
    || receipt.review_id !== r.id || receipt.sequence !== r.expected_sequence + 1 || receipt.status !== r.status) throw new Error('Title receipt mismatch');
  clear(storage, saved);
}
export function clearRejectedTitle(storage: Storage, saved: PendingTitle, definitive: boolean, firstAttempt: boolean) {
  if (!definitive || !firstAttempt) throw new Error('An earlier title review outcome is still unknown'); clear(storage, saved);
}
const stateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, kind: z.literal('title_findings'),
  review_id: id.nullable(), sequence, status: z.enum(['not_reviewed', 'approved', 'requires_resolution', 'withdrawn', 'requires_review']),
  approval_current: z.boolean(), expires_at: timestamp.nullable(), checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
const resolutionChoice = z.object({ artifact_id: id, source_version: version, verification_id: id, sha256: z.string().regex(/^[0-9a-f]{64}$/),
  policy_id: id, expected_sequence: sequence.max(2147483646), available_until: timestamp }).strict();
const reportPolicy = z.object({ max_age_seconds: z.number().int().min(1).max(31536000).nullable(),
  max_age_days: z.number().int().min(0).max(365).nullable(), timezone: z.string().min(1).max(100).nullable() }).strict().refine(v => {
    if ((v.max_age_days === null) !== (v.timezone === null) || v.max_age_days === null && v.max_age_seconds === null) return false;
    try { if (v.timezone !== null) new Intl.DateTimeFormat('en-CA', { timeZone: v.timezone }); return true; } catch { return false; }
  });
const candidateSchema = z.object({ workspace_id: id, contract_id: id, contract_version: version, artifact_id: id.nullable(),
  status: z.enum(['paused', 'contract_unavailable', 'history_limit_reached', 'document_required', 'reviewer_policy_required', 'evidence_review_required',
    'execution_review_required', 'report_freshness_policy_required', 'ready_for_human_review']),
  candidate: resolutionChoice.extend({ max_expires_at: timestamp, report_policy: reportPolicy }).strict().nullable(), resolution: resolutionChoice.nullable(),
  withdrawal: z.object({ review_id: id, artifact_id: id, source_version: version, verification_id: id, policy_id: id,
    expected_sequence: sequence.min(1).max(2147483646), original_status: z.enum(['approved', 'requires_resolution']) }).strict().nullable(),
  current_review: stateSchema, checked_at: timestamp, execution_authorized: z.literal(false) }).strict();
export function parseTitleCandidate(raw: unknown, context: DocumentContext, artifact: string | null, now = Date.now()) {
  const value = candidateSchema.parse(raw), current = value.current_review;
  for (const item of [value, current]) if (item.workspace_id !== context.workspaceId || item.contract_id !== context.contractId || item.contract_version !== context.contractVersion
    || !Number.isFinite(now) || now - Date.parse(item.checked_at) > 30000 || Date.parse(item.checked_at) - now > 5000) throw new Error('Fresh title review context required');
  if (value.artifact_id !== artifact || value.checked_at !== current.checked_at
    || (current.status === 'not_reviewed' ? current.review_id !== null || current.sequence !== 0 : current.review_id === null || current.sequence === 0)
    || current.approval_current !== (current.status === 'approved')
    || (current.approval_current ? current.expires_at === null || Date.parse(current.expires_at) <= Math.max(now, Date.parse(current.checked_at)) : current.expires_at !== null)) throw new Error('Consistent title review required');
  const choice = value.candidate, resolution = value.resolution, withdrawal = value.withdrawal;
  if ((value.status === 'ready_for_human_review') !== (choice !== null)
    || ['ready_for_human_review', 'execution_review_required', 'report_freshness_policy_required'].includes(value.status) !== (resolution !== null)) throw new Error('Consistent title choices required');
  if (resolution && (resolution.artifact_id !== artifact || resolution.source_version > context.contractVersion || resolution.expected_sequence !== current.sequence
    || Date.parse(resolution.available_until) <= Math.max(now, Date.parse(value.checked_at)) || Date.parse(resolution.available_until) - Date.parse(value.checked_at) > 86400000)) throw new Error('Current bounded title source required');
  if (choice && (!resolution || Object.entries(resolution).some(([key, v]) => choice[key as keyof typeof resolution] !== v)
    || Date.parse(choice.max_expires_at) <= Math.max(now, Date.parse(value.checked_at)) || Date.parse(choice.max_expires_at) > Date.parse(resolution.available_until))) throw new Error('Approval source or expiry changed');
  if (withdrawal && (withdrawal.review_id !== current.review_id || withdrawal.source_version > context.contractVersion || withdrawal.expected_sequence !== current.sequence
    || !['approved', 'requires_review', 'requires_resolution'].includes(current.status)
    || withdrawal.original_status !== (current.status === 'requires_resolution' ? 'requires_resolution' : 'approved'))) throw new Error('Original title withdrawal required');
  return value;
}
export type TitleChoices = ReturnType<typeof parseTitleCandidate>;
/** Policy expiry only. Never modify or infer a timestamp for a calendar report. */
export function titleApprovalExpiry(findings: TitleFindings, choice: NonNullable<TitleChoices['candidate']>, now = Date.now()) {
  const report = titleFindingsSchema.parse(findings).report_as_of, policy = reportPolicy.parse(choice.report_policy);
  let bound = Math.min(Date.parse(choice.max_expires_at), Date.parse(choice.available_until));
  if (!Number.isFinite(now) || bound <= now) throw new Error('Refresh title review choices.');
  if (report.precision === 'instant' && policy.max_age_seconds !== null) {
    const cutoff = Date.parse(report.instant!);
    if (cutoff > now) throw new Error('Report cutoff is in the future.');
    bound = Math.min(bound, cutoff + policy.max_age_seconds * 1000);
  } else if (report.precision === 'date' && policy.max_age_days !== null && policy.timezone !== null) {
    const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: policy.timezone, year: 'numeric', month: '2-digit', day: '2-digit' });
    const day = (at: number) => { const parts = formatter.formatToParts(at); return ['year', 'month', 'day'].map(k => parts.find(p => p.type === k)!.value.padStart(k === 'year' ? 4 : 2, '0')).join('-'); };
    const today = day(now), original = report.calendar_date!, last = new Date(Date.parse(original) + policy.max_age_days * 86400000).toISOString().slice(0, 10);
    if (original > today || today > last) throw new Error('Report date is future or outside the reviewed policy.');
    if (day(bound) > last) { let low = now, high = bound; while (high - low > 1) { const mid = Math.floor((high + low) / 2); if (day(mid) > last) high = mid; else low = mid; } bound = high; }
  } else throw new Error('A known cutoff and a reviewed policy for its precision are required.');
  if (bound <= now) throw new Error('Report freshness has expired.');
  return bound;
}
