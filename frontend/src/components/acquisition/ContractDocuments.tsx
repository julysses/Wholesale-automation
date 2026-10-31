import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { apiFetch, ApiError } from '@/lib/api';
import { id } from '@/lib/acquisition/mail-content';
import { chooseFile, matchesFile, retentionLabel, type FileChoice } from '@/lib/acquisition/evidence';
import { checkDocumentRegistration, checkDocumentUpload, clearPendingDocument, parseDocuments, pendingSchema, purposes,
  readPendingDocument, savePendingDocument, type DocumentContext, type PendingDocument } from '@/lib/acquisition/contract-documents';

const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full rounded-lg border border-gray-300 bg-white p-2';
const statuses = { pending_verification: 'Verification and review pending', revoked: 'Withdrawn', expired: 'Retention expired', policy_review_required: 'Retention review needed' };
type Props = { context: DocumentContext; disabled?: boolean; onPending: (pending: boolean) => void };
export function ContractDocuments(props: Props) {
  return <DocumentEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props}/>;
}
function DocumentEditor({ context, disabled = false, onPending }: Props) {
  const { userId, workspaceId: workspace, contractId: contract, contractVersion: version } = context;
  const path = `/api/acquisition/workspaces/${workspace}/contracts/${contract}/versions/${version}/documents`;
  const [initial] = useState(() => {
    try { const saved = readPendingDocument(sessionStorage, userId, workspace);
      if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Recovery context changed');
      return { saved, invalid: false };
    } catch { return { saved: null, invalid: true }; }
  });
  const [pending, setPending] = useState<PendingDocument | null>(initial.saved), [blocked, setBlocked] = useState(initial.invalid);
  const [kind, setKind] = useState<keyof typeof purposes>(initial.saved?.registration.purpose ?? 'purchase_contract');
  const [choice, setChoice] = useState<FileChoice | null>(null), [note, setNote] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now());
  const [retryAt, setRetryAt] = useState(0), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const inFlight = useRef(false), mounted = useRef(true), fileInput = useRef<HTMLInputElement>(null);
  const held = busy || !!pending || blocked, after = cursors.at(-1)!;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, onPending]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: !blocked && !disabled, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const access = useQuery({ ...options, queryKey: ['contract-document-access', userId, workspace], queryFn: async ({ signal }) => {
    const rows = z.array(z.object({ workspace_id: id, user_id: id, status: z.string(), role: z.string() })).parse(await (await apiFetch(`/api/acquisition/workspaces/${workspace}/memberships`, { signal, cache: 'no-store' })).json());
    return rows.some(row => row.workspace_id === workspace && row.user_id === userId && row.status === 'active' && ['owner', 'admin', 'operator'].includes(row.role));
  } });
  const records = useQuery({ ...options, queryKey: ['contract-documents', userId, workspace, contract, version, kind, after], queryFn: async ({ signal }) =>
    parseDocuments(await (await apiFetch(`${path}?purpose=${kind}&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), context, kind, after) });
  const ready = !disabled && access.data === true && !access.isFetching && !access.isError && !!records.data && !records.isFetching && !records.isError;
  const current = ready && now - Date.parse(records.data!.checked_at) <= 30000;
  const policy = records.data?.current_policy;
  const canPrepare = ready && records.data!.upload_enabled && !!policy && Date.parse(policy.valid_until) > now;
  const canStart = current && canPrepare;
  const canRecover = current && !!pending && (pending.stage === 'register' || records.data!.upload_enabled);
  function refresh() { void access.refetch(); void records.refetch(); }
  function persist(value: PendingDocument, previous: PendingDocument | null) {
    try { const next = savePendingDocument(sessionStorage, value, previous); setPending(next); return next; }
    catch (error) { setBlocked(true); throw error; }
  }
  async function select(file: File | undefined) {
    if (inFlight.current || disabled || blocked) return;
    setChoice(null); if (!file) return;
    inFlight.current = true; setBusy(true); setMessage('Checking the selected file…');
    try { const selected = await chooseFile(file); if (!mounted.current) return;
      if (pending && !matchesFile(selected, pending)) throw new Error('Different original file');
      setChoice(selected); setMessage('File checked locally. Nothing has been uploaded yet.');
    } catch { if (mounted.current) setMessage(pending ? 'Choose the exact original file, with the same type and contents, to recover this request.' : 'Choose a PDF, PNG, JPEG or text file between 1 byte and 10 MiB.'); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  const validNote = note.trim().length >= 20 && note.length <= 2000 && !note.includes('\0');
  async function save() {
    if (inFlight.current || disabled || blocked || Date.now() < retryAt || (!pending && (!canStart || !choice || !validNote))
      || (pending && (!canRecover || pending.stage === 'upload' && (!choice || !matchesFile(choice, pending))))) return;
    let saved = pending ?? pendingSchema.parse({ version: 1, context, stage: 'register', registration: {
      id: crypto.randomUUID(), purpose: kind, expected_sha256: choice!.hash, expected_byte_size: choice!.file.size,
      media_type: choice!.media, retention_policy_id: policy!.id, provenance_note: note } });
    let sent = false;
    inFlight.current = true; setBusy(true); setMessage('Saving this document…');
    try {
      if (!pending) saved = persist(saved, null);
      if (saved.stage === 'register') {
        sent = true;
        checkDocumentRegistration(await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(saved.registration), signal: AbortSignal.timeout(30000) })).json(), saved);
        if (!mounted.current) return;
        saved = persist({ ...saved, stage: 'upload' }, saved);
      }
      if (!choice || !matchesFile(choice, saved) || !records.data?.upload_enabled) { setMessage('Document registration confirmed. Reselect the original file when uploads are available to finish.'); return; }
      if (!mounted.current) return;
      sent = true;
      checkDocumentUpload(await (await apiFetch(`${path}/${saved.registration.id}/bytes?purpose=${saved.registration.purpose}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: choice.file, signal: AbortSignal.timeout(95000) })).json(), saved);
      if (!mounted.current) return;
      try { clearPendingDocument(sessionStorage, saved); } catch (error) { setBlocked(true); throw error; }
      setPending(null); setChoice(null); setNote(''); if (fileInput.current) fileInput.current.value = '';
      setMessage('Upload confirmed. Next: file verification and document review. This does not sign or approve the contract.'); void records.refetch();
    } catch (error) {
      if (!mounted.current) return;
      if (!pending && saved.stage === 'register' && error instanceof ApiError && error.rejectedDocument) {
        try {
          clearPendingDocument(sessionStorage, saved); setPending(null);
          setMessage('The document was not registered. Refresh document status and resolve the restriction before trying again.');
          refresh(); return;
        } catch { setBlocked(true); }
      }
      if (error instanceof ApiError && error.status === 429) {
        setRetryAt(Date.now() + (error.retryAfterSeconds ?? 120) * 1000); setMessage('Upload capacity is occupied. Your original request is saved; wait, then retry the same file.');
      } else setMessage(sent || pending ? 'The result is unconfirmed. Keep the original file and retry this saved request. If access or policy changed, restore access or ask an administrator to reconcile it.' : 'Browser recovery storage is unavailable. No request was sent.');
    } finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  const retrySeconds = Math.max(0, Math.ceil((retryAt - now) / 1000));
  return <section aria-label="Contract documents" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <div><h3 className="font-semibold">Add documents for review</h3><p className="text-sm text-gray-600">Choose the document type, attach the original file, then complete verification and review. Uploading does not change the draft’s status or sign an agreement.</p></div>
    {blocked && <p role="alert">Saved document recovery is unavailable or unreadable. Keep the original file and reconcile this browser tab before creating another record.</p>}
    {disabled && <p role="alert">The saved contract context could not be confirmed. Refresh draft information before continuing.</p>}
    <label className="block text-sm font-medium">Document type<select className={input} value={kind} disabled={held || disabled} onChange={event => {
      setKind(event.target.value as keyof typeof purposes); setCursors([null]); setChoice(null); setNote(''); setMessage(''); if (fileInput.current) fileInput.current.value = '';
    }}>{Object.entries(purposes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <button className={button} disabled={busy || disabled || blocked} onClick={refresh}>Refresh document status</button>
    {(access.isFetching || records.isFetching) && <p role="status">Checking documents and access…</p>}
    {(access.isError || records.isError || access.data === false) && <p role="alert">Current document access could not be confirmed. Refresh and check your workspace access.</p>}
    {ready && !records.data!.upload_enabled && <p>Uploads are currently paused. Existing document history remains available.</p>}
    {ready && !policy && <p>A reviewed retention policy is needed before adding this document type.</p>}
    {ready && policy && <p className="text-sm">Approved retention: {retentionLabel(policy.retention_seconds)} from registration.</p>}
    {ready && !current && <p>Refresh document status before continuing.</p>}
    {pending && <div className="rounded-lg border border-orange-200 bg-white p-3 text-sm"><h4 className="font-semibold">Recover the saved document</h4><p>{pending.stage === 'register' ? 'Confirm the original registration before changing any details.' : 'Reselect the exact original file to finish or reconcile the upload.'} This tab retains request details, not the file itself. Property and contract selection remain fixed until the result is confirmed.</p></div>}
    <label className="block text-sm font-medium">Original document<input ref={fileInput} type="file" accept="application/pdf,image/png,image/jpeg,text/plain" className={input}
      disabled={busy || disabled || blocked || (!pending && !canPrepare)} onChange={event => { void select(event.target.files?.[0]); }}/></label>
    <p className="text-xs text-gray-600">PDF, PNG, JPEG or text · Maximum 10 MiB · No file preview before verification and review.</p>
    {choice && <p className="break-words text-sm">Selected: {choice.file.name} · {choice.file.size.toLocaleString()} bytes</p>}
    <label className="block text-sm font-medium">Where did this document come from?<textarea className={input} maxLength={2000} value={pending?.registration.provenance_note ?? note}
      disabled={busy || disabled || blocked || !!pending || !canPrepare} onChange={event => setNote(event.target.value)}/></label>
    <p className="text-xs text-gray-600">Describe its source and purpose in at least 20 characters.</p>
    <button className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || disabled || blocked || retrySeconds > 0 || (pending ? !canRecover || pending.stage === 'upload' && !choice : !canStart || !choice || !validNote)}
      onClick={() => { void save(); }}>{busy ? 'Working…' : pending ? pending.stage === 'register' ? 'Check saved registration' : 'Retry saved document upload' : 'Save and upload document'}</button>
    {retrySeconds > 0 && <p role="status">Retry available in {retrySeconds} seconds.</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
    <div className="border-t border-orange-200 pt-3 space-y-2"><h4 className="font-semibold">Document history</h4><p className="text-xs text-gray-600">Registration alone does not confirm upload, verification or legal review.</p>
      {!records.isFetching && !records.isError && records.data?.items.length === 0 && <p className="text-sm">No {purposes[kind].toLowerCase()} registered yet.</p>}
      <ul>{!records.isError && records.data?.items.map(row => <li key={row.artifact_id} className="border-t py-2 text-sm"><p>{purposes[row.purpose]} · {new Date(row.created_at).toLocaleString()}</p><p>{row.expected_byte_size.toLocaleString()} bytes · {statuses[row.status]}</p></li>)}</ul>
      <nav aria-label="Document history pages" className="flex flex-wrap gap-2"><button className={button} disabled={held || disabled || records.isFetching || cursors.length === 1} onClick={() => setCursors(values => values.slice(0, -1))}>Previous documents</button>
        <button className={button} disabled={held || disabled || records.isFetching || records.isError || !records.data?.next_after} onClick={() => setCursors(values => [...values, records.data!.next_after])}>Next documents</button></nav>
    </div>
  </section>;
}
