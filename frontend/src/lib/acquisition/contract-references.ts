import { z } from 'zod';
import { date, id } from './mail-content';
import { purpose, type DocumentContext } from './contract-documents';
const version = z.number().int().min(1).max(2147483647);
const reference = z.object({ workspace_id: id, contract_id: id, contract_version: version, artifact_id: id,
  source_version: version, reference_type: z.enum(['native', 'term_source', 'linked']), link_id: id.nullable(),
  status: z.enum(['reference_withdrawn', 'source_revoked', 'requires_review', 'available_for_review']), purpose,
  sha256: z.string().regex(/^[a-f0-9]{64}$/), verification_id: id.nullable(), source_created_at: date, checked_at: date,
  review_approved: z.literal(false), execution_authorized: z.literal(false) }).strict();
const page = z.object({ workspace_id: id, contract_id: id, contract_version: version, purpose,
  items: z.array(reference).max(50), next_after: id.nullable(), checked_at: date, execution_authorized: z.literal(false) }).strict();
export function parseReferences(raw: unknown, context: DocumentContext, selectedPurpose: z.infer<typeof purpose>, after: string | null = null, now = Date.now()) {
  const value = page.parse(raw), checked = Date.parse(value.checked_at);
  if (value.workspace_id !== context.workspaceId || value.contract_id !== context.contractId || value.contract_version !== context.contractVersion
    || value.purpose !== selectedPurpose || checked < now - 30000 || checked > now + 5000 || value.items.length > 20
    || (value.next_after !== null && value.items.length !== 20)) throw new Error('Current exact reference page required');
  let previous = after?.toLowerCase() ?? null;
  for (const row of value.items) {
    if (row.workspace_id !== context.workspaceId || row.contract_id !== context.contractId || row.contract_version !== context.contractVersion
      || row.purpose !== selectedPurpose || Date.parse(row.checked_at) !== checked || Date.parse(row.source_created_at) > checked
      || (previous !== null && row.artifact_id.toLowerCase() <= previous) || row.source_version > row.contract_version
      || (row.reference_type === 'native') !== (row.source_version === row.contract_version)
      || (row.reference_type === 'linked') !== (row.link_id !== null)
      || (row.status === 'reference_withdrawn' && row.reference_type !== 'linked')
      || (row.status === 'available_for_review') !== (row.verification_id !== null)) throw new Error('Original source identity or state changed');
    previous = row.artifact_id.toLowerCase();
  }
  if (value.next_after !== null && value.next_after.toLowerCase() !== previous) throw new Error('Reference cursor changed');
  return value;
}
