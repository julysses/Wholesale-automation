import { afterEach, expect, it, vi } from 'vitest';
import { checkDocumentRegistration, clearPendingDocument, documentKey, parseDocuments, readPendingDocument, savePendingDocument, type PendingDocument } from './contract-documents';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(5), contractId: id(6), contractVersion: 1 };
const pending: PendingDocument = { version: 1, context, stage: 'register', registration: { id: id(7), purpose: 'purchase_contract', expected_sha256: 'a'.repeat(64), expected_byte_size: 30, media_type: 'application/pdf', retention_policy_id: id(8), provenance_note: 'Provided by seller for contract review.' } };
afterEach(() => { sessionStorage.clear(); vi.useRealTimers(); });
it('recovers the exact property and contract after reload and prevents replacement', () => {
  savePendingDocument(sessionStorage, pending, null);
  expect(readPendingDocument(sessionStorage, id(1), id(2))).toEqual(pending);
  expect(readPendingDocument(sessionStorage, id(9), id(2))).toBeNull();
  expect(readPendingDocument(sessionStorage, id(1), id(9))).toBeNull();
  expect(() => savePendingDocument(sessionStorage, { ...pending, context: { ...context, contractId: id(9) } }, null)).toThrow();
  const uploading = savePendingDocument(sessionStorage, { ...pending, stage: 'upload' }, pending);
  expect(() => clearPendingDocument(sessionStorage, pending)).toThrow();
  clearPendingDocument(sessionStorage, uploading);
  expect(readPendingDocument(sessionStorage, id(1), id(2))).toBeNull();
});
it('preserves unreadable or foreign recovery instead of replacing it', () => {
  const key = documentKey(id(1), id(2));
  for (const raw of ['invalid', JSON.stringify({ ...pending, context: { ...context, userId: id(9) } })]) {
    sessionStorage.setItem(key, raw);
    expect(() => readPendingDocument(sessionStorage, id(1), id(2))).toThrow();
    expect(() => savePendingDocument(sessionStorage, pending, null)).toThrow();
    expect(sessionStorage.getItem(key)).toBe(raw);
  }
});
it('rejects an unrelated registration or any implied approval', () => {
  const receipt = { workspace_id: id(2), contract_id: id(6), contract_version: 1, artifact_id: id(7), retain_until: '2026-11-30T12:00:00Z', duplicate: true, bytes_verified: false, execution_authorized: false };
  expect(checkDocumentRegistration(receipt, pending)).toEqual(receipt);
  for (const patch of [{ contract_version: 2 }, { artifact_id: id(9) }, { workspace_id: id(9) }, { bytes_verified: true }, { execution_authorized: true }, { private_url: 'unexpected' }])
    expect(() => checkDocumentRegistration({ ...receipt, ...patch }, pending)).toThrow();
});
it('requires fresh scoped discovery and a real pagination boundary', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-31T12:00:00Z'));
  const page = { workspace_id: id(2), contract_id: id(6), contract_version: 1, purpose: 'purchase_contract', current_policy: null, items: [], next_after: null, checked_at: '2026-10-31T12:00:00Z', execution_authorized: false, upload_enabled: false };
  expect(parseDocuments(page, context, 'purchase_contract', null).upload_enabled).toBe(false);
  for (const patch of [{ next_after: id(7) }, { checked_at: '2026-10-31T11:59:29Z' }, { checked_at: '2026-10-31T12:00:06Z' }, { contract_version: 2 }, { purpose: 'title_report' }, { execution_authorized: true }])
    expect(() => parseDocuments({ ...page, ...patch }, context, 'purchase_contract', null)).toThrow();
});
