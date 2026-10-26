import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SourceAttribution } from './SourceAttribution';
import { ApiError, apiFetch } from '@/lib/api';

type Decision = { id: string; expected_sequence: number; preparation_hash: string; action: 'link' | 'revoke'; campaign_id: string | null; ad_account_id: string | null; evidence_ref: string; review_note: string };
type Review = { id: string; workspace_id: string; integration_id: string; external_campaign_id: string; sequence: number; action: 'link' | 'revoke'; campaign_id: string | null; ad_account_id: string | null; evidence_ref: string; review_note: string };
type State = { workspace_id: string; intake_id: string; integration_id: string; page_id: string; external_campaign_id: string; preparation_hash: string; sequence: number; latest_review: Review | null; link_current: boolean; internal_campaign_id: string | null; execution_authorized: false };
type Campaign = { id: string; workspace_id: string; name: string; acquisition_channel: string };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const hash = /^[a-f0-9]{64}$/;
const numeric = /^[0-9]{1,200}$/;
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded border p-2';
const options = { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false } as const;
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }
function validDecision(value: Decision) {
  return value && uuid.test(value.id) && Number.isSafeInteger(value.expected_sequence) && value.expected_sequence >= 0 && hash.test(value.preparation_hash)
    && typeof value.evidence_ref === 'string' && value.evidence_ref.trim().length >= 10 && value.evidence_ref.length <= 500
    && typeof value.review_note === 'string' && value.review_note.trim().length >= 20 && value.review_note.length <= 2000
    && (value.action === 'link' ? typeof value.campaign_id === 'string' && uuid.test(value.campaign_id) && typeof value.ad_account_id === 'string' && numeric.test(value.ad_account_id)
      : value.action === 'revoke' && value.campaign_id === null && value.ad_account_id === null);
}
function validReview(value: Review, workspace: string, integration: string, external: string) {
  return value && uuid.test(value.id) && value.workspace_id === workspace && value.integration_id === integration && value.external_campaign_id === external
    && Number.isSafeInteger(value.sequence) && value.sequence > 0 && typeof value.evidence_ref === 'string' && typeof value.review_note === 'string'
    && (value.action === 'link' ? typeof value.campaign_id === 'string' && uuid.test(value.campaign_id) && typeof value.ad_account_id === 'string' && numeric.test(value.ad_account_id)
      : value.action === 'revoke' && value.campaign_id === null && value.ad_account_id === null);
}
async function readState(path: string, workspace: string, intake: string, signal?: AbortSignal): Promise<State> {
  const state = await read(path, signal) as State;
  if (!state || state.workspace_id !== workspace || state.intake_id !== intake || !uuid.test(state.integration_id) || typeof state.page_id !== 'string'
    || typeof state.external_campaign_id !== 'string' || !numeric.test(state.external_campaign_id) || !hash.test(state.preparation_hash) || !Number.isSafeInteger(state.sequence) || state.sequence < 0
    || typeof state.link_current !== 'boolean' || state.execution_authorized !== false
    || (state.sequence === 0 ? state.latest_review !== null : !validReview(state.latest_review!, workspace, state.integration_id, state.external_campaign_id) || state.latest_review!.sequence !== state.sequence)
    || (state.link_current ? state.latest_review?.action !== 'link' || state.internal_campaign_id !== state.latest_review.campaign_id : state.internal_campaign_id !== null)) throw new Error('Campaign evidence unavailable');
  return state;
}

export function CampaignLinkReview({ userId, workspace, intake, locked, onPending }: { userId: string; workspace: string; intake: string; locked: boolean; onPending: (pending: boolean) => void }) {
  const base = `/api/acquisition/workspaces/${workspace}`; const path = `${base}/intakes/${intake}`;
  const statePath = `${path}/campaign-link-state`;
  const storageKey = `campaign-link-review:v1:${userId}:${workspace}:${intake}`;
  const [initial] = useState(() => {
    try { const raw = sessionStorage.getItem(storageKey); if (!raw) return { request: null, invalid: false }; const value = JSON.parse(raw) as Decision;
      if (!validDecision(value)) throw new Error('Invalid request'); return { request: value, invalid: false };
    } catch { return { request: null, invalid: true }; }
  });
  const [pending, setPending] = useState<Decision | null>(initial.request);
  const [action, setAction] = useState<'link' | 'revoke'>(initial.request?.action ?? 'link');
  const [campaign, setCampaign] = useState(initial.request?.campaign_id ?? '');
  const [account, setAccount] = useState(initial.request?.ad_account_id ?? '');
  const [evidence, setEvidence] = useState(initial.request?.evidence_ref ?? '');
  const [note, setNote] = useState(initial.request?.review_note ?? '');
  const [ack, setAck] = useState(false); const [busy, setBusy] = useState(false); const inFlight = useRef(false);
  const [feedback, setFeedback] = useState(''); const [after, setAfter] = useState<string | null>(null); const [before, setBefore] = useState<number | null>(null);
  const [sourcePending, setSourcePending] = useState(false);
  const [sourceRevision, setSourceRevision] = useState(0);
  useEffect(() => { onPending(sourcePending || !!pending || busy || initial.invalid); }, [sourcePending, pending, busy, initial.invalid, onPending]);
  const state = useQuery({ ...options, queryKey: ['campaign-link-state', userId, workspace, intake], queryFn: ({ signal }) => readState(statePath, workspace, intake, signal) });
  const access = useQuery({ ...options, queryKey: ['campaign-link-access', userId, workspace], queryFn: async ({ signal }) => {
    const rows = await read(`${base}/memberships`, signal);
    return Array.isArray(rows) && rows.some(row => row?.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin'].includes(row.role));
  } });
  const campaigns = useQuery({ ...options, queryKey: ['campaign-link-choices', userId, workspace, after], queryFn: async ({ signal }): Promise<{ items: Campaign[]; next_after: string | null }> => {
    const page = await read(`${base}/campaigns?limit=20${after ? `&after=${after}` : ''}`, signal);
    if (!Array.isArray(page?.items) || page.items.length > 20 || !page.items.every((row: Campaign) => row && uuid.test(row.id) && row.workspace_id === workspace && typeof row.name === 'string' && typeof row.acquisition_channel === 'string')
      || !(page.next_after === null || (uuid.test(page.next_after) && page.next_after === page.items.at(-1)?.id && page.next_after !== after))) throw new Error('Campaign choices unavailable');
    return page;
  } });
  const history = useQuery({ ...options, queryKey: ['campaign-link-history', userId, workspace, intake, before, state.data?.integration_id, state.data?.external_campaign_id], enabled: !!state.data && !state.isError,
    queryFn: async ({ signal }): Promise<Review[]> => {
      const rows = await read(`${path}/campaign-link-reviews?limit=20${before ? `&before=${before}` : ''}`, signal);
      if (!Array.isArray(rows) || rows.length > 20 || !rows.every((row, index) => validReview(row, workspace, state.data!.integration_id, state.data!.external_campaign_id)
        && (!before || row.sequence < before) && (index === 0 || rows[index - 1].sequence > row.sequence))) throw new Error('Campaign history unavailable');
      return rows;
    } });
  const available = !sourcePending && !locked && !initial.invalid && access.data === true && !access.isFetching && !access.isError && !!state.data && !state.isFetching && !state.isError && !!history.data && !history.isFetching && !history.isError;
  const targetValid = action === 'revoke' ? state.data?.latest_review?.action === 'link' : state.data?.latest_review?.action !== 'link'
    && !campaigns.isFetching && !campaigns.isError && campaigns.data?.items.some(row => row.id === campaign && row.acquisition_channel === 'facebook') && numeric.test(account);
  const valid = available && targetValid && ack && evidence.trim().length >= 10 && note.trim().length >= 20;
  async function save() {
    if (inFlight.current || sourcePending || locked || initial.invalid || (!pending && !valid)) return;
    inFlight.current = true; setBusy(true); setFeedback(''); let request = pending; const retrying = !!pending; let sent = false;
    try {
      if (!request) {
        const fresh = await readState(statePath, workspace, intake);
        if (fresh.sequence !== state.data!.sequence || fresh.preparation_hash !== state.data!.preparation_hash || fresh.integration_id !== state.data!.integration_id || fresh.external_campaign_id !== state.data!.external_campaign_id) throw new Error('Review changed');
        request = { id: crypto.randomUUID(), expected_sequence: fresh.sequence, preparation_hash: fresh.preparation_hash, action,
          campaign_id: action === 'link' ? campaign : null, ad_account_id: action === 'link' ? account : null, evidence_ref: evidence.trim(), review_note: note.trim() };
      }
      sessionStorage.setItem(storageKey, JSON.stringify(request)); setPending(request); sent = true;
      const result = await (await apiFetch(`${path}/campaign-link-reviews`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
      if (result?.review_id !== request.id || result.sequence !== request.expected_sequence + 1 || typeof result.duplicate !== 'boolean' || result.execution_authorized !== false) throw new Error('Unconfirmed reply');
      sessionStorage.removeItem(storageKey); setPending(null); setAck(false); setNote(''); setEvidence(''); setBefore(null);
      setSourceRevision(value => value + 1); setFeedback('Campaign review recorded. No advertising or outreach was authorized.'); void state.refetch(); void history.refetch();
    } catch (error) {
      const rejected = !retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (rejected) { try { sessionStorage.removeItem(storageKey); setPending(null); } catch { /* Keep the exact request. */ } }
      setFeedback(rejected ? 'Review rejected. Refresh the evidence and verify MFA and workspace access.' : sent || retrying ? 'Result unconfirmed. Retry the exact campaign review; it is retained in this browser tab.' : 'Review evidence changed or browser storage is unavailable. No review was sent. Refresh before reviewing again.');
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Campaign attribution review" className="rounded border p-4 space-y-3">
    <h4 className="font-semibold">Campaign attribution review</h4>
    <p className="text-sm">An owner or administrator with MFA must review Page, advertising-account and campaign ownership. Recorded evidence is a human review, not provider verification.</p>
    {state.isError ? <p role="alert">Campaign evidence unavailable. This inquiry may lack an external campaign ID.</p> : state.isFetching ? <p>Loading campaign evidence…</p> : state.data && <div className="text-sm break-all"><p>Facebook Page: {state.data.page_id}</p><p>External campaign: {state.data.external_campaign_id}</p><p>Review sequence: {state.data.sequence}</p><p>{state.data.link_current ? `Current reviewed campaign: ${state.data.internal_campaign_id}` : 'No current reviewed campaign link.'}</p></div>}
    {initial.invalid && <p role="alert">Saved review could not be read. Reconcile the earlier request before creating another review in this tab.</p>}
    <fieldset disabled={!available || busy || !!pending} className="space-y-3">
      <label>Campaign decision<select className={input} value={action} onChange={event => { setAction(event.target.value as 'link' | 'revoke'); setAck(false); }}><option value="link">Link campaign</option><option value="revoke">Revoke campaign link</option></select></label>
      {action === 'link' && <>
        <label>Workspace Facebook campaign<select className={input} value={campaign} onChange={event => { setCampaign(event.target.value); setAck(false); }}><option value="">Select a reviewed campaign</option>{campaigns.data?.items.filter(row => row.acquisition_channel === 'facebook').map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        {campaigns.isError && <p role="alert">Workspace campaign choices unavailable.</p>}
        <div className="flex gap-2"><button className={button} disabled={!after || campaigns.isFetching} onClick={() => { setAfter(null); setCampaign(''); }}>First campaign choices</button><button className={button} disabled={!campaigns.data?.next_after || campaigns.isFetching || campaigns.isError} onClick={() => { setAfter(campaigns.data!.next_after); setCampaign(''); }}>More campaign choices</button></div>
        <label>Reviewed advertising account ID<input className={input} inputMode="numeric" maxLength={200} value={account} onChange={event => { setAccount(event.target.value); setAck(false); }} /></label>
        {state.data?.latest_review?.action === 'link' && <p>Revoke the prior campaign link before recording a correction, even if it is no longer current.</p>}
      </>}
      <label>Campaign ownership evidence reference<input className={input} maxLength={500} value={evidence} onChange={event => { setEvidence(event.target.value); setAck(false); }} /></label>
      <label>Campaign review note<textarea className={input} maxLength={2000} value={note} onChange={event => { setNote(event.target.value); setAck(false); }} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />I reviewed this Page, external campaign, account ownership and the evidence for this decision.</label>
    </fieldset>
    <div className="flex flex-wrap gap-2"><button className={button} disabled={sourcePending || busy || locked || initial.invalid || (!pending && !valid)} onClick={() => { void save(); }}>{busy ? 'Recording campaign review…' : pending ? 'Retry exact campaign review' : 'Record campaign review'}</button><button className={button} disabled={busy} onClick={() => { setAck(false); setSourceRevision(value => value + 1); void state.refetch(); void history.refetch(); void access.refetch(); void campaigns.refetch(); }}>Refresh campaign evidence</button></div>
    {pending && <p className="text-xs break-all">Pending campaign review: {pending.id}</p>}{feedback && <p role="status">{feedback}</p>}
    <details><summary>Campaign link history</summary>{history.isError ? <p role="alert">Campaign history unavailable.</p> : history.isFetching ? <p>Loading campaign history…</p> : <ol>{history.data?.map(row => <li key={row.id} className="text-sm border-b py-2 break-words"><strong>{row.sequence}. {row.action}</strong><p>{row.review_note}</p><p>Evidence: {row.evidence_ref}</p>{row.campaign_id && <p>Campaign: {row.campaign_id} · Ad account: {row.ad_account_id}</p>}</li>)}</ol>}
      <button className={button} disabled={history.isFetching || before === null} onClick={() => setBefore(null)}>Latest campaign reviews</button><button className={button} disabled={history.isFetching || history.isError || history.data?.length !== 20} onClick={() => setBefore(history.data!.at(-1)!.sequence)}>Older campaign reviews</button>
    </details>
    <SourceAttribution userId={userId} workspace={workspace} intake={intake} revision={sourceRevision} locked={locked || busy || !!pending || initial.invalid} onPending={setSourcePending} />
  </section>;
}
