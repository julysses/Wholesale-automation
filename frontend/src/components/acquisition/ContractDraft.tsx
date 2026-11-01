import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { SignatureReviewForm } from './SignatureReviewForm';
import { readPendingSignature } from '@/lib/acquisition/signature-review';
import { ContractLinksForm } from './ContractLinksForm';
import { readPendingLink } from '@/lib/acquisition/contract-links';
import { ContractTermsForm } from './ContractTermsForm';
import { readPendingTerms } from '@/lib/acquisition/contract-terms';
import { ContractReviewForm } from './ContractReviewForm';
import { readPendingReview } from '@/lib/acquisition/contract-review-request';
import { ContractDocuments } from './ContractDocuments';
import { readPendingDocument, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { apiFetch, ApiError } from '@/lib/api';
import { clearConfirmedContractDraft, clearRejectedContractDraft, readExistingContractDrafts, contractDraftRequestSchema, preserveContractDraft, readContractDraft, readContractSellers,
  type PendingContractDraft } from '@/lib/contractDraftRequest';

const button = 'rounded-lg border px-4 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'w-full rounded-lg border border-gray-300 p-2 bg-white';
const offerState = z.object({ offer_id: z.string(), workspace_id: z.string(), lead_id: z.string(), property_id: z.string(),
  sequence: z.number().int().positive(), amount_approval_current: z.boolean(), amount: z.number().finite().positive() });
type Selection = { offer_id: string; lead_id: string; property_id: string };
async function read(path: string, signal?: AbortSignal): Promise<unknown> { return (await apiFetch(path, { signal, cache: 'no-store' })).json(); }

export function ContractDraft({ userId, workspace, selected, onPending }: {
  userId: string; workspace: string; selected: Selection | null; onPending: (value: boolean) => void;
}) {
  const [initial] = useState(() => { try { return { request: readContractDraft(sessionStorage, userId, workspace), invalid: false }; }
    catch { return { request: null, invalid: true }; } });
  const [documentInitial] = useState(() => { try { return { saved: readPendingDocument(sessionStorage, userId, workspace), invalid: false }; }
    catch { return { saved: null, invalid: true }; } });
  const [reviewInitial] = useState(() => { try { return { saved: readPendingReview(sessionStorage, userId, workspace), invalid: false }; }
    catch { return { saved: null, invalid: true }; } });
  const [signatureInitial] = useState(() => { try { return { saved: readPendingSignature(sessionStorage, userId, workspace), invalid: false }; }
    catch { return { saved: null, invalid: true }; } });
  const [signaturePending, setSignaturePending] = useState(!!signatureInitial.saved);
  const [signatureRecoveryContext, setSignatureRecoveryContext] = useState<DocumentContext | null>(signatureInitial.saved?.context ?? null);
  const handleSignaturePending = useCallback((value: boolean) => {
    setSignaturePending(value);
    if (!value) { setSignatureRecoveryContext(null); return; }
    try {
      const saved = readPendingSignature(sessionStorage, userId, workspace);
      if (saved) setSignatureRecoveryContext(previous => previous && Object.entries(saved.context).every(([key, field]) => previous[key as keyof DocumentContext] === field) ? previous : saved.context);
    } catch { /* The signature editor keeps unsafe recovery held. */ }
  }, [userId, workspace]);
  const [linkInitial] = useState(() => { try { return { saved: readPendingLink(sessionStorage, userId, workspace), invalid: false }; }
    catch { return { saved: null, invalid: true }; } });
  const [linkPending, setLinkPending] = useState(!!linkInitial.saved);
  const [linkRecoveryContext, setLinkRecoveryContext] = useState<DocumentContext | null>(linkInitial.saved?.context ?? null);
  const handleLinkPending = useCallback((value: boolean) => {
    setLinkPending(value);
    if (!value) { setLinkRecoveryContext(null); return; }
    try {
      const saved = readPendingLink(sessionStorage, userId, workspace);
      if (saved) setLinkRecoveryContext(previous => previous && Object.entries(saved.context).every(([key, field]) => previous[key as keyof DocumentContext] === field) ? previous : saved.context);
    } catch { /* The reference editor keeps unsafe recovery held. */ }
  }, [userId, workspace]);
  const [termsInitial] = useState(() => { try { return { saved: readPendingTerms(sessionStorage, userId, workspace), invalid: false }; }
    catch { return { saved: null, invalid: true }; } });
  const [termsPending, setTermsPending] = useState(!!termsInitial.saved);
  const [termsRecoveryContext, setTermsRecoveryContext] = useState<DocumentContext | null>(termsInitial.saved?.context ?? null);
  const handleTermsPending = useCallback((value: boolean) => {
    setTermsPending(value);
    if (!value) { setTermsRecoveryContext(null); return; }
    try {
      const saved = readPendingTerms(sessionStorage, userId, workspace);
      if (saved) setTermsRecoveryContext(previous => previous && Object.entries(saved.context).every(([key, field]) => previous[key as keyof DocumentContext] === field) ? previous : saved.context);
    } catch { /* The terms editor preserves its blocked recovery state. */ }
  }, [userId, workspace]);
  const [reviewPending, setReviewPending] = useState(!!reviewInitial.saved);
  const [reviewRecoveryContext, setReviewRecoveryContext] = useState<DocumentContext | null>(reviewInitial.saved?.context ?? null);
  const handleReviewPending = useCallback((value: boolean) => {
    setReviewPending(value);
    if (!value) { setReviewRecoveryContext(null); return; }
    try {
      const saved = readPendingReview(sessionStorage, userId, workspace);
      if (saved) setReviewRecoveryContext(previous => previous && Object.entries(saved.context).every(([key, field]) => previous[key as keyof DocumentContext] === field) ? previous : saved.context);
    } catch { /* The review editor preserves its blocked recovery state. */ }
  }, [userId, workspace]);
  const [documentPending, setDocumentPending] = useState(!!documentInitial.saved);
  const invalid = initial.invalid || documentInitial.invalid || reviewInitial.invalid || termsInitial.invalid || linkInitial.invalid || signatureInitial.invalid
    || [initial.request, documentInitial.saved, reviewInitial.saved, termsInitial.saved, linkInitial.saved, signatureInitial.saved].filter(Boolean).length > 1;
  const [pending, setPending] = useState<PendingContractDraft | null>(initial.request);
  const [relationship, setRelationship] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [savedOffer, setSavedOffer] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const lock = useRef(false);
  const context = pending?.context ?? signatureInitial.saved?.context ?? linkInitial.saved?.context ?? termsInitial.saved?.context ?? reviewInitial.saved?.context ?? documentInitial.saved?.context ?? (selected ? { userId, workspaceId: workspace, leadId: selected.lead_id, propertyId: selected.property_id } : null);
  const offerId = pending?.request.offer_id ?? signatureInitial.saved?.context.offerId ?? linkInitial.saved?.context.offerId ?? termsInitial.saved?.context.offerId ?? reviewInitial.saved?.context.offerId ?? documentInitial.saved?.context.offerId ?? selected?.offer_id;
  const after = cursors.at(-1) ?? null;
  const base = `/api/acquisition/workspaces/${workspace}`;
  useEffect(() => { onPending(busy || !!pending || invalid || documentPending || reviewPending || termsPending || linkPending || signaturePending); }, [busy, pending, invalid, documentPending, reviewPending, termsPending, linkPending, signaturePending, onPending]);
  const state = useQuery({ queryKey: ['contract-draft', userId, workspace, offerId, 'state'], enabled: !!offerId && !invalid,
    queryFn: async ({ signal }) => {
      const value = offerState.parse(await read(`${base}/offers/${offerId}/state`, signal));
      if (value.offer_id !== offerId || value.workspace_id !== workspace || value.lead_id !== context?.leadId || value.property_id !== context?.propertyId) throw new Error('Selected offer identity changed.');
      return value;
    }, retry: false, gcTime: 0, staleTime: 0 });
  const sellers = useQuery({ queryKey: ['contract-draft', userId, workspace, context?.leadId, context?.propertyId, after, 'sellers'],
    enabled: !!context && !invalid && !pending,
    queryFn: async ({ signal }) => readContractSellers(await read(`${base}/contracts/drafts/sellers?lead_id=${context!.leadId}&property_id=${context!.propertyId}&limit=20${after ? `&after=${after}` : ''}`, signal), context!, after),
    retry: false, gcTime: 0, staleTime: 0 });
  const property = useQuery({ queryKey: ['contract-draft', userId, workspace, context?.leadId, context?.propertyId, 'property'], enabled: !!context && !invalid,
    queryFn: async ({ signal }) => {
      const value = z.object({ id: z.string(), property_id: z.string(), property_address: z.string().min(1), city: z.string().nullable() }).parse(await read(`${base}/leads/${context!.leadId}/summary`, signal));
      if (value.id !== context!.leadId || value.property_id !== context!.propertyId) throw new Error('Property identity changed.');
      return value;
    }, retry: false, gcTime: 0, staleTime: 0 });
  const history = useQuery({ queryKey: ['contract-draft', userId, workspace, context?.leadId, context?.propertyId, 'history'],
    refetchOnWindowFocus: false, refetchOnReconnect: false,
    enabled: !!context && !invalid,
    queryFn: async ({ signal }) => readExistingContractDrafts(await read(`${base}/contracts/drafts?lead_id=${context!.leadId}&limit=50`, signal), context!),
    retry: false, gcTime: 0, staleTime: 0 });
  const refreshHistory = history.refetch;
  const handleTermsSaved = useCallback(() => { void refreshHistory(); }, [refreshHistory]);
  const existing = history.data?.items[0];
  const documentTarget: DocumentContext | null = (signaturePending ? signatureRecoveryContext : null) ?? (linkPending ? linkRecoveryContext : null) ?? (termsPending ? termsRecoveryContext : null) ?? (reviewPending ? reviewRecoveryContext : null) ?? (documentPending ? documentInitial.saved?.context : null) ?? (existing && context ? {
    userId, workspaceId: workspace, leadId: context.leadId, propertyId: context.propertyId,
    offerId: existing.acquisition_offer_id, contractId: existing.id, contractVersion: existing.acquisition_version,
  } : null);
  const documentIdentityReady = !!documentTarget && !!existing && existing.id === documentTarget.contractId
    && existing.acquisition_offer_id === documentTarget.offerId && !history.isError && !history.isFetching && !!property.data && !property.isError;
  const documentContextReady = documentIdentityReady && existing!.acquisition_version === documentTarget!.contractVersion;
  const preparationReady = documentContextReady && existing!.acquisition_status === 'draft';
  const reviewContextReady = preparationReady || (documentIdentityReady && reviewPending && !!reviewRecoveryContext
    && existing!.acquisition_version >= reviewRecoveryContext.contractVersion);
  const termsContextReady = preparationReady || (documentIdentityReady && termsPending && !!termsRecoveryContext
    && existing!.acquisition_version >= termsRecoveryContext.contractVersion);
  const linkContextReady = preparationReady || (documentIdentityReady && linkPending && !!linkRecoveryContext
    && existing!.acquisition_version >= linkRecoveryContext.contractVersion);
  const signatureContextReady = documentContextReady || (documentIdentityReady && signaturePending && !!signatureRecoveryContext
    && existing!.acquisition_version >= signatureRecoveryContext.contractVersion);
  const currentSeller = sellers.data?.items.find(row => row.id === relationship);
  const canSave = !signaturePending && !linkPending && !termsPending && !documentPending && !reviewPending && !!context && !!currentSeller && !!state.data?.amount_approval_current && !state.isError && !sellers.isError && !property.isError
    && !!property.data && !!history.data && !history.isError && !existing && !!name.trim()
    && contractDraftRequestSchema.shape.name.safeParse(name.trim()).success && ![state, sellers, property, history].some(query => query.isFetching) && savedOffer !== offerId;

  async function save() {
    if (lock.current || invalid || (!pending && !canSave)) return;
    lock.current = true; setBusy(true); setMessage('');
    const firstAttempt = pending === null;
    let request = pending;
    try {
      if (!request) {
        const fresh = offerState.parse(await read(`${base}/offers/${offerId}/state`));
        if (!context || fresh.offer_id !== offerId || fresh.workspace_id !== workspace || fresh.lead_id !== context.leadId
          || fresh.property_id !== context.propertyId || !fresh.amount_approval_current || fresh.sequence !== state.data?.sequence) {
          throw new Error('The amount review changed. Refresh before preparing a draft.');
        }
        request = preserveContractDraft(sessionStorage, { version: 1, context, savedAt: new Date().toISOString(),
          request: { id: crypto.randomUUID(), offer_id: fresh.offer_id, offer_sequence: fresh.sequence, owner_relationship_id: relationship, name: name.trim() } });
        setPending(request);
      }
      const response = await apiFetch(`${base}/contracts/drafts`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request.request), signal: AbortSignal.timeout(30000) });
      clearConfirmedContractDraft(sessionStorage, request, await response.json());
      setPending(null); setSavedOffer(request.request.offer_id); void history.refetch();
      setMessage('Draft saved for review. No agreement was signed or sent. Document and title review are still required.');
    } catch (error) {
      if (request && firstAttempt && error instanceof ApiError && error.rejectedContract) {
        try {
          clearRejectedContractDraft(sessionStorage, request, true, true);
          setPending(null); void history.refetch(); void state.refetch();
          setMessage('The draft was not saved. Refresh the review information and resolve the current restriction before trying again.');
          return;
        } catch { /* Preserve the recovery hold if browser storage changed. */ }
      }
      setMessage(request ? 'Save is unconfirmed. Keep this request and retry it to avoid a second draft. If access changed, restore access before retrying.'
        : error instanceof Error ? error.message : 'Draft preparation is unavailable. No save was sent.');
    } finally { lock.current = false; setBusy(false); }
  }

  return <section aria-label="Contract draft preparation" className="rounded-xl border bg-white p-5 space-y-4 text-[#1B3A5C]">
    <p className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm">Prepare a review record from the selected proposal. A recorded seller relationship is not verified ownership, and a saved draft is not a signed contract.</p>
    {invalid ? <p role="alert">The saved contract or document request could not be read. Reconcile the existing request before starting another.</p> : !context ? <p>Select a proposal in step 4 to carry its property and reviewed amount into this step.</p> : <>
      {property.data && !property.isError ? <h3 className="font-semibold">{property.data.property_address}{property.data.city ? `, ${property.data.city}` : ''}</h3> : <p role="status">{property.isError ? 'Property details could not be confirmed.' : 'Loading property…'}</p>}
      {state.data && !state.isError && <p>Reviewed amount: {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(state.data.amount)}</p>}
      {!pending && state.data && !state.data.amount_approval_current && <p role="alert">Complete the current amount review in step 4 before creating a draft.</p>}
      {(state.isError || sellers.isError || history.isError) && <p role="alert">Current review or seller choices could not be confirmed. Refresh to try again.</p>}
      <button className={button} disabled={busy || termsPending || linkPending || signaturePending} onClick={() => { void state.refetch(); void property.refetch(); void history.refetch(); if (!pending) void sellers.refetch(); }}>Refresh draft information</button>
      {!pending && existing && <div role="status" className="rounded-lg border border-green-200 bg-green-50 p-3"><h3 className="font-semibold">{existing.acquisition_status === 'pending_signature' ? 'Contract awaiting signature' : 'Existing draft'}: {existing.deal_name}</h3><p className="text-sm">Current contract version {existing.acquisition_version}.</p>{existing.acquisition_status === 'pending_signature' && <p className="font-medium">Awaiting signature. This status does not confirm that an agreement was sent or signed.</p>}<p className="text-sm">{existing.acquisition_status === 'pending_signature' ? 'The reviewed terms are held. Signature-release review and withdrawal remain available below.' : 'Continue with document and title review before any agreement is signed or sent. Another draft cannot be created for this lead.'}</p></div>}
      {pending ? <div className="rounded-lg border border-amber-300 bg-amber-50 p-3"><h3 className="font-semibold">Recover your saved request</h3><p>{pending.request.name}</p><p className="text-sm">The original property, seller selection and offer review stay fixed until the save is confirmed.</p></div> : !existing && savedOffer !== offerId ? <fieldset disabled={busy} className="space-y-3">
        <legend className="font-semibold mb-2">Choose the reported seller</legend>
        {sellers.isFetching ? <p role="status">Loading seller relationships…</p> : <label className="block text-sm">Seller relationship<select className={input} value={relationship} onChange={event => setRelationship(event.target.value)}>
          <option value="">Select a recorded relationship</option>{sellers.data?.items.map(row => <option key={row.id} value={row.id}>{row.seller.display_name} — {row.relationship === 'reported_owner' ? 'reported owner' : 'reported representative'}</option>)}</select></label>}
        {sellers.data?.items.length === 0 && <p className="text-sm">No seller relationship is recorded for this property. <a className="underline" href="#acquisition-sellers">Return to seller review</a> before preparing a draft.</p>}
        <nav aria-label="Seller relationship pages" className="flex gap-2"><button className={button} disabled={cursors.length === 1 || sellers.isFetching} onClick={() => { setRelationship(''); setCursors(values => values.slice(0, -1)); }}>Previous sellers</button><button className={button} disabled={!sellers.data?.next_after || sellers.isFetching || sellers.isError} onClick={() => { const next = sellers.data?.next_after; if (next) { setRelationship(''); setCursors(values => [...values, next]); } }}>More sellers</button></nav>
        <label className="block text-sm">Draft name<input className={input} value={name} maxLength={500} onChange={event => setName(event.target.value)} placeholder="Property address or review name" /></label>
      </fieldset> : null}
      <button className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || documentPending || reviewPending || termsPending || linkPending || signaturePending || (!pending && !canSave)} onClick={() => { void save(); }}>{busy ? 'Saving…' : pending ? 'Retry same draft' : existing || savedOffer === offerId ? 'Draft saved' : 'Save draft for review'}</button>
      {!pending && documentTarget && <ContractDocuments context={documentTarget} disabled={(!preparationReady && !documentPending) || !documentContextReady || busy || reviewPending || termsPending || linkPending || signaturePending} disabledReason={signaturePending ? 'Finish the signature-release review below before changing documents.' : linkPending ? 'Finish the document reference step below before changing documents.' : termsPending ? 'Finish the terms step below before changing documents.' : reviewPending ? 'Finish recovery of the saved review below before changing documents.' : undefined} onPending={setDocumentPending} />}
      {!pending && documentTarget && <ContractLinksForm context={documentTarget} disabled={!linkContextReady || busy || documentPending || reviewPending || termsPending || signaturePending} onPending={handleLinkPending} onSaved={handleTermsSaved} />}
      {!pending && documentTarget && <ContractTermsForm context={documentTarget} disabled={!termsContextReady || busy || documentPending || reviewPending || linkPending || signaturePending} onPending={handleTermsPending} onSaved={handleTermsSaved} />}
      {!pending && documentTarget && <ContractReviewForm context={documentTarget} disabled={!reviewContextReady || busy || documentPending || termsPending || linkPending || signaturePending} onPending={handleReviewPending} />}
      {!pending && documentTarget && <SignatureReviewForm context={documentTarget} disabled={!signatureContextReady || busy || documentPending || termsPending || linkPending || reviewPending} onPending={handleSignaturePending} onSaved={handleTermsSaved} />}
    </>}
    {message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
