import { titleFindingNames, type TitleFindings } from '../../src/lib/acquisition/title-review';
export const titleId = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
export const titleContext = { userId: titleId(1), workspaceId: titleId(2), leadId: titleId(3), propertyId: titleId(4), offerId: titleId(5), contractId: titleId(6), contractVersion: 2 };
export const titleScope = { workspace_id: titleId(2), contract_id: titleId(6), contract_version: 2 };
export function titleFindings(now = Date.now()): TitleFindings {
  const source = { artifact_id: titleId(8), artifact_version: 2, sha256: 'a'.repeat(64), locator: 'Page 1 of the original report' };
  return { report_as_of: { precision: 'instant', calendar_date: null, instant: new Date(now - 60000).toISOString() }, report_as_of_source: source, report_note: 'Synthetic original report with disclosed limitations.',
    ...Object.fromEntries(titleFindingNames.map(name => [name, { finding: 'satisfactory', note: 'Personally reviewed this synthetic original source.', required_action: null, sources: [source] }])) } as TitleFindings;
}
export function titleChoice(artifact: string | null = titleId(8), now = Date.now()) {
  const stamp = new Date(now).toISOString();
  const resolution = { artifact_id: titleId(8), source_version: 2, verification_id: titleId(9), sha256: 'a'.repeat(64), policy_id: titleId(10), expected_sequence: 0, available_until: new Date(now + 3600000).toISOString() };
  return { ...titleScope, artifact_id: artifact, status: artifact ? 'ready_for_human_review' : 'document_required', resolution: artifact ? resolution : null,
    candidate: artifact ? { ...resolution, max_expires_at: new Date(now + 300000).toISOString(), report_policy: { max_age_seconds: 3600, max_age_days: 0, timezone: 'America/Chicago' } } : null,
    withdrawal: null, current_review: { ...titleScope, kind: 'title_findings', review_id: null, sequence: 0, status: 'not_reviewed', approval_current: false, expires_at: null, checked_at: stamp, execution_authorized: false }, checked_at: stamp, execution_authorized: false };
}
export function titleReference(now = Date.now()) { return { ...titleScope, artifact_id: titleId(8), source_version: 2, reference_type: 'native', link_id: null, status: 'available_for_review', purpose: 'title_report', sha256: 'a'.repeat(64), verification_id: titleId(9), source_created_at: new Date(now - 10000).toISOString(), checked_at: new Date(now).toISOString(), review_approved: false, execution_authorized: false }; }
