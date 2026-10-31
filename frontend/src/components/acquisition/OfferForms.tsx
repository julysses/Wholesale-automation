import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type Definition = { form_key: string; version: string; privacy_acknowledged: string; human_callback_requested: string; email_reply_requested: string };
type Draft = { id: string; expected_revision: number; definition: Definition };
type Version = { id: string; workspace_id: string; campaign_id: string; acquisition_form_key: string; acquisition_form_revision: number; acquisition_form_version: string; acquisition_form_definition: Definition; acquisition_definition_hash: string; created_at: string; active: false; send_confirmation_sms: false; send_confirmation_email: false };
type Props = { userId: string; workspace: string; campaign: string; onPending?: (key: string, pending: boolean) => void };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const label = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/;
const hash = /^[0-9a-f]{64}$/;
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded-lg border border-gray-300 bg-white p-2 mt-1';
const wordingKeys = ['privacy_acknowledged', 'human_callback_requested', 'email_reply_requested'] as const;
function object(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value); }
function definition(value: unknown): value is Definition {
  return object(value) && Object.keys(value).sort().join(',') === 'email_reply_requested,form_key,human_callback_requested,privacy_acknowledged,version'
    && typeof value.form_key === 'string' && label.test(value.form_key) && typeof value.version === 'string' && label.test(value.version)
    && wordingKeys.every(key => typeof value[key] === 'string' && !!value[key].trim() && value[key].length <= 4000);
}
function draft(value: unknown): value is Draft {
  return object(value) && Object.keys(value).sort().join(',') === 'definition,expected_revision,id' && typeof value.id === 'string' && uuid.test(value.id)
    && typeof value.expected_revision === 'number' && Number.isInteger(value.expected_revision) && value.expected_revision >= 0 && value.expected_revision < 1000000000 && definition(value.definition);
}
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }

export function OfferForms(props: Props) { return <FormEditor key={`${props.userId}:${props.workspace}:${props.campaign}`} {...props}/>; }
function FormEditor({ userId, workspace, campaign, onPending }: Props) {
  const path = `/api/acquisition/workspaces/${workspace}/campaigns/${campaign}/offer-forms`;
  const key = `acquisition-offer-form-request:v1:${userId}:${workspace}:${campaign}`;
  const [initial] = useState(() => {
    try { const raw = sessionStorage.getItem(key); if (!raw) return { pending: null, invalid: false };
      const value: unknown = JSON.parse(raw); if (!draft(value)) throw new Error('Invalid saved request');
      return { pending: value, invalid: false };
    } catch { return { pending: null, invalid: true }; }
  });
  const [open, setOpen] = useState(!!initial.pending || initial.invalid);
  const [pending, setPending] = useState<Draft | null>(initial.pending);
  const [base, setBase] = useState<{ key: string; revision: number } | null>(initial.pending ? { key: initial.pending.definition.form_key, revision: initial.pending.expected_revision } : null);
  const [versionLabel, setVersionLabel] = useState(initial.pending?.definition.version ?? 'v1');
  const [privacy, setPrivacy] = useState(initial.pending?.definition.privacy_acknowledged ?? '');
  const [callback, setCallback] = useState(initial.pending?.definition.human_callback_requested ?? '');
  const [email, setEmail] = useState(initial.pending?.definition.email_reply_requested ?? '');
  const [busy, setBusy] = useState(false); const lock = useRef(false);
  const [message, setMessage] = useState(''); const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const after = cursors.at(-1);
  useEffect(() => { onPending?.(`${campaign}:offer-form`, busy || !!pending || initial.invalid); }, [campaign, busy, pending, initial.invalid, onPending]);
  const access = useQuery({ queryKey: ['offer-form-access', userId, workspace], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => {
      const rows = await read(`/api/acquisition/workspaces/${workspace}/memberships`, signal);
      if (!Array.isArray(rows)) throw new Error('Access unavailable');
      return rows.some(row => row?.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin'].includes(row.role));
    } });
  const history = useQuery({ queryKey: ['offer-forms', userId, workspace, campaign, after], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }): Promise<{ items: Version[]; next_after: string | null }> => {
      const page = await read(`${path}?limit=20${after ? `&after=${after}` : ''}`, signal);
      let previous = after;
      if (!Array.isArray(page?.items) || page.items.length > 20 || !page.items.every((row: Version) => {
        const valid = row && typeof row.id === 'string' && uuid.test(row.id) && (!previous || row.id > previous) && row.workspace_id === workspace && row.campaign_id === campaign
          && typeof row.acquisition_form_revision === 'number' && Number.isInteger(row.acquisition_form_revision) && row.acquisition_form_revision > 0 && row.acquisition_form_revision <= 1000000000
          && definition(row.acquisition_form_definition) && row.acquisition_form_key === row.acquisition_form_definition.form_key && row.acquisition_form_version === row.acquisition_form_definition.version
          && typeof row.acquisition_definition_hash === 'string' && hash.test(row.acquisition_definition_hash) && typeof row.created_at === 'string' && Number.isFinite(Date.parse(row.created_at))
          && row.active === false && row.send_confirmation_sms === false && row.send_confirmation_email === false;
        previous = row?.id; return valid;
      }) || !(page.next_after === null || (typeof page.next_after === 'string' && uuid.test(page.next_after) && page.items.length === 20 && page.next_after === page.items.at(-1)?.id))) throw new Error('History unavailable');
      return page;
    } });
  const canEdit = access.data === true && !access.isFetching && !access.isError && !!history.data && !history.isFetching && !history.isError && !pending && !busy && !initial.invalid;
  const current = { form_key: base?.key ?? campaign, version: versionLabel, privacy_acknowledged: privacy, human_callback_requested: callback, email_reply_requested: email };
  const valid = definition(current) && (base?.revision ?? 0) < 1000000000;
  function select(row: Version) {
    setBase({ key: row.acquisition_form_key, revision: row.acquisition_form_revision }); setVersionLabel(`v${row.acquisition_form_revision + 1}`);
    setPrivacy(row.acquisition_form_definition.privacy_acknowledged); setCallback(row.acquisition_form_definition.human_callback_requested); setEmail(row.acquisition_form_definition.email_reply_requested); setMessage('');
  }
  async function save() {
    if (lock.current || initial.invalid || (!pending && (!canEdit || !valid))) return;
    lock.current = true; setBusy(true); setMessage(''); const retrying = !!pending; let sent = false;
    const request: Draft = pending ?? { id: crypto.randomUUID(), expected_revision: base?.revision ?? 0, definition: { ...current, form_key: base?.key ?? crypto.randomUUID() } };
    try {
      sessionStorage.setItem(key, JSON.stringify(request)); setPending(request); sent = true;
      const receipt = await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
      if (receipt?.id !== request.id || receipt.workspace_id !== workspace || receipt.campaign_id !== campaign || receipt.form_key !== request.definition.form_key
        || receipt.revision !== request.expected_revision + 1 || receipt.version !== request.definition.version || receipt.status !== 'draft'
        || typeof receipt.definition_hash !== 'string' || !hash.test(receipt.definition_hash) || typeof receipt.duplicate !== 'boolean'
        || receipt.public_enabled !== false || receipt.execution_authorized !== false) throw new Error('Save unconfirmed');
      sessionStorage.removeItem(key); setPending(null); setBase({ key: request.definition.form_key, revision: receipt.revision }); setVersionLabel(`v${receipt.revision + 1}`);
      setMessage(`Form version ${receipt.revision} saved for review. Seller access remains off.`); void history.refetch();
    } catch (error) {
      if (!retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        try { sessionStorage.removeItem(key); setPending(null); } catch { /* Preserve exact recovery if storage is unavailable. */ }
        setMessage('Save rejected. Refresh access and history, then choose the latest saved version.'); void access.refetch(); void history.refetch();
      } else setMessage(sent || retrying ? 'Save is unconfirmed. Retry the same saved request in this tab.' : 'Browser storage is unavailable. No save was sent.');
    } finally { lock.current = false; setBusy(false); }
  }
  return <section aria-label="Offer form setup" className="mt-4 rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-4 text-[#1B3A5C]">
    <div><h3 className="font-semibold">Prepare the seller request form</h3><p className="text-sm text-gray-600 mt-1">Property → Condition and timing → Contact details → Review</p></div>
    <p className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm">Preparation only. Save the wording for review; seller access and follow-up remain off.</p>
    <button className={button} aria-expanded={open} disabled={busy || !!pending || initial.invalid} onClick={() => setOpen(value => !value)}>{open ? 'Hide form setup' : 'Set up request form'}</button>
    {open && <>
      <button className={button} disabled={busy} onClick={() => { void access.refetch(); void history.refetch(); }}>Refresh form setup</button>
      {initial.invalid && <p role="alert">Saved form request cannot be read. Resolve browser storage or reconcile the prior request before starting another save.</p>}
      {access.isError && <p role="alert">Form editing access could not be verified. Refresh to try again.</p>}
      {access.data === false && <p className="text-sm">Saving form versions requires current owner or administrator access with MFA.</p>}
      <fieldset disabled={!canEdit} className="space-y-4">
        <legend className="font-semibold mb-3">{pending ? 'Reconcile the saved form request' : base ? `Prepare the next version after ${base.revision}` : 'New request form'}</legend>
        <div><h4 className="font-semibold text-sm">1. Explain how the inquiry will be used</h4><label className="block text-sm mt-2">Privacy acknowledgement wording<textarea className={input} rows={3} maxLength={4000} value={privacy} onChange={e => setPrivacy(e.target.value)}/></label><p className="text-xs text-gray-600 mt-1">Enter wording for review. Saving a draft does not certify legal approval.</p></div>
        <div className="border-t pt-4"><h4 className="font-semibold text-sm">2. Keep reply choices separate</h4><label className="block text-sm mt-2">Optional human callback wording<textarea className={input} rows={2} maxLength={4000} value={callback} onChange={e => setCallback(e.target.value)}/></label><label className="block text-sm mt-2">Optional email reply wording<textarea className={input} rows={2} maxLength={4000} value={email} onChange={e => setEmail(e.target.value)}/></label><p className="text-xs text-gray-600 mt-1">Seller selections will be stored separately. A callback request does not authorize AI calls or SMS.</p></div>
        <div className="border-t pt-4"><h4 className="font-semibold text-sm">3. Review this version</h4><label className="block text-sm mt-2">Version label<input className={input} value={versionLabel} maxLength={64} onChange={e => setVersionLabel(e.target.value)}/></label><p className="text-xs text-gray-600 mt-1">Use a unique label such as v2. Letters, numbers, periods, underscores and hyphens are supported.</p></div>
        {base && <button className={button} onClick={() => { setBase(null); setVersionLabel('v1'); setPrivacy(''); setCallback(''); setEmail(''); setMessage(''); }}>Start a separate form</button>}
      </fieldset>
      <button className="rounded-lg bg-[#1B3A5C] text-white px-4 py-2 text-sm disabled:opacity-40" disabled={busy || initial.invalid || (!pending && (!canEdit || !valid))} onClick={() => { void save(); }}>{busy ? 'Saving form version…' : pending ? 'Retry exact form save' : 'Save form for review'}</button>
      {message && <p role="status" className="rounded-lg border bg-white p-3 text-sm">{message}</p>}
      {pending && <div className="text-sm"><p>A previous save is unresolved. Keep its wording unchanged and retry the same request.</p><details className="text-xs mt-2"><summary>Saved request reference</summary><p className="break-all">{pending.id}</p></details></div>}
      <div className="border-t pt-4"><h4 className="font-semibold">Saved form versions</h4>
        {history.isFetching ? <p role="status">Loading saved forms…</p> : history.isError ? <p role="alert">Saved form history could not be verified.</p> : history.data?.items.length === 0 ? <p className="text-sm mt-2">No saved form versions on this page. Complete the wording above to prepare the first draft.</p> : <ul className="space-y-3 mt-2">{history.data?.items.map(row => <li className="rounded-lg border bg-white p-3" key={row.id}><strong>Version {row.acquisition_form_revision} · {row.acquisition_form_version}</strong><p className="text-sm">Draft · Seller access off</p><details className="text-sm mt-2"><summary>View saved wording</summary><dl className="space-y-2 mt-2">{wordingKeys.map((key, index) => <div key={key}><dt className="font-medium">{['Privacy acknowledgement', 'Optional human callback', 'Optional email reply'][index]}</dt><dd className="whitespace-pre-wrap break-words">{row.acquisition_form_definition[key]}</dd></div>)}</dl></details><button className={`${button} mt-3`} disabled={!canEdit} onClick={() => select(row)}>Prepare next version from {row.acquisition_form_version}</button></li>)}</ul>}
        <p className="text-xs text-gray-600 my-3">History pages are not ordered by recency. The server prevents saving over a newer version.</p>
        <nav aria-label="Form history pages" className="flex gap-2"><button className={button} disabled={busy || !!pending || history.isFetching || cursors.length === 1} onClick={() => setCursors(value => value.slice(0, -1))}>Previous form versions</button><button className={button} disabled={busy || !!pending || history.isFetching || history.isError || !history.data?.next_after} onClick={() => { if (history.data?.next_after) setCursors(value => [...value, history.data!.next_after]); }}>Next form versions</button></nav>
      </div>
    </>}
  </section>;
}
