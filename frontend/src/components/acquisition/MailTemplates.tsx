import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type PendingReporter = (key: string, pending: boolean) => void;

type Draft = { id: string; template_id: string; expected_version: number; name: string; format: 'letter' | 'postcard'; tracking_mode: 'phone' | 'landing_page'; body: string };
type Version = { id: string; workspace_id: string; campaign_id: string; acquisition_template_id: string; acquisition_template_version: number; name: string; primary_text: string; acquisition_mail_format: Draft['format']; acquisition_tracking_mode: Draft['tracking_mode']; status: string };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded border p-2';
function valid(value: unknown): value is Draft {
  if (!value || typeof value !== 'object') return false;
  const d = value as Draft;
  return Object.keys(d).sort().join(',') === 'body,expected_version,format,id,name,template_id,tracking_mode'
    && uuid.test(d.id) && uuid.test(d.template_id) && Number.isInteger(d.expected_version) && d.expected_version >= 0 && d.expected_version < 1000000000
    && typeof d.name === 'string' && !!d.name.trim() && d.name.length <= 200 && ['letter', 'postcard'].includes(d.format)
    && ['phone', 'landing_page'].includes(d.tracking_mode) && typeof d.body === 'string' && !!d.body.trim() && d.body.length <= 20000
    && d.body.includes(d.tracking_mode === 'phone' ? '{{tracking_phone}}' : '{{tracking_url}}')
    && !/[{}]/.test(d.body.replace(/\{\{(tracking_phone|tracking_url|property_address|company_name)\}\}/g, ''));
}
async function read(path: string, signal?: AbortSignal) { return (await apiFetch(path, { signal })).json(); }

export function MailTemplates(props: { userId: string; workspace: string; campaign: string; onPending?: PendingReporter }) {
  return <MailEditor key={`${props.userId}:${props.workspace}:${props.campaign}`} {...props} />;
}
function MailEditor({ userId, workspace, campaign, onPending }: { userId: string; workspace: string; campaign: string; onPending?: PendingReporter }) {
  const path = `/api/acquisition/workspaces/${workspace}/campaigns/${campaign}/mail-templates`;
  const key = `acquisition-mail-request:v1:${userId}:${workspace}:${campaign}`;
  const [initial] = useState(() => {
    try { const raw = sessionStorage.getItem(key); if (!raw) return { pending: null, invalid: false };
      const value: unknown = JSON.parse(raw); if (!valid(value)) throw new Error('Invalid request');
      return { pending: value, invalid: false };
    } catch { return { pending: null, invalid: true }; }
  });
  const [open, setOpen] = useState(!!initial.pending || initial.invalid);
  const [pending, setPending] = useState<Draft | null>(initial.pending);
  const [base, setBase] = useState<{ template: string; version: number } | null>(initial.pending ? { template: initial.pending.template_id, version: initial.pending.expected_version } : null);
  const [name, setName] = useState(initial.pending?.name ?? '');
  const [body, setBody] = useState(initial.pending?.body ?? '');
  const [format, setFormat] = useState<Draft['format']>(initial.pending?.format ?? 'letter');
  const [mode, setMode] = useState<Draft['tracking_mode']>(initial.pending?.tracking_mode ?? 'phone');
  const [busy, setBusy] = useState(false); const inFlight = useRef(false);
  useEffect(() => { onPending?.(`${campaign}:template`, busy || !!pending || initial.invalid); }, [campaign, busy, pending, initial.invalid, onPending]);
  const [message, setMessage] = useState(''); const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const after = cursors.at(-1);
  const access = useQuery({ queryKey: ['mail-template-access', userId, workspace], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }) => {
      const rows = await read(`/api/acquisition/workspaces/${workspace}/memberships`, signal);
      if (!Array.isArray(rows)) throw new Error('Access unavailable');
      return rows.some(row => row.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin', 'operator'].includes(row.role));
    } });
  const history = useQuery({ queryKey: ['mail-templates', userId, workspace, campaign, after], enabled: open, retry: false, gcTime: 0, staleTime: 0,
    queryFn: async ({ signal }): Promise<{ items: Version[]; next_after: string | null }> => {
      const page = await read(`${path}?limit=20${after ? `&after=${after}` : ''}`, signal);
      if (!Array.isArray(page?.items) || page.items.length > 20 || !page.items.every((row: Version) => row && row.workspace_id === workspace && row.campaign_id === campaign && row.status === 'draft'
        && Number.isInteger(row.acquisition_template_version) && row.acquisition_template_version > 0
        && valid({ id: row.id, template_id: row.acquisition_template_id, expected_version: row.acquisition_template_version - 1, name: row.name, body: row.primary_text, format: row.acquisition_mail_format, tracking_mode: row.acquisition_tracking_mode }))
        || !(page.next_after === null || (typeof page.next_after === 'string' && uuid.test(page.next_after) && page.next_after === page.items.at(-1)?.id && page.next_after !== after))) throw new Error('History unavailable');
      return page;
    } });
  const canEdit = access.data === true && !access.isError && !access.isFetching && !initial.invalid && !pending && !busy;
  const contentValid = valid({ id: campaign, template_id: base?.template ?? campaign, expected_version: base?.version ?? 0, name, body, format, tracking_mode: mode });
  function selectVersion(row: Version) { setBase({ template: row.acquisition_template_id, version: row.acquisition_template_version }); setName(row.name); setBody(row.primary_text); setFormat(row.acquisition_mail_format); setMode(row.acquisition_tracking_mode); setMessage(''); }
  async function save() {
    if (inFlight.current || initial.invalid || (!pending && (!canEdit || !contentValid))) return;
    inFlight.current = true; setBusy(true); setMessage(''); const retrying = !!pending; let sent = false;
    const draft: Draft = pending ?? { id: crypto.randomUUID(), template_id: base?.template ?? crypto.randomUUID(), expected_version: base?.version ?? 0, name, body, format, tracking_mode: mode };
    try {
      sessionStorage.setItem(key, JSON.stringify(draft)); setPending(draft); sent = true;
      const receipt = await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft) })).json();
      if (receipt?.id !== draft.id || receipt.workspace_id !== workspace || receipt.template_id !== draft.template_id || receipt.version !== draft.expected_version + 1
        || receipt.status !== 'draft' || receipt.execution_authorized !== false || typeof receipt.duplicate !== 'boolean') throw new Error('Unconfirmed save');
      sessionStorage.removeItem(key); setPending(null); setBase({ template: draft.template_id, version: receipt.version });
      setMessage(`Draft version ${receipt.version} saved. Approval and mail fulfillment remain separate.`); void history.refetch();
    } catch (error) {
      if (!retrying && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        try { sessionStorage.removeItem(key); setPending(null); } catch { /* Retain exact request if removal fails. */ }
        setMessage('Save rejected. Refresh access and history, then select the latest version before editing again.'); void access.refetch(); void history.refetch();
      } else setMessage(sent || retrying ? 'Save is unconfirmed. The exact request is retained in this tab; retry it to reconcile.' : 'Browser storage is unavailable. No save was sent.');
    } finally { setBusy(false); inFlight.current = false; }
  }
  return <section aria-label="Mail template drafts" className="mt-4 space-y-3">
    <button className={button} aria-expanded={open} disabled={busy || !!pending || initial.invalid} onClick={() => setOpen(value => !value)}>{open ? 'Hide mail drafts' : 'Edit mail drafts'}</button>
    {open && <><p>Draft letters and postcards for review. Saving does not approve content, bind a phone number or website, or send mail.</p>
      <button className={button} disabled={busy} onClick={() => { void access.refetch(); void history.refetch(); }}>Refresh mail drafts</button>
      {initial.invalid && <p role="alert">Saved request cannot be read. Resolve browser storage or reconcile the prior request before creating another draft.</p>}
      {!canEdit && !pending && !busy && <p>Editing requires current owner, administrator or operator access.</p>}
      <fieldset disabled={!canEdit} className="space-y-3"><legend>{base ? `Next version after ${base.version}` : 'New mail template'}</legend>
        <label>Template name<input className={input} maxLength={200} value={name} onChange={e => setName(e.target.value)}/></label>
        <label>Mail format<select className={input} value={format} onChange={e => setFormat(e.target.value as Draft['format'])}><option value="letter">Letter</option><option value="postcard">Postcard</option></select></label>
        <label>Tracked response<select className={input} value={mode} onChange={e => setMode(e.target.value as Draft['tracking_mode'])}><option value="phone">Phone</option><option value="landing_page">Landing page</option></select></label>
        <label>Draft content<textarea className={input} rows={6} maxLength={20000} value={body} onChange={e => setBody(e.target.value)}/></label>
        <p className="text-sm">Use {'{{tracking_phone}}'} or {'{{tracking_url}}'} for the selected response method. Optional fields: {'{{company_name}}'}, {'{{property_address}}'}. Destinations require separate review.</p>
        {base && <button className={button} onClick={() => { setBase(null); setName(''); setBody(''); }}>Start a separate template</button>}
      </fieldset>
      <button className={button} disabled={busy || initial.invalid || (!pending && (!canEdit || !contentValid))} onClick={() => { void save(); }}>{busy ? 'Saving mail draft…' : pending ? 'Retry exact mail save' : 'Save mail draft'}</button>
      {message && <p role="status">{message}</p>}
      {history.isFetching ? <p role="status">Loading mail history…</p> : history.isError ? <p role="alert">Mail history could not be verified.</p> : <ul>{history.data?.items.map(row => <li className="border-t py-3" key={row.id}><strong>{row.name} · Version {row.acquisition_template_version}</strong><pre className="whitespace-pre-wrap break-words font-sans">{row.primary_text}</pre><button className={button} disabled={!canEdit} onClick={() => selectVersion(row)}>Edit from version {row.acquisition_template_version}</button></li>)}</ul>}
      <p className="text-sm">History is paginated, not sorted by recency. A newer saved version will prevent a stale edit.</p>
      <nav aria-label="Mail history pages"><button className={button} disabled={busy || !!pending || history.isFetching || cursors.length === 1} onClick={() => setCursors(value => value.slice(0, -1))}>Previous mail versions</button><button className={button} disabled={busy || !!pending || history.isFetching || history.isError || !history.data?.next_after} onClick={() => { if (history.data?.next_after) setCursors(value => [...value, history.data!.next_after]); }}>Next mail versions</button></nav>
    </>}
  </section>;
}
