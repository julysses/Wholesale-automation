import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';
import { IntakeQualification } from './IntakeQualification';

type Intake = { id: string; lead_id: string; classification: string; created_at: string };
type Detail = Intake & { prepared_answers: { answers: Record<string, string>; missing_fields: string[]; reason_codes: string[] }; normalization_notes: string[] };
type Target = { lead_id: string; property_id: string | null; property_address: string; city: string; state: string; county: string | null; parcel_id: string | null; county_unit: string | null; match_basis: string };
type Review = { id: string; sequence: number; action: string; review_note: string; property_evidence_ref: string | null; seller_evidence_ref: string | null; created_at: string };
type State = { sequence: number; preparation_hash: string; target_hash: string | null; target_snapshot: Record<string, unknown> | null; latest_review: Review | null; link_current: boolean };
type Decision = { id: string; expected_sequence: number; preparation_hash: string; action: string; target_lead_id: string | null; target_hash: string | null;
  property_basis: string | null; property_evidence_ref: string | null; seller_evidence_ref: string | null; review_note: string };
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded border p-2';
const options = { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false } as const;
async function read<T>(path: string, signal?: AbortSignal): Promise<T> { return (await apiFetch(path, { signal })).json(); }
async function readState(path: string, signal?: AbortSignal): Promise<State> {
  const value = await read<State>(path, signal);
  if (!Number.isInteger(value?.sequence) || value.sequence < 0 || !/^[a-f0-9]{64}$/.test(value.preparation_hash)
    || (value.target_hash !== null && !/^[a-f0-9]{64}$/.test(value.target_hash)) || typeof value.link_current !== 'boolean') throw new Error('Invalid review state');
  return value;
}

export function IntakeReview({ userId, workspace }: { userId: string; workspace: string }) {
  const [open, setOpen] = useState(false);
  return <section className="rounded-xl border bg-white p-4 space-y-4">
    <h2 className="font-semibold text-lg">{open ? 'Seller intake identity review' : <button aria-expanded={false} onClick={() => setOpen(true)}>Seller intake identity review</button>}</h2>
    {!open && <p className="text-sm text-gray-600">Compare seller submissions with workspace property records and review repeat inquiries.</p>}
    {open && <IntakeQueue key={`${userId}:${workspace}`} userId={userId} workspace={workspace} />}
  </section>;
}
function IntakeQueue({ userId, workspace }: { userId: string; workspace: string }) {
  const base = `/api/acquisition/workspaces/${workspace}/intakes`;
  const [cursors, setCursors] = useState<(string | null)[]>([null]); const after = cursors.at(-1);
  const [selected, setSelected] = useState<string | null>(null);
  const queue = useQuery({ ...options, queryKey: ['intake-queue', userId, workspace, after], queryFn: async ({ signal }) => {
    const data = await read<{ items: Intake[]; next_after: string | null }>(`${base}?limit=20${after ? `&after=${encodeURIComponent(after)}` : ''}`, signal);
    if (!Array.isArray(data?.items) || !data.items.every(row => typeof row.id === 'string' && typeof row.classification === 'string')
      || (data.next_after !== null && typeof data.next_after !== 'string')) throw new Error('Invalid intake queue');
    return data;
  } });
  return <div className="space-y-4">
    <p className="text-sm">Original classifications are retained. Identity review does not verify title, grant contact permission or send an offer.</p>
    <button className={button} disabled={queue.isFetching} onClick={() => { void queue.refetch(); }}>Refresh intakes</button>
    {queue.isFetching ? <p role="status">Loading intakes…</p> : queue.isError ? <p role="alert">Intakes unavailable. Check workspace access.</p> : <>
      {!queue.data?.items.length && <p>No seller intakes on this page.</p>}
      <ul className="space-y-2">{queue.data?.items.map(row => <li key={row.id} className="border rounded p-3">
        <p className="text-sm break-all">{row.id} · {row.classification.replaceAll('_', ' ')} · {row.created_at}</p>
        <button className={button} disabled={!!selected} onClick={() => setSelected(row.id)}>Review intake</button>
      </li>)}</ul></>}
    <nav aria-label="Intake pages" className="flex gap-2">
      <button className={button} disabled={queue.isFetching || cursors.length === 1} onClick={() => setCursors(c => c.slice(0, -1))}>Previous intakes</button>
      <button className={button} disabled={queue.isFetching || queue.isError || !queue.data?.next_after} onClick={() => { if (queue.data?.next_after) setCursors(c => [...c, queue.data!.next_after]); }}>More intakes</button>
    </nav>
    {selected && <IdentityReview key={selected} userId={userId} workspace={workspace} intake={selected} onClose={() => setSelected(null)} onSaved={() => { void queue.refetch(); }} />}
  </div>;
}
function IdentityReview({ userId, workspace, intake, onClose, onSaved }: { userId: string; workspace: string; intake: string; onClose: () => void; onSaved: () => void }) {
  const base = `/api/acquisition/workspaces/${workspace}`; const path = `${base}/intakes/${intake}`;
  const [target, setTarget] = useState(''); const [action, setAction] = useState('link_property');
  const [basis, setBasis] = useState(''); const [propertyRef, setPropertyRef] = useState(''); const [sellerRef, setSellerRef] = useState('');
  const [note, setNote] = useState(''); const [ack, setAck] = useState(false); const [feedback, setFeedback] = useState('');
  const [pending, setPending] = useState<Decision | null>(null); const [busy, setBusy] = useState(false); const inFlight = useRef(false);
  const [before, setBefore] = useState<number | null>(null);
  const [assessmentPending, setAssessmentPending] = useState(false);
  const [assessmentRevision, setAssessmentRevision] = useState(0);
  const detail = useQuery({ ...options, queryKey: ['intake-detail', userId, workspace, intake], queryFn: async ({ signal }) => {
    const value = await read<Detail>(path, signal);
    if (!value?.prepared_answers?.answers || !Array.isArray(value.prepared_answers.missing_fields) || !Array.isArray(value.prepared_answers.reason_codes) || !Array.isArray(value.normalization_notes)) throw new Error('Invalid intake evidence');
    return value;
  } });
  const candidates = useQuery({ ...options, queryKey: ['intake-candidates', userId, workspace, intake], queryFn: async ({ signal }) => {
    const value = await read<{ items: Target[]; truncated: boolean }>(`${path}/candidates?limit=50`, signal);
    if (!Array.isArray(value?.items) || typeof value.truncated !== 'boolean' || !value.items.every(row => typeof row.lead_id === 'string' && typeof row.match_basis === 'string')) throw new Error('Invalid candidates');
    return value;
  } });
  const access = useQuery({ ...options, queryKey: ['intake-access', userId, workspace], queryFn: async ({ signal }) => {
    const rows = await read<{ workspace_id: string; user_id: string; status: string; role: string }[]>(`${base}/memberships`, signal);
    return Array.isArray(rows) && rows.some(row => row.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin'].includes(row.role));
  } });
  const statePath = `${path}/identity-state${target && action !== 'revoke' ? `?target=${encodeURIComponent(target)}` : ''}`;
  const state = useQuery({ ...options, queryKey: ['intake-state', userId, workspace, intake, target, action === 'revoke'], queryFn: ({ signal }) => readState(statePath, signal) });
  const history = useQuery({ ...options, queryKey: ['intake-history', userId, workspace, intake, before], queryFn: async ({ signal }) => {
    const rows = await read<Review[]>(`${path}/identity-reviews?limit=20${before ? `&before=${before}` : ''}`, signal);
    if (!Array.isArray(rows) || !rows.every(row => typeof row.id === 'string' && Number.isInteger(row.sequence) && typeof row.review_note === 'string')) throw new Error('Invalid review history');
    return rows;
  } });
  const available = access.data === true && !access.isError && !access.isFetching && !!state.data && !state.isError && !state.isFetching
    && !!detail.data && !detail.isError && !detail.isFetching && !!history.data && !history.isError && !history.isFetching;
  const valid = available && ack && note.trim().length >= 20 && (action === 'revoke' ? !!state.data?.latest_review && state.data.latest_review.action !== 'revoke'
    : !!target && !!state.data?.target_hash && !!basis && propertyRef.trim().length >= 10 && (action !== 'repeat_inquiry' || sellerRef.trim().length >= 10));
  async function submit() {
    if (inFlight.current || assessmentPending || (!pending && !valid)) return;
    inFlight.current = true; setBusy(true); setFeedback(''); let request = pending;
    try {
      if (!request) {
        const fresh = await readState(statePath);
        if (fresh.sequence !== state.data!.sequence || fresh.preparation_hash !== state.data!.preparation_hash || fresh.target_hash !== state.data!.target_hash)
          throw new Error('Review changed');
        request = { id: crypto.randomUUID(), expected_sequence: fresh.sequence, preparation_hash: fresh.preparation_hash, action,
          target_lead_id: action === 'revoke' ? null : target, target_hash: action === 'revoke' ? null : fresh.target_hash,
          property_basis: action === 'revoke' ? null : basis, property_evidence_ref: action === 'revoke' ? null : propertyRef.trim(),
          seller_evidence_ref: action === 'repeat_inquiry' ? sellerRef.trim() : null, review_note: note.trim() };
        setPending(request);
      }
      const result = await (await apiFetch(`${path}/identity-reviews`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
      if (result?.review_id !== request.id || result.sequence !== request.expected_sequence + 1 || typeof result.duplicate !== 'boolean' || result.outreach_authorized !== false) throw new Error('Unconfirmed result');
      setPending(null); setAck(false); setNote(''); setBefore(null); setFeedback('Identity review recorded. Original records remain intact; no seller contact or offer was authorized.');
      void state.refetch(); void history.refetch(); setAssessmentRevision(value => value + 1); onSaved();
    } catch (error) {
      const definite = error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (definite) { setPending(null); setAck(false); void state.refetch(); }
      setFeedback(request && !definite ? 'Result unconfirmed. Keep this review open and retry the exact request to reconcile it.' : 'Review unavailable or changed. Refresh the evidence and check MFA and workspace access before deciding.');
      if (!request) setAck(false);
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Selected intake review" className="border rounded-lg p-4 space-y-4">
    <h3 className="font-semibold">Review seller identity and property</h3>
    <p className="text-sm">Owner/admin MFA is required to record a decision. Phone matches alone do not establish property or seller identity.</p>
    {detail.isError ? <p role="alert">Seller evidence unavailable.</p> : detail.data && <div>
      <h4 className="font-medium">Seller-submitted answers</h4><dl className="grid sm:grid-cols-2 gap-2 text-sm">{Object.entries(detail.data.prepared_answers.answers).map(([key, value]) => <div key={key} className="break-words"><dt className="text-gray-500">{key.replaceAll('_', ' ')}</dt><dd>{value || 'Missing'}</dd></div>)}</dl>
      <p className="text-sm mt-2">Missing: {detail.data.prepared_answers.missing_fields.join(', ') || 'None reported'}</p>
      <p className="text-sm">Review flags: {[...detail.data.prepared_answers.reason_codes, ...detail.data.normalization_notes].join(', ') || 'None reported'}</p>
    </div>}
    <div><h4 className="font-medium">Candidate property records</h4>
      {candidates.isError ? <p role="alert">Candidates unavailable.</p> : candidates.data && <>
        {candidates.data.truncated && <p role="alert">Only the first 50 candidates are shown. This is not a complete identity search.</p>}
        {!candidates.data.items.length && <p>No scoped candidate found. Canonical enrollment or further investigation is required.</p>}
        {candidates.data.items.map(row => <div key={row.lead_id} className="border rounded p-3 my-2 text-sm">
          <p>{row.property_address || 'Address missing'}, {row.city} {row.state}</p><p>{row.match_basis === 'CONTACT_ONLY' ? 'Contact-only match; independent property evidence required.' : 'Exact address text; independent verification still required.'}</p>
          <p>Parcel: {row.parcel_id ?? 'Unbound'} · County: {row.county ?? 'Unknown'} · Unit: {row.county_unit ?? 'Unknown'}</p>
          <button className={button} disabled={assessmentPending || busy || !!pending || !row.property_id} onClick={() => { setTarget(row.lead_id); setAck(false); }}>{target === row.lead_id ? 'Selected property' : 'Select property'}</button>
        </div>)}
      </>}
    </div>
    {state.isError ? <p role="alert">Current identity state unavailable.</p> : state.data && <div className="text-sm">
      <p>Review sequence {state.data.sequence}. {state.data.link_current ? 'Reviewed link is current.' : 'No currently valid reviewed link.'}</p>
      {state.data.target_snapshot && <details><summary>Exact target evidence</summary><dl>{Object.entries(state.data.target_snapshot).filter(([key]) => key !== 'contact_fingerprint').map(([key, value]) => <div key={key} className="break-all"><dt>{key.replaceAll('_', ' ')}</dt><dd>{value === null ? 'Unknown' : String(value)}</dd></div>)}</dl></details>}
    </div>}
    <fieldset disabled={!available || assessmentPending || busy || !!pending} className="space-y-3">
      <label className="block text-sm">Identity decision<select className={input} value={action} onChange={e => { setAction(e.target.value); setAck(false); }}><option value="link_property">Link property</option><option value="repeat_inquiry">Mark reviewed repeat inquiry</option><option value="revoke">Revoke prior link</option></select></label>
      {action !== 'revoke' && <>
        <label className="block text-sm">Property evidence basis<select className={input} value={basis} onChange={e => setBasis(e.target.value)}><option value="">Select evidence basis</option><option value="parcel_document">Parcel document</option><option value="verified_address">Independently verified address</option></select></label>
        <label className="block text-sm">Property evidence reference<input className={input} maxLength={500} value={propertyRef} onChange={e => setPropertyRef(e.target.value)} /></label>
        {action === 'repeat_inquiry' && <label className="block text-sm">Seller identity evidence reference<input className={input} maxLength={500} value={sellerRef} onChange={e => setSellerRef(e.target.value)} /></label>}
      </>}
      <label className="block text-sm">Identity review note<textarea className={input} maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />I reviewed the displayed source, target and evidence for this decision.</label>
    </fieldset>
    <div className="flex flex-wrap gap-2"><button className={button} disabled={assessmentPending || busy || (!pending && !valid)} onClick={() => { void submit(); }}>{busy ? 'Recording identity review…' : pending ? 'Retry exact identity request' : 'Record identity review'}</button>
      <button className={button} disabled={assessmentPending || busy || !!pending} onClick={() => { setAck(false); void detail.refetch(); void candidates.refetch(); void state.refetch(); void access.refetch(); void history.refetch(); setAssessmentRevision(value => value + 1); }}>Refresh identity evidence</button>
      <button className={button} disabled={assessmentPending || busy || !!pending} onClick={onClose}>Close intake review</button></div>
    {feedback && <p role="status">{feedback}</p>}
    <IntakeQualification userId={userId} workspace={workspace} intake={intake} revision={assessmentRevision} locked={busy || !!pending} onPending={setAssessmentPending} />
    <h4 className="font-medium">Identity review history</h4>
    {history.isFetching ? <p>Loading review history…</p> : history.isError ? <p role="alert">Review history unavailable.</p> : <>
      {!history.data?.length && <p>No identity reviews on this page.</p>}
      {history.data?.map(row => <div key={row.id} className="text-sm border rounded p-2 break-words"><p>{row.sequence} · {row.action.replaceAll('_', ' ')} · {row.created_at}</p><p>{row.review_note}</p><p>{row.property_evidence_ref} {row.seller_evidence_ref}</p></div>)}
      <div className="flex gap-2"><button className={button} disabled={assessmentPending || busy || !!pending || before === null} onClick={() => setBefore(null)}>Latest identity reviews</button>
        <button className={button} disabled={assessmentPending || busy || !!pending || history.data?.length !== 20} onClick={() => setBefore(history.data!.at(-1)!.sequence)}>Older identity reviews</button></div>
    </>}
  </section>;
}
