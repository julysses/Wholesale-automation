import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { assembleBuyer, buyerAmounts, emptyBuyer, buyerDetailsSchema, clearConfirmedBuyer, clearRejectedBuyer, parseBuyerPage, parseBuyerProfile,
  pendingBuyerSchema, preserveBuyer, readPendingBuyer, type BuyerDetails, type PendingBuyer } from '@/lib/acquisition/buyers';
import { BuyerDetailsFields, BuyerDetailsSummary } from './BuyerDetailsFields';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
type Props = { userId: string; workspace: string; disabled: boolean; onPending: (value: boolean) => void };
export function BuyerProfiles(props: Props) {
  return <BuyerEditor key={`${props.userId}:${props.workspace}`} {...props} />;
}
function BuyerEditor({ userId, workspace, disabled, onPending }: Props) {
  const [initial] = useState(() => { try { return { saved: readPendingBuyer(sessionStorage, userId, workspace), blocked: false }; }
    catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingBuyer | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved || initial.blocked), [busy, setBusy] = useState(false);
  const [after, setAfter] = useState<string | null>(null), [selection, setSelection] = useState<{ buyer: string; revision: number } | null>(null);
  const [details, setDetails] = useState(emptyBuyer), [amounts, setAmounts] = useState(() => buyerAmounts(emptyBuyer())), [zips, setZips] = useState('');
  const [review, setReview] = useState<BuyerDetails | null>(null), [message, setMessage] = useState('');
  const [retryAt, setRetryAt] = useState(0), [now, setNow] = useState(Date.now());
  const lock = useRef(false), mounted = useRef(true);
  const held = expanded || !!pending || blocked || busy;
  const path = `/api/acquisition/workspaces/${workspace}/buyers`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, onPending]);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { window.removeEventListener('beforeunload', warn); clearInterval(timer); }; }, [held]);
  const page = useQuery({ queryKey: ['acquisition-buyers', userId, workspace, after], enabled: expanded && !disabled && !blocked && !pending && !selection,
    queryFn: async ({ signal }) => parseBuyerPage(await (await apiFetch(`${path}?limit=25${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), workspace, after),
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false });
  const pageReady = !page.isError && !page.isFetching && page.data && now - Date.parse(page.data.checked_at) <= 30000 && Date.parse(page.data.checked_at) - now <= 5000;
  function begin(buyer: string, revision: number, value: BuyerDetails) {
    setSelection({ buyer, revision }); setDetails(value); setAmounts(buyerAmounts(value)); setZips(value.target_zips.join(', ')); setReview(null); setMessage('');
  }
  function back() { if (busy || pending || blocked) return; setSelection(null); setReview(null); setMessage(''); }
  async function choose(buyer: string) {
    if (lock.current || disabled || blocked || pending) return;
    lock.current = true; setBusy(true); setMessage('');
    try {
      const value = parseBuyerProfile(await (await apiFetch(`${path}/${buyer}`, { cache: 'no-store', signal: AbortSignal.timeout(30000) })).json(), workspace, buyer);
      if (!mounted.current) return;
      begin(buyer, value.revision, value.details);
      if (!value.can_save) setMessage('Buyer changes are paused. You may review these details; saving requires current server approval.');
    } catch { if (mounted.current) setMessage('Buyer details could not be confirmed. Refresh the list and try again.'); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  function prepareReview() {
    try { setReview(buyerDetailsSchema.parse(assembleBuyer(details, amounts, zips))); setMessage(''); }
    catch { setMessage('Check names, contact details, unique ZIP codes, budgets and source notes. Leave unknown amounts blank; minimum price cannot exceed maximum price.'); }
  }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && (!selection || !review))) return;
    lock.current = true; setBusy(true); setMessage(''); let saved = pending, sent = false; const firstAttempt = !pending;
    try {
      if (!saved) {
        if (selection!.revision === 0) {
          const current = parseBuyerPage(await (await apiFetch(`${path}?limit=1`, { cache: 'no-store', signal: AbortSignal.timeout(30000) })).json(), workspace, null, 1);
          if (!current.can_save) throw new Error('Buyer changes paused');
        } else {
          const current = parseBuyerProfile(await (await apiFetch(`${path}/${selection!.buyer}`, { cache: 'no-store', signal: AbortSignal.timeout(30000) })).json(), workspace, selection!.buyer);
          if (!current.can_save || current.revision !== selection!.revision) throw new Error('Buyer changed or paused');
        }
        if (!mounted.current) return;
        saved = pendingBuyerSchema.parse({ version: 1, context: { userId, workspaceId: workspace }, request: {
          id: crypto.randomUUID(), buyer_id: selection!.buyer, expected_revision: selection!.revision, details: review } });
        try { saved = preserveBuyer(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedBuyer(sessionStorage, saved, receipt); setPending(null); setSelection(null); setReview(null); setAfter(null);
      setMessage('Buyer details saved for review. Verification, matching and permission to contact the buyer remain separate steps.');
      void page.refetch();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedBuyer) {
        try { clearRejectedBuyer(sessionStorage, saved, true, true); setPending(null); setReview(null); setMessage('The save was rejected. Return to the buyer list and reload current details before reviewing again.'); }
        catch { setBlocked(true); setMessage('Buyer recovery needs reconciliation. Keep the original saved request.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved request to avoid duplicates.' : 'Current buyer details or save permission changed. Return to the list and reload before saving.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Buyer profiles" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-4 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Prepare buyer profiles</h3><p className="text-sm text-gray-600">Keep investor preferences in this workspace for the next disposition review.</p>
    {!expanded && <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>Open buyer profiles</button>}
    {expanded && !blocked && !pending && <>
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy} onClick={() => { back(); setExpanded(false); }}>Close without saving</button>
        {selection && <button type="button" className={button} disabled={busy} onClick={back}>Back to buyer list</button>}</div>
      {disabled && <p role="alert">Finish the adjacent pending step before continuing.</p>}
      {!selection && <div className="space-y-3"><h4 className="font-medium">1. Choose or add a buyer</h4>
        <button type="button" className={button} disabled={disabled || busy || page.isFetching} onClick={() => { setNow(Date.now()); void page.refetch(); }}>Refresh buyers</button>
        {(page.isError || !pageReady) && !page.isFetching && <p role="status">Refresh the buyer list to confirm current access.</p>}
        {page.isFetching && <p role="status">Loading buyers…</p>}
        {pageReady && page.data && <><p className="text-sm">{page.data.can_save ? 'Choose a profile to review, or add buyer-reported details.' : 'Changes are paused. Saved profiles are available for review.'}</p>
          <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || !page.data.can_save} onClick={() => begin(crypto.randomUUID(), 0, emptyBuyer())}>Add buyer</button>
          {!page.data.items.length && <p className="text-sm">No buyer profiles on this page.</p>}
          <ul className="space-y-2">{page.data.items.map(buyer => <li key={buyer.buyer_id} className="rounded-lg border bg-white p-3 flex flex-wrap items-center justify-between gap-2"><span className="text-sm break-words min-w-0">{buyer.first_name} {buyer.last_name}{buyer.company ? ` · ${buyer.company}` : ''}<span className="block text-xs text-gray-500">{buyer.active ? 'Active for review' : 'Inactive'} · Verification pending</span></span><button type="button" className={button} disabled={disabled || busy} onClick={() => { void choose(buyer.buyer_id); }}>Review profile</button></li>)}</ul>
          <div className="flex flex-wrap gap-2">{after && <button type="button" className={button} disabled={disabled || busy} onClick={() => setAfter(null)}>First page</button>}{page.data.next_cursor && <button type="button" className={button} disabled={disabled || busy} onClick={() => setAfter(page.data!.next_cursor)}>Next page</button>}</div></>}
      </div>}
      {selection && !review && <><BuyerDetailsFields details={details} amounts={amounts} zips={zips} onChange={setDetails} onAmounts={setAmounts} onZips={setZips} disabled={disabled || busy} />
        <button type="button" className={button} disabled={disabled || busy} onClick={prepareReview}>Review buyer details</button></>}
      {review && <div className="space-y-3"><h4 className="font-medium">3. Review and save</h4><BuyerDetailsSummary details={review} />
        <p className="text-sm">Saving records these preferences only. It does not approve the buyer, distribute a property or authorize outreach.</p>
        <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={busy} onClick={() => setReview(null)}>Edit details</button>
          <button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Saving…' : 'Save buyer profile'}</button></div></div>}
    </>}
    {blocked && <p role="alert">Saved buyer recovery could not be read safely. Reconcile the original request before continuing.</p>}
    {pending && <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3"><h4 className="font-semibold">Recover the saved buyer request</h4><BuyerDetailsSummary details={pending.request.details} />
      <p className="text-sm">Keep this exact request until its outcome is confirmed.</p><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || blocked || busy || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Checking saved request…' : 'Retry saved buyer request'}</button></div>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
