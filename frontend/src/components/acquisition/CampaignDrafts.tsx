import { MailDestinations } from '@/components/acquisition/MailDestinations';
import { MailTemplates } from '@/components/acquisition/MailTemplates';
import { CampaignCosts } from '@/components/acquisition/CampaignCosts';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type Draft = { id: string; name: string; channel: string; budget_cents: number; currency: 'USD' };
type Campaign = { id: string; workspace_id: string; name: string; status: string; acquisition_channel: string; acquisition_budget_cents: number; acquisition_currency: string };
const channels: Record<string, string> = { facebook: 'Facebook', inbound_voice: 'Inbound voice', direct_mail: 'Direct mail', online_offer: 'Online offer requests', human_voice: 'Human caller', agency_voice: 'Calling agency' };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full border rounded p-2';
const validBudget = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 && value <= 100000000000;
function budgetCents(value: string): number | null {
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(value)) return null;
  const [dollars, cents = ''] = value.split('.');
  const result = Number(dollars) * 100 + Number(cents.padEnd(2, '0'));
  return validBudget(result) ? result : null;
}
function validDraft(value: unknown): value is Draft {
  if (!value || typeof value !== 'object') return false;
  const row = value as Draft;
  return uuid.test(row.id) && typeof row.name === 'string' && row.name === row.name.trim() && row.name.length > 0 && row.name.length <= 200
    && Object.hasOwn(channels, row.channel) && validBudget(row.budget_cents) && row.currency === 'USD';
}
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }

export function CampaignDrafts({ userId, workspace, onPending }: { userId: string; workspace: string; onPending: (pending: boolean) => void }) {
  const path = `/api/acquisition/workspaces/${workspace}/campaigns`;
  const storageKey = `acquisition-campaign-request:v1:${userId}:${workspace}`;
  const [initial] = useState(() => {
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (!stored) return { request: null, error: false };
      const value: unknown = JSON.parse(stored);
      if (!validDraft(value)) throw new Error('Invalid saved request');
      return { request: value, error: false };
    } catch { return { request: null, error: true }; }
  });
  const [pending, setPending] = useState<Draft | null>(initial.request);
  const [name, setName] = useState(initial.request?.name ?? '');
  const [channel, setChannel] = useState(initial.request?.channel ?? 'facebook');
  const [budget, setBudget] = useState(initial.request ? (initial.request.budget_cents / 100).toFixed(2) : '');
  const [busy, setBusy] = useState(false); const inFlight = useRef(false);
  const [feedback, setFeedback] = useState('');
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const after = cursors[cursors.length - 1];
  useEffect(() => { onPending(!!pending || initial.error); }, [pending, initial.error, onPending]);
  const access = useQuery({ queryKey: ['campaign-access', userId, workspace], retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => {
      const rows = await read(`/api/acquisition/workspaces/${workspace}/memberships`, signal);
      if (!Array.isArray(rows)) throw new Error('Membership unavailable');
      return rows.some(row => row?.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin'].includes(row.role));
    } });
  const list = useQuery({ queryKey: ['campaign-drafts', userId, workspace, after], retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }): Promise<{ items: Campaign[]; next_after: string | null }> => {
      const page = await read(`${path}?limit=20${after ? `&after=${after}` : ''}`, signal);
      if (!Array.isArray(page?.items) || page.items.length > 20 || !page.items.every((row: Campaign) => row && uuid.test(row.id) && row.workspace_id === workspace
        && typeof row.name === 'string' && row.status === 'draft' && Object.hasOwn(channels, row.acquisition_channel)
        && validBudget(row.acquisition_budget_cents) && row.acquisition_currency === 'USD')
        || !(page.next_after === null || (typeof page.next_after === 'string' && uuid.test(page.next_after) && page.next_after === page.items.at(-1)?.id && page.next_after !== after)))
        throw new Error('Campaign records could not be verified.');
      return page;
    } });
  const cents = budgetCents(budget);
  const canCreate = access.data === true && !access.isError && !access.isFetching && !initial.error;
  const valid = canCreate && name.trim().length > 0 && name.trim().length <= 200 && cents !== null;
  async function save() {
    if (inFlight.current || initial.error || (!pending && !valid)) return;
    inFlight.current = true; setBusy(true); setFeedback('');
    const retrying = !!pending;
    const request: Draft = pending ?? { id: crypto.randomUUID(), name: name.trim(), channel, budget_cents: cents!, currency: 'USD' };
    let sent = false;
    try {
      // Persist before sending so reload/navigation cannot replace an uncertain request.
      sessionStorage.setItem(storageKey, JSON.stringify(request));
      setPending(request); sent = true;
      const result = await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
      if (result?.id !== request.id || result.workspace_id !== workspace || result.status !== 'draft' || result.channel !== request.channel
        || result.budget_cents !== request.budget_cents || result.currency !== request.currency || typeof result.duplicate !== 'boolean' || result.execution_authorized !== false)
        throw new Error('Unconfirmed campaign result');
      sessionStorage.removeItem(storageKey);
      setPending(null); setName(''); setBudget(''); setFeedback('Campaign draft saved. Publishing and spending require separate approval.');
      setCursors([null]); void list.refetch();
    } catch (error) {
      const rejected = !retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (rejected) {
        try { sessionStorage.removeItem(storageKey); setPending(null); } catch { /* Preserve the exact request if storage cannot be cleared. */ }
        setFeedback('Draft creation was rejected. Check workspace access and acquisition activation before retrying.'); void access.refetch();
      } else setFeedback(sent || retrying ? 'The result is unconfirmed. Retry the exact draft request to reconcile it. Your request is retained in this browser tab.'
        : 'Browser session storage is unavailable. No request was sent. Enable session storage before saving a draft.');
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Campaign drafts" className="border rounded-xl bg-white p-5 space-y-4">
    <div className="flex flex-wrap justify-between gap-2"><h2 className="text-lg font-semibold">Campaign drafts</h2><button className={button} disabled={list.isFetching} onClick={() => { void list.refetch(); void access.refetch(); }}>Refresh campaigns</button></div>
    <p className="text-sm text-gray-600">Plan a campaign budget. Channels activate in the approved rollout order, beginning with Facebook. Drafts do not publish ads, fund campaigns or authorize outreach.</p>
    {list.isFetching ? <p role="status">Loading campaign drafts…</p> : list.isError ? <p role="alert">Campaign records could not be verified.</p> : <ul className="space-y-2">{list.data?.items.map(row => <li className="border rounded p-3" key={row.id}><strong>{row.name}</strong><p>{channels[row.acquisition_channel]} · Draft · Budget {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(row.acquisition_budget_cents / 100)}</p><p className="text-sm text-gray-600">Actual spend requires reviewed cost evidence.</p><p className="text-xs break-all">Reference: {row.id}</p>{row.acquisition_channel === 'direct_mail' && <><MailTemplates userId={userId} workspace={workspace} campaign={row.id}/><MailDestinations userId={userId} workspace={workspace} campaign={row.id}/></>}
{row.acquisition_channel === 'facebook' && <CampaignCosts userId={userId} workspace={workspace} campaign={row.id}/>}</li>)}</ul>}
    {list.data?.items.length === 0 && !list.isFetching && !list.isError && <p>No campaign drafts on this page.</p>}
    <nav aria-label="Campaign pages" className="flex gap-2"><button className={button} disabled={cursors.length === 1 || list.isFetching} onClick={() => setCursors(value => value.slice(0, -1))}>Previous campaigns</button><button className={button} disabled={!list.data?.next_after || list.isError || list.isFetching} onClick={() => { if (list.data?.next_after) setCursors(value => [...value, list.data!.next_after]); }}>Next campaigns</button></nav>
    {initial.error && <p role="alert">A saved draft request could not be read. Resolve browser storage access or reconcile the saved campaign request before creating another draft in this tab.</p>}
    {!canCreate && !pending && !initial.error && <p className="text-sm">Creating drafts requires active owner or administrator access.</p>}
    <fieldset disabled={!canCreate || busy || !!pending} className="grid gap-3 md:grid-cols-3"><legend className="font-semibold mb-2">New campaign draft</legend>
      <label>Campaign name<input className={input} value={name} maxLength={200} onChange={event => setName(event.target.value)} /></label>
      <label>Acquisition channel<select className={input} value={channel} onChange={event => setChannel(event.target.value)}>{Object.entries(channels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>Planned budget (USD)<input className={input} inputMode="decimal" value={budget} onChange={event => setBudget(event.target.value)} aria-describedby="campaign-budget-help" /></label>
    </fieldset>
    <p id="campaign-budget-help" className="text-sm">Use dollars with up to two decimal places. The budget does not establish actual spend or approve payment.</p>
    <button className={button} disabled={busy || initial.error || (!pending && !valid)} onClick={() => { void save(); }}>{busy ? 'Saving draft…' : pending ? 'Retry exact draft request' : 'Save campaign draft'}</button>
    {pending && <p className="text-xs break-all">Pending request: {pending.id}</p>}
    {feedback && <p role="status">{feedback}</p>}
  </section>;
}
