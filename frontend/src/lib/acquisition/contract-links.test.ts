import { beforeEach, expect, it } from 'vitest';
import { clearConfirmedLink, clearRejectedLink, linkKey, preserveLink, readPendingLink, type PendingLink } from './contract-links';
import { emptyTerms, parseContractVersions } from './contract-terms';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const context = { userId: id(1), workspaceId: id(2), contractId: id(3), contractVersion: 2, leadId: id(4), propertyId: id(5), offerId: id(6) };
const link = (): PendingLink => ({ version: 1, kind: 'link', context, request: { id: id(7), source_version: 1, artifact_id: id(8), verification_id: id(9), sha256: 'a'.repeat(64), note: 'Original title record supports the current contract version.' } });
const receipt = () => ({ link_id: id(7), workspace_id: id(2), contract_id: id(3), contract_version: 2, source_version: 1, artifact_id: id(8), duplicate: true, review_approved: false, execution_authorized: false });
beforeEach(() => sessionStorage.clear());
it('preserves exact original link request and rejects competitors and future sources', () => {
  const saved = preserveLink(sessionStorage, link()); expect(readPendingLink(sessionStorage, id(1), id(2))).toEqual(saved);
  expect(() => preserveLink(sessionStorage, { ...link(), context: { ...context, contractVersion: 1 } })).toThrow();
  const candidate = link(); if (candidate.kind === 'link') candidate.request.source_version = 2;
  expect(() => preserveLink(sessionStorage, candidate)).toThrow();
  expect(() => preserveLink(sessionStorage, { version: 1, kind: 'withdraw', context, linkId: id(7), request: { id: id(10), reason: 'This link must be withdrawn after the terms changed.' } })).toThrow();
});
it('keeps uncertain link requests on mismatched receipts or later rejection', () => {
  const saved = preserveLink(sessionStorage, link());
  for (const patch of [{ link_id: id(10) }, { workspace_id: id(10) }, { contract_version: 3 }, { source_version: 2 }, { artifact_id: id(10) }, { review_approved: true }, { execution_authorized: true }]) {
    expect(() => clearConfirmedLink(sessionStorage, saved, { ...receipt(), ...patch })).toThrow(); expect(sessionStorage.length).toBe(1);
  }
  expect(() => clearRejectedLink(sessionStorage, saved, true, false)).toThrow(); clearConfirmedLink(sessionStorage, saved, receipt()); expect(sessionStorage.length).toBe(0);
});
it('withdrawal requires exact target link and request receipt', () => {
  const saved = preserveLink(sessionStorage, { version: 1, kind: 'withdraw', context, linkId: id(7), request: { id: id(10), reason: 'This reference is no longer applicable to the contract.' } });
  const result = { workspace_id: id(2), contract_id: id(3), contract_version: 2, link_id: id(7), revocation_id: id(10), duplicate: true, execution_authorized: false };
  expect(() => clearConfirmedLink(sessionStorage, saved, { ...result, link_id: id(8) })).toThrow();
  clearConfirmedLink(sessionStorage, saved, result); expect(sessionStorage.length).toBe(0);
});
it('blocks malformed and foreign saved requests', () => {
  sessionStorage.setItem(linkKey(id(1), id(2)), '{invalid'); expect(() => readPendingLink(sessionStorage, id(1), id(2))).toThrow();
  sessionStorage.setItem(linkKey(id(1), id(2)), JSON.stringify({ ...link(), context: { ...context, userId: id(10) } })); expect(() => readPendingLink(sessionStorage, id(1), id(2))).toThrow();
});
it('validates paged version choices without cross-contract data or silent future versions', () => {
  const row = (n: number) => ({ id: id(n + 20), workspace_id: id(2), deal_id: id(3), version: n, status: 'draft', previous_version: n === 1 ? null : n - 1,
    terms: n === 1 ? null : { ...emptyTerms(), note: 'Unknown terms retained as an explicit draft.' }, actor_id: id(1), created_at: '2026-10-31T22:00:00Z' });
  const page = { workspace_id: id(2), contract_id: id(3), items: Array.from({ length: 20 }, (_, i) => row(i + 1)), next_after: 20, execution_authorized: false };
  expect(parseContractVersions(page, { ...context, contractVersion: 21 }).items).toHaveLength(20);
  expect(() => parseContractVersions(page, context)).toThrow();
  expect(() => parseContractVersions({ ...page, next_after: 19 }, { ...context, contractVersion: 21 })).toThrow();
  expect(() => parseContractVersions({ ...page, items: [row(1), row(1)], next_after: null }, context)).toThrow();
  expect(() => parseContractVersions({ ...page, items: [{ ...row(1), deal_id: id(10) }], next_after: null }, context)).toThrow();
});
