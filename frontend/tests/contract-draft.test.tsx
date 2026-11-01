import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractDraft } from '../src/components/acquisition/ContractDraft';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), pending: vi.fn(), fail: false, reject: false, existing: false, approved: true }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { rejectedContract = true; } }));
import { ApiError } from '../src/lib/api';
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const selected = { offer_id: id(6), lead_id: id(3), property_id: id(4) };
const record = { id: id(5), workspace_id: id(2), lead_id: id(3), deal_name: 'Saved property draft', acquisition_status: 'draft', acquisition_version: 1,
  acquisition_property_id: id(4), acquisition_owner_relationship_id: id(7), acquisition_offer_id: id(6), acquisition_offer_sequence: 2, created_by: id(1), created_at: '2026-10-31T22:00:00Z' };
beforeEach(() => {
  record.acquisition_status = 'draft'; record.acquisition_version = 1; sessionStorage.clear(); mock.fetch.mockReset(); mock.pending.mockReset(); mock.fail = false; mock.reject = false; mock.existing = false; mock.approved = true;
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (mock.reject) throw new ApiError('Rejected', 409);
      if (mock.fail) throw new Error('Lost response');
      if (path.includes('/document-links')) {
        const body = JSON.parse(init.body as string);
        return { json: async () => ({ link_id: body.id, workspace_id: id(2), contract_id: id(5), contract_version: 2, source_version: 1, artifact_id: id(32), duplicate: true, review_approved: false, execution_authorized: false }) };
      }
      if (path.endsWith('/terms')) {
        const body = JSON.parse(init.body as string);
        return { json: async () => ({ request_id: body.id, workspace_id: id(2), contract_id: id(5), version: body.expected_version + 1, status: 'draft', duplicate: true, execution_authorized: false }) };
      }
      if (path.endsWith('/transitions')) {
        const body = JSON.parse(init.body as string);
        return { json: async () => ({ workspace_id: id(2), contract_id: id(5), contract_version: body.expected_version, request_id: body.id,
          sequence: body.expected_sequence + 1, previous_status: body.expected_status, recorded_status: body.target_status,
          duplicate: true, transition_recorded: true, execution_authorized: false }) };
      }
      if (path.endsWith('/deadline-reviews')) {
        const body = JSON.parse(init.body as string);
        return { json: async () => ({ workspace_id: id(2), contract_id: id(5), contract_version: body.expected_version,
          kind: 'deadline_resolution', term: body.term, review_id: body.id, interpretation_review_id: body.original_review_id ?? body.id,
          sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
      }
      if (path.endsWith('/signature-review')) {
        const body = JSON.parse(init.body as string);
        return { json: async () => ({ workspace_id: id(2), contract_id: id(5), contract_version: 1, review_id: body.id,
          sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
      }
      if (path.includes('/reviews/')) {
        const body = JSON.parse(init.body as string);
        return { json: async () => ({ workspace_id: id(2), contract_id: id(5), contract_version: 1, kind: 'contract_review', review_id: body.id,
          sequence: body.expected_sequence + 1, status: body.status, duplicate: true, review_recorded: true, approval_current: false, execution_authorized: false }) };
      }
      mock.existing = true;
      return { json: async () => ({ deal_id: JSON.parse(init.body as string).id, version: 1, status: 'draft', duplicate: false, execution_authorized: false }) };
    }
    const value = path.endsWith('/state') ? { ...selected, workspace_id: id(2), sequence: 2, amount_approval_current: mock.approved, amount: 140000 }
      : path.endsWith('/summary') ? { id: id(3), property_id: id(4), property_address: '123 Fixture St', city: 'Dallas' }
      : path.includes('/sellers?') ? { items: [{ id: id(7), workspace_id: id(2), lead_id: id(3), property_id: id(4), owner_id: id(8), relationship: 'reported_owner', verification_status: 'unverified', seller: { display_name: 'Synthetic Seller' } }], next_after: null, ownership_verified: false, execution_authorized: false }
      : { items: mock.existing ? [record] : [], next_after: null, execution_authorized: false };
    return { json: async () => value };
  });
});
function open(selection: typeof selected | null = selected) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ContractDraft userId={id(1)} workspace={id(2)} selected={selection} onPending={mock.pending} /></QueryClientProvider>);
}
async function fill() {
  await screen.findByRole('option', { name: /Synthetic Seller/ });
  fireEvent.change(screen.getByLabelText('Seller relationship'), { target: { value: id(7) } });
  fireEvent.change(screen.getByLabelText('Draft name'), { target: { value: 'Property draft' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft for review' })).toBeEnabled());
}
const posts = () => mock.fetch.mock.calls.filter(call => call[1]?.method === 'POST');
it('carries property, amount and reported seller into a nonbinding draft', async () => {
  open(); await fill(); expect(screen.getByText('123 Fixture St, Dallas')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft for review' }));
  await screen.findByText(/Draft saved for review/); expect(posts()).toHaveLength(1);
  expect(JSON.parse(posts()[0][1].body)).toMatchObject({ offer_id: id(6), offer_sequence: 2, owner_relationship_id: id(7) });
  expect(sessionStorage.length).toBe(0); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('recovers the exact request after reload even without a selected proposal', async () => {
  mock.fail = true; const view = open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save draft for review' }));
  await screen.findByText(/Save is unconfirmed/); expect(mock.pending).toHaveBeenLastCalledWith(true); view.unmount();
  mock.fail = false; mock.approved = false; open(null);
  fireEvent.click(await screen.findByRole('button', { name: 'Retry same draft' }));
  await screen.findByText(/Draft saved for review/); expect(posts()).toHaveLength(2); expect(posts()[0][1].body).toBe(posts()[1][1].body);
});
it('retains an uncertain request when a later retry is rejected', async () => {
  mock.fail = true; open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save draft for review' }));
  await screen.findByText(/Save is unconfirmed/); const original = sessionStorage.getItem(sessionStorage.key(0)!);
  mock.reject = true; fireEvent.click(screen.getByRole('button', { name: 'Retry same draft' }));
  await waitFor(() => expect(posts()).toHaveLength(2)); await waitFor(() => expect(screen.getByRole('button', { name: 'Retry same draft' })).toBeEnabled());
  expect(sessionStorage.getItem(sessionStorage.key(0)!)).toBe(original);
});
it('unlocks a first attempt explicitly rejected by the database', async () => {
  mock.reject = true; open(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save draft for review' }));
  await screen.findByText(/The draft was not saved/); expect(sessionStorage.length).toBe(0);
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('shows an existing draft after reload and prevents another save', async () => {
  mock.existing = true; open(); await screen.findByText('Existing draft: Saved property draft');
  expect(screen.getByRole('button', { name: 'Draft saved' })).toBeDisabled(); expect(posts()).toHaveLength(0);
});
it('rechecks an amount approval immediately before saving', async () => {
  open(); await fill(); mock.approved = false; fireEvent.click(screen.getByRole('button', { name: 'Save draft for review' }));
  await screen.findByText(/The amount review changed/); expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});
it('restores document context without a selected proposal and holds navigation', async () => {
  mock.existing = true;
  sessionStorage.setItem(`wholesale.contract.document:v1:${id(1)}:${id(2)}`, JSON.stringify({ version: 1,
    context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 1 }, stage: 'upload',
    registration: { id: id(9), purpose: 'purchase_contract', expected_sha256: 'a'.repeat(64), expected_byte_size: 20, media_type: 'text/plain', retention_policy_id: id(8), provenance_note: 'Original seller document for review.' } }));
  open(null);
  await screen.findByText('123 Fixture St, Dallas');
  await screen.findByText('Recover the saved document');
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole('button', { name: 'Draft saved' })).toBeDisabled();
  expect(screen.getByLabelText('Document type')).toBeDisabled();
  expect(posts()).toHaveLength(0);
});


it('restores pending human review context after reload without a selected proposal', async () => {
  const { preserveReview } = await import('../src/lib/acquisition/contract-review-request');
  preserveReview(sessionStorage, { version: 1, context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 1 }, kind: 'contract_review', request: { id: id(20), expected_sequence: 0, status: 'approved', artifact_id: id(21), verification_id: id(22), policy_id: id(23), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true, note: 'Synthetic original human review preserved for recovery.' } });
  mock.existing = true; open(null);
  await screen.findByText('Recover the saved review');
  expect(await screen.findByText('123 Fixture St, Dallas')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Draft saved' })).toBeDisabled();
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true));
  expect(posts()).toHaveLength(0);
});

it('recovers the exact historical review after the canonical contract advances', async () => {
  const { preserveReview } = await import('../src/lib/acquisition/contract-review-request');
  const request = { id: id(20), expected_sequence: 0, status: 'approved' as const, artifact_id: id(21), verification_id: id(22), policy_id: id(23), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true, note: 'Original review request retained after version advancement.' };
  preserveReview(sessionStorage, { version: 1, context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 1 }, kind: 'contract_review', request });
  record.acquisition_version = 2; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry saved review' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved review' }));
  await waitFor(() => expect(sessionStorage.length).toBe(0));
  expect(posts()).toHaveLength(1); expect(posts()[0][0]).toContain('/versions/1/reviews/contract_review');
  expect(JSON.parse(posts()[0][1].body)).toEqual(request);
  expect(screen.getByText('Current contract version 2.')).toBeVisible();
  await waitFor(() => expect(mock.fetch.mock.calls.some(([path]) => path.includes('/versions/2/references?'))).toBe(true));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});


it('recovers historical terms without a selected offer and returns to the current version', async () => {
  const { preserveTerms, emptyTerms } = await import('../src/lib/acquisition/contract-terms');
  const request = { id: id(30), expected_version: 1, terms: { ...emptyTerms(), note: 'Original unknown terms retained across a lost save reply.' } };
  preserveTerms(sessionStorage, { version: 1, context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 1 }, request });
  record.acquisition_version = 2; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry saved terms' })).toBeEnabled());
  expect(screen.getByLabelText('Document type')).toBeDisabled(); expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved terms' }));
  await waitFor(() => expect(sessionStorage.length).toBe(0));
  expect(posts()).toHaveLength(1); expect(posts()[0][0]).toMatch(/\/contracts\/[^/]+\/terms$/);
  expect(JSON.parse(posts()[0][1].body)).toEqual(request);
  expect(screen.getByText('Current contract version 2.')).toBeVisible();
  await waitFor(() => expect(mock.fetch.mock.calls.some(([path]) => path.includes('/versions/2/references?'))).toBe(true));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('blocks conflicting saved term and document requests instead of choosing one', async () => {
  const { preserveTerms, emptyTerms } = await import('../src/lib/acquisition/contract-terms');
  const context = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 1 };
  preserveTerms(sessionStorage, { version: 1, context, request: { id: id(30), expected_version: 1, terms: { ...emptyTerms(), note: 'Original terms retained across a lost save reply.' } } });
  sessionStorage.setItem(`wholesale.contract.document:v1:${id(1)}:${id(2)}`, JSON.stringify({ version: 1, context, stage: 'upload',
    registration: { id: id(9), purpose: 'purchase_contract', expected_sha256: 'a'.repeat(64), expected_byte_size: 20, media_type: 'text/plain', retention_policy_id: id(8), provenance_note: 'Original seller document for review.' } }));
  open(null); expect(screen.getByRole('alert')).toHaveTextContent('Reconcile the existing request');
  expect(mock.fetch).not.toHaveBeenCalled(); expect(mock.pending).toHaveBeenLastCalledWith(true); expect(sessionStorage.length).toBe(2);
});

it('recovers an original reference after the canonical version advances without a selected proposal', async () => {
  const { preserveLink } = await import('../src/lib/acquisition/contract-links');
  const request = { id: id(31), source_version: 1, artifact_id: id(32), verification_id: id(33), sha256: 'a'.repeat(64), note: 'Original title document retained for the prior contract version.' };
  preserveLink(sessionStorage, { version: 1, kind: 'link', context: { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 2 }, request });
  record.acquisition_version = 3; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry saved reference' })).toBeEnabled());
  expect(screen.getByLabelText('Document type')).toBeDisabled(); expect(screen.getByRole('button', { name: 'Edit draft terms' })).toBeDisabled();
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved reference' })); await waitFor(() => expect(sessionStorage.length).toBe(0));
  expect(posts()).toHaveLength(1); expect(posts()[0][0]).toContain('/versions/2/document-links'); expect(JSON.parse(posts()[0][1].body)).toEqual(request);
  expect(screen.getByText('Current contract version 3.')).toBeVisible(); await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});

const signatureContext = { userId: id(1), workspaceId: id(2), leadId: id(3), propertyId: id(4), offerId: id(6), contractId: id(5), contractVersion: 1 };
const signatureRequest = { id: id(40), expected_sequence: 0, status: 'approved' as const, basis_review_id: id(41), policy_id: id(42), expires_at: '2020-01-01T00:00:00Z', personally_reviewed: true, note: 'Original signature decision preserved after version advancement.' };
it('recovers a historical signature decision without a selected proposal and restores the current version', async () => {
  const { preserveSignature } = await import('../src/lib/acquisition/signature-review');
  preserveSignature(sessionStorage, { version: 1, context: signatureContext, request: signatureRequest });
  record.acquisition_version = 2; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry saved signature review' })).toBeEnabled());
  expect(screen.getByLabelText('Document type')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Edit draft terms' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Refresh draft information' })).toBeDisabled();
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved signature review' }));
  await waitFor(() => expect(sessionStorage.length).toBe(0));
  expect(posts()).toHaveLength(1); expect(posts()[0][0]).toContain('/versions/1/signature-review');
  expect(JSON.parse(posts()[0][1].body)).toEqual(signatureRequest);
  expect(screen.getByText('Current contract version 2.')).toBeVisible();
  await waitFor(() => expect(mock.fetch.mock.calls.some(([path]) => path.includes('/versions/2/references?'))).toBe(true));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('holds adjacent edits while signature review is open and releases unsaved edits on close', async () => {
  mock.existing = true; open();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Open signature-release review' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Open signature-release review' }));
  expect(screen.getByLabelText('Document type')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Edit draft terms' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Refresh draft information' })).toBeDisabled();
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Close without saving' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
  expect(screen.getByRole('button', { name: 'Refresh terms' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Refresh draft information' })).toBeEnabled();
  expect(posts()).toHaveLength(0); expect(sessionStorage.length).toBe(0);
});
it('preserves conflicting signature and terms recoveries without selecting either', async () => {
  const { preserveSignature } = await import('../src/lib/acquisition/signature-review');
  const { preserveTerms, emptyTerms } = await import('../src/lib/acquisition/contract-terms');
  preserveSignature(sessionStorage, { version: 1, context: signatureContext, request: signatureRequest });
  preserveTerms(sessionStorage, { version: 1, context: signatureContext, request: { id: id(30), expected_version: 1, terms: { ...emptyTerms(), note: 'Original terms retained across a lost save reply.' } } });
  open(null); expect(screen.getByRole('alert')).toHaveTextContent('Reconcile the existing request');
  expect(mock.fetch).not.toHaveBeenCalled(); expect(mock.pending).toHaveBeenLastCalledWith(true); expect(sessionStorage.length).toBe(2);
});

it('keeps a contract awaiting signature visible and enables document capture while holding draft terms', async () => {
  record.acquisition_status = 'pending_signature'; mock.existing = true; open();
  await screen.findByText('Awaiting signature. This status does not confirm that an agreement was sent or signed.');
  expect(screen.getByRole('button', { name: 'Draft saved' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Edit draft terms' })).toBeDisabled();
  expect(screen.getByLabelText('Document type')).toBeEnabled();
  expect(screen.getByText('Next: confirm the signed document')).toBeVisible();
  expect(posts()).toHaveLength(0);
});

const transitionRequest = { id: id(50), expected_version: 1, expected_sequence: 0, expected_status: 'draft' as const, target_status: 'pending_signature' as const, reason: 'Original reviewed status handoff kept after a lost response.' };
it.each([
  ['draft', 'pending_signature', 0], ['pending_signature', 'executed', 1], ['executed', 'title_review', 2],
] as const)('recovers committed %s → %s after reload without a selected proposal', async (expected_status, target_status, expected_sequence) => {
  const original = { ...transitionRequest, expected_status, target_status, expected_sequence };
  const { preserveTransition } = await import('../src/lib/acquisition/contract-transition');
  preserveTransition(sessionStorage, { version: 1, context: signatureContext, request: original });
  record.acquisition_status = target_status; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Retry saved status change' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'Open signature-release review' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Refresh draft information' })).toBeDisabled();
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Retry saved status change' }));
  await waitFor(() => expect(sessionStorage.length).toBe(0));
  expect(posts()).toHaveLength(1); expect(posts()[0][0]).toMatch(/\/contracts\/[^/]+\/transitions$/);
  expect(JSON.parse(posts()[0][1].body)).toEqual(original);
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
});
it('holds sibling signature and draft actions during unsaved status review', async () => {
  mock.existing = true; open();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review next contract status' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Review next contract status' }));
  expect(screen.getByRole('button', { name: 'Open signature-release review' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Refresh draft information' })).toBeDisabled();
  expect(mock.pending).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole('button', { name: 'Close status review without saving' }));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
  expect(screen.getByRole('button', { name: 'Open signature-release review' })).toBeEnabled();
  expect(posts()).toHaveLength(0);
});
it('retains conflicting signature and status requests without selecting either', async () => {
  const { preserveTransition } = await import('../src/lib/acquisition/contract-transition');
  const { preserveSignature } = await import('../src/lib/acquisition/signature-review');
  preserveTransition(sessionStorage, { version: 1, context: signatureContext, request: transitionRequest });
  preserveSignature(sessionStorage, { version: 1, context: signatureContext, request: signatureRequest });
  open(null); expect(screen.getByRole('alert')).toHaveTextContent('Reconcile the existing request');
  expect(mock.fetch).not.toHaveBeenCalled(); expect(mock.pending).toHaveBeenLastCalledWith(true); expect(sessionStorage.length).toBe(2);
});

it('holds adjacent actions and navigation throughout an open execution review', async () => {
  record.acquisition_status = 'pending_signature'; mock.existing = true; open();
  await waitFor(() => expect(screen.getByText('Open execution review')).toBeEnabled());
  fireEvent.click(screen.getByText('Open execution review'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true));
  expect(screen.getByText('Refresh draft information')).toBeDisabled();
  expect(screen.getByLabelText('Document type')).toBeDisabled();
  expect(screen.getByText('Open signature-release review')).toBeDisabled();
  fireEvent.click(screen.getByText('Close without saving'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(false));
  expect(screen.getByLabelText('Document type')).toBeEnabled(); expect(posts()).toHaveLength(0);
});
it('retains the original execution target with no selection and a newer contract version', async () => {
  const { preserveExecution } = await import('../src/lib/acquisition/execution-review');
  preserveExecution(sessionStorage, { version: 1, context: signatureContext, request: { id: id(80), expected_version: 1, expected_sequence: 1, status: 'withdrawn', artifact_id: id(81), verification_id: id(82), policy_id: id(83), expires_at: null, personally_reviewed: false, findings: null, note: 'Original review withdrawal retained after uncertain save.' } });
  record.acquisition_version = 2; record.acquisition_status = 'pending_signature'; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByText('Retry saved execution review')).toBeEnabled());
  expect(screen.getByText(/Original contract version 1/)).toBeVisible();
  expect(screen.getByText('Refresh draft information')).toBeDisabled();
  expect(mock.pending).toHaveBeenLastCalledWith(true); expect(sessionStorage.length).toBe(1);
});


it('shows executed history without reopening draft edits or document capture', async () => {
  record.acquisition_status = 'executed'; mock.existing = true; open();
  await screen.findByText('Executed contract: Saved property draft');
  expect(screen.getByText(/Execution has been recorded/)).toBeVisible();
  expect(screen.getByText('Edit draft terms')).toBeDisabled();
  expect(screen.getByLabelText('Document type')).toBeDisabled();
  expect(screen.getByText('Open signature-release review')).toBeDisabled();
  expect(screen.getByText('Draft saved')).toBeDisabled(); expect(posts()).toHaveLength(0);
});

const deadlineRequest = { id: id(90), expected_version: 1, expected_sequence: 4, status: 'withdrawn' as const,
  artifact_id: id(91), verification_id: id(92), policy_id: id(93), expires_at: null, personally_reviewed: false,
  note: 'Withdraw the original date interpretation after uncertain reply.', term: 'closing_deadline' as const, resolution: null, original_review_id: id(94) };
it('recovers original date-review version without a selection and restores the current context', async () => {
  const { preserveDeadline } = await import('../src/lib/acquisition/deadline-review');
  preserveDeadline(sessionStorage, { version: 1, context: signatureContext, request: deadlineRequest });
  record.acquisition_version = 2; record.acquisition_status = 'pending_signature'; mock.existing = true; open(null);
  await waitFor(() => expect(screen.getByText('Retry saved date review')).toBeEnabled());
  expect(screen.getByText('Open execution review')).toBeDisabled();
  fireEvent.click(screen.getByText('Retry saved date review')); await waitFor(() => expect(sessionStorage.length).toBe(0));
  expect(posts()).toHaveLength(1); expect(posts()[0][0]).toContain('/versions/1/deadline-reviews'); expect(JSON.parse(posts()[0][1].body)).toEqual(deadlineRequest);
  await waitFor(() => expect(screen.getByText('Open date review')).toBeEnabled());
});
it('holds execution and navigation while date review is open', async () => {
  record.acquisition_status = 'pending_signature'; mock.existing = true; open();
  await waitFor(() => expect(screen.getByText('Open date review')).toBeEnabled()); fireEvent.click(screen.getByText('Open date review'));
  await waitFor(() => expect(mock.pending).toHaveBeenLastCalledWith(true));
  expect(screen.getByText('Open execution review')).toBeDisabled(); expect(screen.getByText('Refresh draft information')).toBeDisabled();
  fireEvent.click(screen.getByText('Close without saving')); await waitFor(() => expect(screen.getByText('Open execution review')).toBeEnabled());
});
it('holds conflicting date and execution recovery requests without selecting either', async () => {
  const { preserveDeadline } = await import('../src/lib/acquisition/deadline-review');
  const { preserveExecution } = await import('../src/lib/acquisition/execution-review');
  preserveDeadline(sessionStorage, { version: 1, context: signatureContext, request: deadlineRequest });
  preserveExecution(sessionStorage, { version: 1, context: signatureContext, request: { id: id(95), expected_version: 1, expected_sequence: 4, status: 'withdrawn', artifact_id: id(91), verification_id: id(92), policy_id: id(93), expires_at: null, personally_reviewed: false, note: deadlineRequest.note, findings: null } });
  open(null); expect(screen.getByRole('alert')).toHaveTextContent('Reconcile'); expect(mock.fetch).not.toHaveBeenCalled(); expect(sessionStorage.length).toBe(2);
});

it('keeps title-review contracts visible without claiming clearance or enabling signing', async () => {
  record.acquisition_status = 'title_review'; mock.existing = true; open();
  await screen.findByText('Title review in progress: Saved property draft');
  expect(screen.getByLabelText('Document type')).toBeEnabled();
  expect(screen.getByLabelText('Document type')).toHaveValue('title_report');
  expect(screen.getByRole('heading', { name: 'Next: verify the title evidence' })).toBeVisible();
  expect(screen.getByText(/Title review is underway/)).toHaveTextContent('does not confirm clear title');
  expect(screen.getByText('Open signature-release review')).toBeDisabled();
  expect(screen.getByText('Open execution review')).toBeEnabled();
  expect(screen.getByText('Open date review')).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Draft saved' })).toBeDisabled();
});
