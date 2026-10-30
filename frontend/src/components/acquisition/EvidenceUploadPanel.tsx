import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { ApiError, apiFetch } from '@/lib/api';
import { id } from '@/lib/acquisition/mail-content';
import { checkRegistration, checkUpload, chooseFile, matchesFile, parseCandidates, parseScanState, scanGuidance, pendingSchema, retentionLabel, type FileChoice, type PendingEvidence } from '@/lib/acquisition/evidence';

type Props = { userId: string; workspace: string; campaign: string; disabled?: boolean; onPending: (key: string, pending: boolean) => void };
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded-lg border bg-white p-2';
const statuses = { pending_verification: 'Registered — upload or verification pending', revoked: 'Withdrawn', expired: 'Retention expired', policy_review_required: 'Policy review required' };
export function EvidenceUploadPanel(props: Props) { return <EvidenceEditor key={`${props.userId}:${props.workspace}:${props.campaign}`} {...props}/>; }
function EvidenceEditor({ userId, workspace, campaign, disabled = false, onPending }: Props) {
  const path = `/api/acquisition/workspaces/${workspace}/campaigns/${campaign}/evidence`;
  const storageKey = `acquisition-evidence-request:v1:${userId}:${workspace}:${campaign}`;
  const [initial] = useState(() => {
    try { const raw = sessionStorage.getItem(storageKey); if (!raw) return { pending: null, invalid: false };
      const value = pendingSchema.parse(JSON.parse(raw));
      if (value.user_id !== userId || value.workspace_id !== workspace || value.campaign_id !== campaign) throw new Error('Recovery scope mismatch');
      return { pending: value, invalid: false };
    } catch { return { pending: null, invalid: true }; }
  });
  const [pending, setPending] = useState<PendingEvidence | null>(initial.pending);
  const [blocked, setBlocked] = useState(initial.invalid), [open, setOpen] = useState(!!initial.pending || initial.invalid);
  const [choice, setChoice] = useState<FileChoice | null>(null), [note, setNote] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now());
  const [retryAt, setRetryAt] = useState(0), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const after = cursors.at(-1)!; const inFlight = useRef(false), mounted = useRef(true), fileInput = useRef<HTMLInputElement>(null);
  const held = busy || !!pending || blocked;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(`${campaign}:evidence`, held); }, [campaign, held, onPending]);
  useEffect(() => { if (!open) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [open]);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: open, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const access = useQuery({ ...options, queryKey: ['evidence-access', userId, workspace], queryFn: async ({ signal }) => {
    const rows = z.array(z.object({ workspace_id: id, user_id: id, status: z.string(), role: z.string() })).parse(await (await apiFetch(`/api/acquisition/workspaces/${workspace}/memberships`, { signal })).json());
    return rows.some(r => r.workspace_id === workspace && r.user_id === userId && r.status === 'active' && ['owner', 'admin', 'operator'].includes(r.role));
  } });
  const records = useQuery({ ...options, queryKey: ['evidence-candidates', userId, workspace, campaign, after], queryFn: async ({ signal }) =>
    parseCandidates(await (await apiFetch(`${path}?purpose=mail_content&limit=20${after ? `&after=${after}` : ''}`, { signal })).json(), workspace, campaign, after) });
  const ready = access.data === true && !access.isFetching && !access.isError && !!records.data && !records.isFetching && !records.isError;
  const current = ready && now - Date.parse(records.data!.checked_at) <= 30000;
  const policy = records.data?.current_policy;
  const canPrepare = ready && records.data!.upload_enabled && !!policy && Date.parse(policy.valid_until) > now;
  const canStart = current && canPrepare;
  const canRecover = current && !!pending && (pending.stage === 'register' || records.data!.upload_enabled);
  function refresh() { void access.refetch(); void records.refetch(); }
  function persist(value: PendingEvidence) {
    try { const raw = JSON.stringify(value); sessionStorage.setItem(storageKey, raw); if (sessionStorage.getItem(storageKey) !== raw) throw new Error('Recovery unavailable'); }
    catch (error) { setBlocked(true); throw error; }
    setPending(value);
  }
  function clear() {
    try { sessionStorage.removeItem(storageKey); if (sessionStorage.getItem(storageKey) !== null) throw new Error('Recovery unavailable'); }
    catch (error) { setBlocked(true); throw error; }
    setPending(null);
  }
  async function select(file: File | undefined) {
    if (inFlight.current || disabled || blocked) return;
    setChoice(null); if (!file) return;
    inFlight.current = true; setBusy(true); setMessage('Checking the selected file…');
    try { const selected = await chooseFile(file); if (!mounted.current) return;
      if (pending && !matchesFile(selected, pending)) throw new Error('Different original file');
      setChoice(selected); setMessage('File checked locally. It has not been uploaded or approved.');
    } catch { if (mounted.current) setMessage(pending ? 'Choose the exact original file, with the same type and contents, to recover this request.' : 'File could not be checked. Choose a PDF, PNG, JPEG or text file between 1 byte and 10 MiB.'); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  const validNote = note.trim().length >= 20 && note.length <= 2000 && !note.includes('\0');
  async function save() {
    if (inFlight.current || disabled || blocked || now < retryAt || (!pending && (!canStart || !choice || !validNote))
      || (pending && (!canRecover || pending.stage === 'upload' && (!choice || !matchesFile(choice, pending))))) return;
    const retrying = !!pending; let sent = false;
    let saved = pending ?? pendingSchema.parse({ user_id: userId, workspace_id: workspace, campaign_id: campaign, stage: 'register', registration: {
      id: crypto.randomUUID(), purpose: 'mail_content', expected_sha256: choice!.hash, expected_byte_size: choice!.file.size,
      media_type: choice!.media, retention_policy_id: policy!.id, provenance_note: note } });
    inFlight.current = true; setBusy(true); setMessage('Saving evidence…');
    try {
      if (!pending) persist(saved);
      if (saved.stage === 'register') {
        sent = true;
        checkRegistration(await (await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.registration) })).json(), saved);
        if (!mounted.current) return;
        saved = { ...saved, stage: 'upload' }; persist(saved);
      }
      if (!choice || !matchesFile(choice, saved) || !records.data?.upload_enabled) { setMessage('Registration confirmed. Reselect the original file when uploads are available to finish.'); return; }
      if (!mounted.current) return;
      sent = true;
      checkUpload(await (await apiFetch(`${path}/${saved.registration.id}/bytes?purpose=mail_content`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: choice.file })).json(), saved);
      if (!mounted.current) return;
      clear(); setChoice(null); setNote(''); if (fileInput.current) fileInput.current.value = '';
      setMessage('Uploaded — verification pending. The file is not scanned or approved for use.'); void records.refetch();
    } catch (error) {
      if (!mounted.current) return;
      if (!retrying && saved.stage === 'register' && error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        try { clear(); } catch { /* Keep the exact request held if recovery storage cannot be reconciled. */ }
        setMessage('Registration was rejected. Refresh current access and policy before trying again.');
      } else if (error instanceof ApiError && error.status === 429) {
        setRetryAt(Date.now() + (error.retryAfterSeconds ?? 120) * 1000); setMessage('Upload capacity is occupied. Your original request is saved; wait, then retry the same file.');
      } else setMessage(sent || retrying ? 'The result is unconfirmed. Keep the original file and retry this saved request; do not create another evidence record.' : 'Browser recovery storage is unavailable. No request was sent.');
    } finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  const retrySeconds = Math.max(0, Math.ceil((retryAt - now) / 1000));
  return <section aria-label="Mail evidence files" className="mt-3 rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3">
    <button className={`${button} border-[#E8720C] text-[#1B3A5C]`} aria-expanded={open} disabled={held || disabled} onClick={() => setOpen(v => !v)}>{open ? 'Hide evidence files' : 'Add or review evidence files'}</button>
    {open && <>
      <h4 className="font-semibold text-[#1B3A5C]">Supporting files for your mail review</h4>
      <p className="text-sm text-gray-600">Choose the original file and describe its source. Uploading does not approve the wording, verify the file or authorize mailing.</p>
      {blocked && <p role="alert">Saved evidence recovery is unavailable or unreadable. Keep the original file and reconcile this browser tab before creating another record.</p>}
      <button className={button} disabled={busy || disabled} onClick={refresh}>Refresh evidence status</button>
      {(access.isError || records.isError) && <p role="alert">Evidence status could not be verified. Refresh and check your access.</p>}
      {(access.isFetching || records.isFetching) && <p role="status">Checking evidence and access…</p>}
      {ready && !records.data!.upload_enabled && <p>File uploads are currently paused. Existing evidence history remains available.</p>}
      {ready && !policy && <p>A reviewed retention policy is needed before registering a new file.</p>}
      {ready && policy && <p className="text-sm">Approved retention: {retentionLabel(policy.retention_seconds)} from registration. Policy available until {new Date(policy.valid_until).toLocaleString()}.</p>}
      {ready && !current && <p>Refresh evidence status before continuing.</p>}
      {pending && <p className="rounded-lg border border-orange-200 bg-white p-3 text-sm">Saved request awaiting confirmation. {pending.stage === 'register' ? 'Check the saved registration before changing any details.' : 'Reselect the exact original file to finish or reconcile the upload.'} This tab retains the request details, not the file itself.</p>}
      <label className="block text-sm font-medium text-[#1B3A5C]">Evidence file<input ref={fileInput} className={input} type="file" accept="application/pdf,image/png,image/jpeg,text/plain" disabled={busy || disabled || blocked || (!pending && !canPrepare)} onChange={e => { void select(e.target.files?.[0]); }}/></label>
      <p className="text-xs text-gray-600">PDF, PNG, JPEG or plain text · Maximum 10 MiB · No file preview until verification is complete.</p>
      {choice && <p className="break-words text-sm">Selected: {choice.file.name} · {choice.file.size.toLocaleString()} bytes</p>}
      <label className="block text-sm font-medium text-[#1B3A5C]">File source and purpose<textarea className={input} maxLength={2000} value={pending?.registration.provenance_note ?? note} disabled={busy || disabled || blocked || !!pending || !canPrepare} onChange={e => setNote(e.target.value)}/></label>
      <p className="text-xs text-gray-600">Describe where the file came from and why it supports this review, using at least 20 characters.</p>
      <button className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || disabled || blocked || retrySeconds > 0 || (pending ? !canRecover || pending.stage === 'upload' && !choice : !canStart || !choice || !validNote)} onClick={() => { void save(); }}>{pending ? pending.stage === 'register' ? 'Check saved registration' : 'Retry saved file upload' : 'Register and upload file'}</button>
      {retrySeconds > 0 && <p role="status">Retry available in {retrySeconds} seconds.</p>}
      {message && <p role="status" className="text-sm">{message}</p>}
      <div className="border-t border-orange-200 pt-3"><h5 className="font-semibold text-[#1B3A5C]">Registered evidence</h5><p className="text-xs text-gray-600">These records do not establish that a file has been uploaded, scanned or approved.</p>
        {!records.isFetching && !records.isError && records.data?.items.length === 0 && <p className="text-sm">No evidence registered for this campaign.</p>}
        <ul>{!records.isError && records.data?.items.map(row => <li key={row.artifact_id} className="border-t py-2 text-sm"><span>{row.media_type === 'application/pdf' ? 'PDF' : row.media_type.startsWith('image/') ? 'Image' : 'Text'} · {new Date(row.created_at).toLocaleString()} · {row.expected_byte_size.toLocaleString()} bytes</span><p>{statuses[row.status]}</p>{current && !disabled && !held && <FileScanStatus key={`${row.artifact_id}:${records.data!.checked_at}`} userId={userId} workspace={workspace} campaign={campaign} artifact={row.artifact_id} now={now}/>}</li>)}</ul>
        <nav aria-label="Evidence history pages" className="flex gap-2"><button className={button} disabled={held || disabled || records.isFetching || cursors.length === 1} onClick={() => setCursors(v => v.slice(0, -1))}>Previous evidence</button><button className={button} disabled={held || disabled || records.isFetching || records.isError || !records.data?.next_after} onClick={() => setCursors(v => [...v, records.data!.next_after])}>Next evidence</button></nav>
      </div>
    </>}
  </section>;
}

function FileScanStatus({ userId, workspace, campaign, artifact, now }: { userId: string; workspace: string; campaign: string; artifact: string; now: number }) {
  const scan = useQuery({ queryKey: ['evidence-scan', userId, workspace, campaign, artifact], enabled: false,
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
    queryFn: async ({ signal }) => parseScanState(await (await apiFetch(
      `/api/acquisition/workspaces/${workspace}/campaigns/${campaign}/evidence/${artifact}/scan-state`, { signal })).json(), workspace, campaign, artifact),
  });
  const visible = scan.data && !scan.isFetching && !scan.isError && now - Date.parse(scan.data.checked_at) <= 30000;
  const guidance = visible ? scanGuidance[scan.data!.status] : null;
  return <div className="mt-2 rounded-lg border-l-4 border-[#E8720C] bg-white p-3 text-[#1B3A5C]">
    <button className={button} disabled={scan.isFetching} onClick={() => { void scan.refetch(); }}>Check file status</button>
    {scan.isFetching && <p role="status">Checking current file status…</p>}
    {scan.isError && <p role="alert">File status could not be verified. Check your access and try again.</p>}
    {guidance && <div role="status"><p className="font-medium">{guidance[0]}</p><p>Next: {guidance[1]}</p>
      {scan.data!.quarantined && scan.data!.status !== 'quarantined' && <p>A recorded detection also keeps this file on hold.</p>}
      <p className="text-xs text-gray-600">Checked {new Date(scan.data!.checked_at).toLocaleTimeString()}. This is a status snapshot, not approval to use the file.</p></div>}
    {!scan.isFetching && !scan.isError && scan.data && !visible && <p>Check file status again to refresh this result.</p>}
  </div>;
}
