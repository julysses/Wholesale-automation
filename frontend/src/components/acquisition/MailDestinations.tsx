import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type Evidence = { mode: 'phone' | 'landing_page'; value: string; verification_ref: string; verification_hash: string; verified_at: string; expires_at: string };
type Review = { id: string; expected_version: number; action: 'approved' | 'withdrawn'; note: string } & Partial<Evidence>;
type Pending = { destination_id: string; review: Review };
type History = { id: string; workspace_id: string; campaign_id: string; destination_id: string; version: number; action: string; mode: string; value: string };
type State = { workspace_id: string; campaign_id: string; destination_id: string; version: number; latest_review: (History & Evidence) | null; status: string; review_current: boolean; execution_authorized: false; checked_at: string };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const timestamp = (s: unknown): s is string => typeof s === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(s) && Number.isFinite(Date.parse(s));
const empty: Evidence = { mode: 'phone', value: '', verification_ref: '', verification_hash: '', verified_at: '', expires_at: '' };
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded border p-2';
function evidence(value: Partial<Evidence>): boolean {
  return ['phone', 'landing_page'].includes(value.mode ?? '') && typeof value.value === 'string' && !!value.value.trim() && value.value.length <= 2048
    && uuid.test(value.verification_ref ?? '') && /^[a-f0-9]{64}$/.test(value.verification_hash ?? '')
    && timestamp(value.verified_at) && timestamp(value.expires_at) && Date.parse(value.expires_at) > Date.parse(value.verified_at);
}
function validPending(value: unknown): value is Pending {
  if (!value || typeof value !== 'object') return false;
  const p = value as Pending, r = p.review;
  if (Object.keys(p).sort().join(',') !== 'destination_id,review' || !uuid.test(p.destination_id) || !r || typeof r !== 'object'
    || !uuid.test(r.id) || !Number.isInteger(r.expected_version) || r.expected_version < 0 || r.expected_version >= 1000000000
    || typeof r.note !== 'string' || r.note.trim().length < 20 || r.note.length > 2000) return false;
  const common = 'action,expected_version,id,note';
  return r.action === 'withdrawn' ? Object.keys(r).sort().join(',') === common
    : r.action === 'approved' && Object.keys(r).sort().join(',') === 'action,expected_version,expires_at,id,mode,note,value,verification_hash,verification_ref,verified_at' && evidence(r);
}
function validHistory(row: History, workspace: string, campaign: string): boolean {
  return !!row && uuid.test(row.id) && row.workspace_id === workspace && row.campaign_id === campaign && uuid.test(row.destination_id)
    && Number.isInteger(row.version) && row.version > 0 && row.version <= 1000000000 && ['approved', 'withdrawn'].includes(row.action)
    && ['phone', 'landing_page'].includes(row.mode) && typeof row.value === 'string' && !!row.value && row.value.length <= 2048;
}
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }
export function MailDestinations(props: { userId: string; workspace: string; campaign: string }) {
  return <DestinationEditor key={`${props.userId}:${props.workspace}:${props.campaign}`} {...props}/>;
}
function DestinationEditor({ userId, workspace, campaign }: { userId: string; workspace: string; campaign: string }) {
  const path = `/api/acquisition/workspaces/${workspace}/campaigns/${campaign}/mail-destinations`;
  const key = `acquisition-destination-request:v1:${userId}:${workspace}:${campaign}`;
  const [initial] = useState(() => {
    try { const raw = sessionStorage.getItem(key); if (!raw) return { request: null, invalid: false }; const p: unknown = JSON.parse(raw);
      if (!validPending(p)) throw new Error('Invalid request'); return { request: p, invalid: false };
    } catch { return { request: null, invalid: true }; }
  });
  const [pending, setPending] = useState<Pending | null>(initial.request);
  const [open, setOpen] = useState(!!initial.request || initial.invalid);
  const [selected, setSelected] = useState<string | null>(initial.request?.destination_id ?? null);
  const [baseVersion, setBaseVersion] = useState<number | null>(initial.request?.review.expected_version ?? null);
  const [details, setDetails] = useState<Evidence>(initial.request?.review.action === 'approved' ? initial.request.review as Evidence : empty);
  const [note, setNote] = useState(initial.request?.review.note ?? ''); const [attested, setAttested] = useState(false);
  const [busy, setBusy] = useState(false); const inFlight = useRef(false); const [message, setMessage] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]); const after = cursors.at(-1);
  const access = useQuery({ queryKey: ['mail-destination-access', userId, workspace], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => { const rows = await read(`/api/acquisition/workspaces/${workspace}/memberships`, signal);
      if (!Array.isArray(rows)) throw new Error('Access unavailable');
      return rows.some(row => row?.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin'].includes(row.role)); } });
  const history = useQuery({ queryKey: ['mail-destination-history', userId, workspace, campaign, after], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }): Promise<{ items: History[]; next_after: string | null }> => {
      const page = await read(`${path}?limit=20${after ? `&after=${after}` : ''}`, signal);
      if (!Array.isArray(page?.items) || page.items.length > 20 || !page.items.every((row: History) => validHistory(row, workspace, campaign))
        || !(page.next_after === null || (typeof page.next_after === 'string' && uuid.test(page.next_after) && page.next_after === page.items.at(-1)?.id && page.next_after !== after))) throw new Error('History unavailable');
      return page;
    } });
  const current = useQuery({ queryKey: ['mail-destination-state', userId, workspace, campaign, selected], enabled: open && !!selected, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }): Promise<State> => {
      const row = await read(`${path}/${selected}`, signal);
      if (!row || row.workspace_id !== workspace || row.campaign_id !== campaign || row.destination_id !== selected
        || !Number.isInteger(row.version) || row.version < 0 || row.version > 1000000000 || row.execution_authorized !== false
        || !timestamp(row.checked_at) || typeof row.review_current !== 'boolean' || !['approved', 'withdrawn', 'requires_review', 'pending_review'].includes(row.status)
        || row.review_current !== (row.status === 'approved')
        || (row.version === 0 ? row.latest_review !== null || row.status !== 'pending_review'
          : !validHistory(row.latest_review, workspace, campaign) || row.latest_review.destination_id !== selected || row.latest_review.version !== row.version
            || !evidence(row.latest_review) || (row.review_current && !(Date.parse(row.latest_review.verified_at) <= Date.parse(row.checked_at) && Date.parse(row.checked_at) < Date.parse(row.latest_review.expires_at))) || (row.latest_review.action === 'withdrawn') !== (row.status === 'withdrawn') || row.status === 'pending_review')) throw new Error('State unavailable');
      return row;
    } });
  const editable = access.data === true && !access.isError && !access.isFetching && !pending && !busy && !initial.invalid;
  const stateReady = !!selected && !!current.data && !current.isFetching && !current.isError;
  const prepared = !selected || (stateReady && baseVersion === current.data?.version);
  const noteValid = note.trim().length >= 20 && note.length <= 2000;
  const approve = editable && prepared && (!selected || current.data!.version < 1000000000) && evidence(details) && noteValid && attested;
  const withdraw = editable && stateReady && current.data!.version < 1000000000 && current.data?.latest_review?.action === 'approved' && noteValid;
  function refresh() { void access.refetch(); void history.refetch(); if (selected) void current.refetch(); }
  function loadDetails() {
    if (!editable || !stateReady || !current.data?.latest_review) return;
    const row = current.data.latest_review;
    setBaseVersion(row.version); setDetails({ mode: row.mode, value: row.value, verification_ref: row.verification_ref, verification_hash: row.verification_hash, verified_at: row.verified_at, expires_at: row.expires_at }); setNote(''); setAttested(false);
  }
  async function save(action: Review['action']) {
    if (inFlight.current || initial.invalid || (!pending && !(action === 'approved' ? approve : withdraw))) return;
    inFlight.current = true; setBusy(true); setMessage(''); const retrying = !!pending; let sent = false;
    const request: Pending = pending ?? { destination_id: selected ?? crypto.randomUUID(), review: { id: crypto.randomUUID(), expected_version: selected ? current.data!.version : 0, action, note, ...(action === 'approved' ? details : {}) } };
    try {
      sessionStorage.setItem(key, JSON.stringify(request)); setPending(request); sent = true;
      const receipt = await (await apiFetch(`${path}/${request.destination_id}/reviews`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request.review) })).json();
      if (receipt?.review_id !== request.review.id || receipt.workspace_id !== workspace || receipt.destination_id !== request.destination_id
        || receipt.version !== request.review.expected_version + 1 || typeof receipt.duplicate !== 'boolean' || receipt.execution_authorized !== false) throw new Error('Unconfirmed receipt');
      sessionStorage.removeItem(key); setPending(null); setSelected(request.destination_id); setBaseVersion(null); setAttested(false); setNote('');
      setMessage('Destination review recorded. Refresh current status before using it; mail fulfillment requires separate approval.');
      refresh();
    } catch (error) {
      if (!retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        try { sessionStorage.removeItem(key); setPending(null); } catch { /* Retain exact request until reconciled. */ }
        setBaseVersion(null); setAttested(false); setMessage('Review rejected. Refresh and load the current destination before reviewing again.'); refresh();
      } else setMessage(sent || retrying ? 'Review is unconfirmed. The exact request is retained in this tab; retry it to reconcile.' : 'Browser storage is unavailable. No review was sent.');
    } finally { setBusy(false); inFlight.current = false; }
  }
  return <section aria-label="Mail response destinations" className="mt-4 space-y-3">
    <button className={button} aria-expanded={open} disabled={busy || !!pending || initial.invalid} onClick={() => setOpen(v => !v)}>{open ? 'Hide mail destinations' : 'Review mail destinations'}</button>
    {open && <><p>Review the phone number or website printed on mail. This records your verification of control and routing; it does not configure a destination, approve mail content, or send mail.</p>
      <button className={button} disabled={busy} onClick={refresh}>Refresh destinations</button>
      {initial.invalid && <p role="alert">Saved destination request cannot be read. Reconcile it before creating another review.</p>}
      {!editable && !pending && !busy && <p>Destination approval requires current owner or administrator access.</p>}
      {history.isFetching ? <p role="status">Loading destination history…</p> : history.isError ? <p role="alert">Destination history could not be verified.</p> : <ul>{history.data?.items.map(row => <li className="border-t py-2" key={row.id}><p className="break-all">{row.value} · Version {row.version} · Recorded {row.action}</p><button className={button} disabled={busy || !!pending || initial.invalid} onClick={() => { setSelected(row.destination_id); setBaseVersion(null); setDetails(empty); setNote(''); setAttested(false); setMessage(''); }}>Inspect destination {row.destination_id}</button></li>)}</ul>}
      <p className="text-sm">History is paginated by reference, not recency. Recorded approvals may have expired or been withdrawn; inspect current status.</p>
      <nav aria-label="Destination history pages"><button className={button} disabled={busy || !!pending || cursors.length === 1 || history.isFetching} onClick={() => setCursors(v => v.slice(0, -1))}>Previous destinations</button><button className={button} disabled={busy || !!pending || history.isFetching || history.isError || !history.data?.next_after} onClick={() => { if (history.data?.next_after) setCursors(v => [...v, history.data!.next_after]); }}>Next destinations</button></nav>
      {selected && <div><p className="break-all">Destination reference: {selected}</p>{current.isFetching ? <p role="status">Checking current destination…</p> : current.isError ? <p role="alert">Current destination could not be verified.</p> : current.data && <div><p>Current status: {current.data.status} · Version {current.data.version}</p><p className="text-sm">Status checked at: {current.data.checked_at}</p></div>}
        <button className={button} disabled={!editable || !stateReady || !current.data?.latest_review} onClick={loadDetails}>Load current destination details</button>
        <button className={button} disabled={!editable} onClick={() => { setSelected(null); setBaseVersion(null); setDetails(empty); setNote(''); setAttested(false); }}>Start a separate destination</button></div>}
      <fieldset disabled={!editable || !prepared} className="space-y-3"><legend>{selected ? 'Review selected destination' : 'New response destination'}</legend>
        <label>Response method<select className={input} value={details.mode} onChange={e => setDetails(v => ({ ...v, mode: e.target.value as Evidence['mode'] }))}><option value="phone">Phone</option><option value="landing_page">Website</option></select></label>
        <label>Phone number or HTTPS address<input className={input} value={details.value} maxLength={2048} onChange={e => setDetails(v => ({ ...v, value: e.target.value }))}/></label>
        <label>Verification evidence reference<input className={input} value={details.verification_ref} onChange={e => setDetails(v => ({ ...v, verification_ref: e.target.value }))}/></label>
        <label>Evidence SHA-256 digest<input className={input} value={details.verification_hash} maxLength={64} onChange={e => setDetails(v => ({ ...v, verification_hash: e.target.value }))}/></label>
        <label>Verified at (ISO date with time zone)<input className={input} placeholder="2026-10-28T12:00:00-05:00" value={details.verified_at} onChange={e => setDetails(v => ({ ...v, verified_at: e.target.value }))}/></label>
        <label>Verification expires at (ISO date with time zone)<input className={input} placeholder="2026-11-28T12:00:00-06:00" value={details.expires_at} onChange={e => setDetails(v => ({ ...v, expires_at: e.target.value }))}/></label>
        <label className="block"><input type="checkbox" checked={attested} onChange={e => setAttested(e.target.checked)}/> I reviewed destination control and routing evidence.</label>
      </fieldset>
      <label className="block">Review or withdrawal reason<textarea className={input} disabled={!editable} value={note} maxLength={2000} onChange={e => setNote(e.target.value)}/></label>
      <p className="text-sm">Provide at least 20 characters and a retained evidence reference. Evidence storage and verification are separate requirements.</p>
      {pending ? <button className={button} disabled={busy || initial.invalid} onClick={() => { void save(pending.review.action); }}>Retry exact destination review</button> : <><button className={button} disabled={!approve} onClick={() => { void save('approved'); }}>Record destination approval</button><button className={button} disabled={!withdraw} onClick={() => { void save('withdrawn'); }}>Withdraw destination approval</button></>}
      {busy && <p role="status">Recording destination review…</p>}
      {message && <p role="status">{message}</p>}
    </>}
  </section>;
}
