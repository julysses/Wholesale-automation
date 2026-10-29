import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { ApiError, apiFetch } from '@/lib/api';
import { destination, history, id, page, pendingSchema, preparation, proof, scoped, state, template, type Pending, type Preparation, type Proof } from '@/lib/acquisition/mail-content';

type Props = { userId: string; workspace: string; campaign: string; onPending: (key: string, pending: boolean) => void };
const button = 'max-w-full break-words rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded-lg border p-2';
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }
async function post(path: string, body: unknown) { return (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json(); }
function usePage<T extends { id: string; workspace_id: string; campaign_id: string }>(path: string, schema: z.ZodType<T>, props: Props, open: boolean) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]); const after = cursors.at(-1)!;
  const query = useQuery({ queryKey: ['mail-content-source', props.userId, path, after], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => page(await read(`${path}?limit=20${after ? `&after=${after}` : ''}`, signal), schema, props.workspace, props.campaign, after) });
  return { query, cursors, setCursors };
}
export function MailContentReviews(props: Props) { return <ContentEditor key={`${props.userId}:${props.workspace}:${props.campaign}`} {...props}/>; }
function ContentEditor(props: Props) {
  const { userId, workspace, campaign, onPending } = props;
  const base = `/api/acquisition/workspaces/${workspace}/campaigns/${campaign}`;
  const path = `${base}/mail-content`, storageKey = `acquisition-content-request:v1:${userId}:${workspace}:${campaign}`;
  const [initial] = useState(() => {
    try { const raw = sessionStorage.getItem(storageKey); return { request: raw ? pendingSchema.parse(JSON.parse(raw)) : null, invalid: false }; }
    catch { return { request: null, invalid: true }; }
  });
  const [pending, setPending] = useState<Pending | null>(initial.request);
  const [open, setOpen] = useState(!!initial.request || initial.invalid);
  const [selected, setSelected] = useState<string | null>(initial.request?.content_id ?? null);
  const [baseVersion, setBaseVersion] = useState<number | null>(null);
  const [creative, setCreative] = useState(''), [route, setRoute] = useState(''), [company, setCompany] = useState('Hilltop Home Company');
  const [prepared, setPrepared] = useState<Preparation | null>(null), [preview, setPreview] = useState<Proof | null>(null);
  const [evidenceRef, setEvidenceRef] = useState(''), [evidenceHash, setEvidenceHash] = useState(''), [expires, setExpires] = useState('');
  const [note, setNote] = useState(''), [attested, setAttested] = useState(false), [lead, setLead] = useState('');
  const [leadCursors, setLeadCursors] = useState<(string | null)[]>([null]); const leadAfter = leadCursors.at(-1);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()); const inFlight = useRef(false);
  useEffect(() => { onPending(`${campaign}:content`, busy || !!pending || initial.invalid); }, [campaign, busy, pending, initial.invalid, onPending]);
  useEffect(() => { if (!open) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [open]);
  const access = useQuery({ queryKey: ['mail-content-access', userId, workspace], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => { const rows = await read(`/api/acquisition/workspaces/${workspace}/memberships`, signal);
      if (!Array.isArray(rows)) throw new Error('Access unavailable');
      return rows.some(r => r?.workspace_id === workspace && r.user_id === userId && r.status === 'active' && ['owner', 'admin'].includes(r.role)); } });
  const templates = usePage(`${base}/mail-templates`, template, props, open), destinations = usePage(`${base}/mail-destinations`, destination, props, open), reviews = usePage(path, history, props, open);
  const current = useQuery({ queryKey: ['mail-content-state', userId, workspace, campaign, selected], enabled: open && !!selected, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => { const s = scoped(state.parse(await read(`${path}/${selected}`, signal)), workspace, campaign); if (s.content_id !== selected) throw new Error('Review mismatch'); return s; } });
  const leads = useQuery({ queryKey: ['mail-content-leads', userId, workspace, leadAfter], enabled: open && current.data?.review_current === true, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => z.array(z.object({ lead_id: id, property_id: id.nullable(), property_address: z.string(), city: z.string() })).max(20).parse(await read(`/api/acquisition/workspaces/${workspace}/leads?limit=20${leadAfter ? `&after=${leadAfter}` : ''}`, signal)) });
  const locked = busy || !!pending || initial.invalid;
  const editable = access.data === true && !access.isFetching && !access.isError && !locked;
  const ready = !!current.data && !current.isFetching && !current.isError;
  const loaded = !selected || (ready && baseVersion === current.data?.version);
  const preparedCurrent = !!prepared && prepared.snapshot.template.creative_id === creative && prepared.snapshot.destination.review_id === route && prepared.snapshot.company_name === company.trim() && Date.parse(prepared.destination_valid_until) > now;
  const approvalBody = { id: campaign, expected_version: selected ? baseVersion : 0, action: 'approved', creative_id: creative, destination_review_id: route, company_name: company.trim(), preparation_hash: prepared?.preparation_hash, evidence_ref: evidenceRef, evidence_hash: evidenceHash, expires_at: expires, note };
  const approve = editable && loaded && preparedCurrent && attested && pendingSchema.safeParse({ content_id: selected ?? campaign, review: approvalBody }).success
    && Date.parse(expires) > now && Date.parse(expires) <= Date.parse(prepared!.destination_valid_until);
  const withdraw = editable && ready && current.data!.version < 1000000000 && current.data!.latest_review?.action === 'approved' && note.trim().length >= 20 && note.length <= 2000;
  function invalidate() { setPrepared(null); setPreview(null); setAttested(false); }
  function inspect(contentId: string | null) { setSelected(contentId); setBaseVersion(null); invalidate(); setNote(''); setMessage(''); setLead(''); }
  function refresh() { invalidate(); void access.refetch(); void templates.query.refetch(); void destinations.query.refetch(); void reviews.query.refetch(); if (selected) void current.refetch(); }
  async function prepare() {
    if (inFlight.current || !editable || !loaded || !creative || !route || !company.trim()) return;
    inFlight.current = true; setBusy(true); invalidate(); setMessage('');
    try { const p = preparation.parse(await post(`${path}/prepare`, { creative_id: creative, destination_review_id: route, company_name: company.trim() })); scoped(p.snapshot, workspace, campaign);
      if (p.snapshot.template.creative_id !== creative || p.snapshot.destination.review_id !== route || p.snapshot.company_name !== company.trim() || Date.parse(p.destination_valid_until) <= Date.now()) throw new Error('Preparation mismatch');
      setPrepared(p); setMessage('Content prepared for your review. This is not an approval or a mailing.');
    } catch { setMessage('Content could not be prepared. Refresh sources and choose a current message and verified response destination.'); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function save(action: 'approved' | 'withdrawn') {
    if (inFlight.current || initial.invalid || (!pending && !(action === 'approved' ? approve : withdraw))) return;
    const request = pending ?? pendingSchema.parse({ content_id: selected ?? crypto.randomUUID(), review: action === 'approved' ? { ...approvalBody, id: crypto.randomUUID() } : { id: crypto.randomUUID(), expected_version: current.data!.version, action, note } });
    const retrying = !!pending; let sent = false; inFlight.current = true; setBusy(true); setMessage(''); setPreview(null);
    try { sessionStorage.setItem(storageKey, JSON.stringify(request)); setPending(request); sent = true;
      const r = await post(`${path}/${request.content_id}/reviews`, request.review);
      if (r?.review_id !== request.review.id || r.workspace_id !== workspace || r.content_id !== request.content_id || r.version !== request.review.expected_version + 1 || typeof r.duplicate !== 'boolean' || r.execution_authorized !== false) throw new Error('Unconfirmed receipt');
      sessionStorage.removeItem(storageKey); setPending(null); setSelected(request.content_id); setBaseVersion(null); invalidate(); setNote('');
      setMessage('Content decision recorded. Check current status before preparing an internal preview. Sending mail requires separate approval.');
      void reviews.query.refetch(); if (selected === request.content_id) void current.refetch();
    } catch (error) {
      if (!retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        try { sessionStorage.removeItem(storageKey); setPending(null); } catch { /* Retain exact request if cleanup fails. */ }
        invalidate(); setBaseVersion(null); setMessage('Decision rejected. Refresh and load the current review before trying again.'); void access.refetch(); if (selected) void current.refetch();
      } else setMessage(sent || retrying ? 'The decision is unconfirmed. Retry the exact saved request to reconcile it; it is retained in this browser tab.' : 'Browser storage is unavailable. No decision was sent.');
    } finally { inFlight.current = false; setBusy(false); }
  }
  async function renderPreview() {
    const s = current.data;
    if (inFlight.current || locked || !ready || !s?.review_current || !lead || !leads.data?.some(l => l.lead_id === lead && l.property_id)) return;
    inFlight.current = true; setBusy(true); setPreview(null); setMessage('');
    try { const p = scoped(proof.parse(await post(`${path}/${selected}/proof`, { lead_id: lead })), workspace, campaign);
      if (p.content_id !== selected || p.content_version !== s.version || p.review_id !== s.latest_review?.id || p.preparation_hash !== s.latest_review.preparation_hash || p.lead_id !== lead
        || p.property_id !== leads.data.find(l => l.lead_id === lead)?.property_id || Date.parse(p.content_valid_until) <= Date.now() || Date.parse(p.source_checked_at) > Date.now() + 5000 || Date.now() - Date.parse(p.source_checked_at) > 30000) throw new Error('Preview mismatch');
      setPreview(p);
    } catch { setMessage('Preview unavailable or the reviewed content changed. Refresh current status and confirm the property has a complete canonical address.'); void current.refetch(); }
    finally { inFlight.current = false; setBusy(false); }
  }
  function pages<T extends { id: string; workspace_id: string; campaign_id: string }>(source: ReturnType<typeof usePage<T>>, label: string) {
    return <nav aria-label={`${label} pages`} className="flex gap-2"><button className={button} disabled={locked || source.query.isFetching || source.cursors.length === 1} onClick={() => source.setCursors(v => v.slice(0, -1))}>Previous {label}</button><button className={button} disabled={locked || source.query.isFetching || source.query.isError || !source.query.data?.next_after} onClick={() => source.setCursors(v => [...v, source.query.data!.next_after])}>Next {label}</button></nav>;
  }
  const visiblePreview = preview && ready && current.data?.review_current && preview.review_id === current.data.latest_review?.id && preview.content_version === current.data.version && preview.lead_id === lead && Date.parse(preview.content_valid_until) > now;
  return <section aria-label="Mail content review" className="mt-3 space-y-3">
    <button className={button} aria-expanded={open} disabled={locked} onClick={() => setOpen(v => !v)}>{open ? 'Hide content review' : 'Review mail content'}</button>
    {open && <>
      <p className="text-sm text-gray-600">Choose a saved message and response destination, review the wording, then record a content decision. Content approval does not authorize mailing.</p>
      <button className={button} disabled={locked} onClick={refresh}>Refresh content sources and status</button>
      {initial.invalid && <p role="alert">Saved content request cannot be read. Reconcile it before creating another review.</p>}
      {!editable && !locked && <p>Content decisions require current owner or administrator access. Existing records and internal previews remain available to authorized readers.</p>}
      <div className="space-y-2"><h5 className="font-semibold text-[#1B3A5C]">Previous content decisions</h5>
        {reviews.query.isFetching ? <p role="status">Loading content history…</p> : reviews.query.isError ? <p role="alert">Content history could not be verified.</p> : <ul>{reviews.query.data?.items.map(r => <li key={r.id} className="border-t py-2"><span>{r.company_name} · Version {r.version} · Recorded {r.action} · {r.created_at}</span><button className={`${button} break-all`} disabled={locked} onClick={() => inspect(r.content_id)}>Inspect content {r.content_id}</button></li>)}</ul>}
        <p className="text-sm text-gray-600">History pages use references, not recency. Inspect current status before relying on a recorded approval.</p>{pages(reviews, 'content decisions')}
      </div>
      {pending && <p className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm">Saved decision awaiting confirmation: {pending.review.action === 'approved' ? 'content approval' : 'withdrawal'} for version {pending.review.expected_version + 1}. Use the exact retry below before changing this review.</p>}
      {selected && <div className="rounded-lg border bg-white p-3 space-y-2">
        {current.isFetching ? <p role="status">Checking current content…</p> : current.isError ? <p role="alert">Current content could not be verified.</p> : current.data && <p>Current content: {current.data.status.replaceAll('_', ' ')} · Version {current.data.version} · Checked {current.data.checked_at}</p>}
        {!loaded && !locked && <p className="text-sm text-gray-600">To revise this content, load the current version below and prepare it again. Internal property preview is available below only while the content is approved.</p>}
        <button className={button} disabled={!editable || !ready || !current.data?.latest_review} onClick={() => { const r = current.data!.latest_review!; setBaseVersion(r.version); setCreative(r.creative_id); setRoute(r.destination_review_id); setCompany(r.company_name); setEvidenceRef(''); setEvidenceHash(''); setExpires(''); setNote(''); invalidate(); }}>Load current content for review</button>
        <button className={button} disabled={locked} onClick={() => inspect(null)}>Start separate content review</button>
      </div>}
      <fieldset disabled={!editable || !loaded} className="space-y-3"><legend className="font-semibold text-[#1B3A5C]">Prepare the wording</legend>
        <label>Saved message<select className={input} value={creative} disabled={templates.query.isFetching || templates.query.isError || !editable || !loaded} onChange={e => { setCreative(e.target.value); invalidate(); }}><option value="">Choose a message version</option>{creative && !templates.query.data?.items.some(r => r.id === creative) && <option value={creative}>Previously selected message (refresh to verify)</option>}{templates.query.data?.items.map(r => <option key={r.id} value={r.id}>{r.name} · Version {r.acquisition_template_version} · {r.acquisition_mail_format}</option>)}</select></label>
        {templates.query.isError && <p role="alert">Message versions could not be verified.</p>}{pages(templates, 'message versions')}
        <label>Reviewed response destination<select className={input} value={route} disabled={destinations.query.isFetching || destinations.query.isError || !editable || !loaded} onChange={e => { setRoute(e.target.value); invalidate(); }}><option value="">Choose a destination review</option>{route && !destinations.query.data?.items.some(r => r.id === route) && <option value={route}>Previously selected destination (refresh to verify)</option>}{destinations.query.data?.items.map(r => <option key={r.id} value={r.id} disabled={r.action !== 'approved'}>{r.value} · Version {r.version} · Recorded {r.action}</option>)}</select></label>
        {destinations.query.isError && <p role="alert">Destination reviews could not be verified.</p>}{pages(destinations, 'response destinations')}
        <label>Company name printed on mail<input className={input} maxLength={200} value={company} onChange={e => { setCompany(e.target.value); invalidate(); }}/></label>
        <button className={button} disabled={!editable || !loaded || !creative || !route || !company.trim()} onClick={() => { void prepare(); }}>Prepare content for review</button>
      </fieldset>
      {prepared && <div className="rounded-lg border bg-white p-4 space-y-2"><h5 className="font-semibold">Prepared wording — property placeholder</h5><pre className="whitespace-pre-wrap break-words font-sans text-sm">{prepared.snapshot.template.body.replace(/\{\{(company_name|property_address|tracking_phone|tracking_url)\}\}/g, (_, token: string) => token === 'company_name' ? prepared.snapshot.company_name : token === 'property_address' ? '[Property address]' : prepared.snapshot.destination.value)}</pre><p className="text-sm">Destination evidence expires: {prepared.destination_valid_until}. This view uses a property placeholder. An approved internal preview uses the selected property.</p>{!preparedCurrent && <p role="alert">Preparation expired or changed. Prepare the content again.</p>}</div>}
      <fieldset disabled={!editable || !loaded || !preparedCurrent} className="space-y-3"><legend className="font-semibold text-[#1B3A5C]">Record the content review</legend>
        <details><summary className="cursor-pointer">Retained review evidence</summary><p className="text-sm">Use the reference and SHA-256 digest of your retained evidence. This form does not upload or verify that artifact; protected evidence resolution remains a separate release requirement.</p>
          <label>Content evidence reference<input className={input} value={evidenceRef} onChange={e => setEvidenceRef(e.target.value)}/></label><label>Content evidence SHA-256 digest<input className={input} maxLength={64} value={evidenceHash} onChange={e => setEvidenceHash(e.target.value)}/></label></details>
        <label>Content approval expires at (ISO date with time zone)<input className={input} placeholder="2026-11-01T12:00:00-06:00" value={expires} onChange={e => setExpires(e.target.value)}/></label>
        <label className="block"><input type="checkbox" checked={attested} onChange={e => setAttested(e.target.checked)}/> I reviewed this wording, company name and response destination against the retained evidence.</label>
      </fieldset>
      <label className="block">Content review or withdrawal reason<textarea className={input} disabled={!editable} maxLength={2000} value={note} onChange={e => setNote(e.target.value)}/></label><p className="text-sm text-gray-600">Explain the decision in at least 20 characters. Approval expiry cannot exceed destination evidence expiry.</p>
      {pending ? <button className={button} disabled={busy || initial.invalid} onClick={() => { void save(pending.review.action); }}>Retry exact content decision</button> : <div className="flex flex-wrap gap-2"><button className={`${button} bg-[#1B3A5C] text-white`} disabled={!approve} onClick={() => { void save('approved'); }}>Record content approval</button><button className={button} disabled={!withdraw} onClick={() => { void save('withdrawn'); }}>Withdraw content approval</button></div>}
      {selected && current.data?.review_current && <div className="rounded-lg border bg-white p-4 space-y-3"><h5 className="font-semibold text-[#1B3A5C]">Internal property preview</h5><p className="text-sm">Uses the current approved content and the property's canonical address. It does not verify postal delivery, recipient permission or a vendor proof.</p>
        <label>Preview property<select className={input} value={lead} disabled={locked || !ready || leads.isFetching || leads.isError} onChange={e => { setLead(e.target.value); setPreview(null); }}><option value="">Choose an enrolled property</option>{leads.data?.map(l => <option key={l.lead_id} value={l.lead_id} disabled={!l.property_id}>{l.property_address} · {l.city}</option>)}</select></label>
        {leads.isError && <p role="alert">Enrolled properties could not be loaded.</p>}
        <nav aria-label="Preview property pages"><button className={button} disabled={locked || leads.isFetching || leadCursors.length === 1} onClick={() => { setLead(''); setPreview(null); setLeadCursors(v => v.slice(0, -1)); }}>Previous properties</button><button className={button} disabled={locked || leads.isFetching || leads.isError || leads.data?.length !== 20} onClick={() => { setLead(''); setPreview(null); setLeadCursors(v => [...v, leads.data!.at(-1)!.lead_id]); }}>Next properties</button></nav>
        <button className={button} disabled={locked || !ready || !lead || leads.isFetching || leads.isError} onClick={() => { void renderPreview(); }}>Prepare internal preview</button>
        {visiblePreview && <div><p className="font-semibold">Internal content preview — not ready for fulfillment</p><pre className="whitespace-pre-wrap break-words font-sans text-sm">{preview.text}</pre><p className="text-sm">Prepared {preview.prepared_at} · Content valid until {preview.content_valid_until}</p></div>}
      </div>}
      {busy && <p role="status">Checking or recording content…</p>}{message && <p role="status">{message}</p>}
    </>}
  </section>;
}
