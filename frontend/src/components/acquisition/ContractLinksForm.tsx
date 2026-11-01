import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { purposes, type DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseReferences } from '@/lib/acquisition/contract-references';
import { parseContractVersions } from '@/lib/acquisition/contract-terms';
import { clearConfirmedLink, clearRejectedLink, pendingLinkSchema, preserveLink, readPendingLink, type PendingLink } from '@/lib/acquisition/contract-links';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
type Props = { context: DocumentContext; disabled: boolean; onPending: (held: boolean) => void; onSaved: () => void };
export function ContractLinksForm(props: Props) {
  return <LinksEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function LinksEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingLink(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Reference context changed.');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingLink | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [mode, setMode] = useState<'link' | 'withdraw' | null>(initial.saved?.kind ?? null);
  const [kind, setKind] = useState<keyof typeof purposes>('purchase_contract');
  const [sourceVersion, setSourceVersion] = useState<number | null>(null), [artifact, setArtifact] = useState(''), [note, setNote] = useState('');
  const [versionCursors, setVersionCursors] = useState<(number | null)[]>([null]), [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now());
  const lock = useRef(false), mounted = useRef(true), client = useQueryClient();
  const locked = busy || !!pending || blocked, held = locked || mode !== null;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}`;
  const versionAfter = versionCursors.at(-1)!, after = cursors.at(-1)!;
  const viewedVersion = mode === 'withdraw' ? context.contractVersion : sourceVersion;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const options = { enabled: !disabled && !locked && mode !== null, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false } as const;
  const versions = useQuery({ ...options, enabled: options.enabled && mode === 'link', queryKey: ['link-versions', context.userId, context.workspaceId, context.contractId, context.contractVersion, versionAfter],
    queryFn: async ({ signal }) => parseContractVersions(await (await apiFetch(`${base}/versions?limit=20${versionAfter ? `&after=${versionAfter}` : ''}`, { signal, cache: 'no-store' })).json(), context, versionAfter) });
  const references = useQuery({ ...options, enabled: options.enabled && viewedVersion !== null,
    queryKey: ['link-references', context.userId, context.workspaceId, context.contractId, context.contractVersion, viewedVersion, kind, after],
    queryFn: async ({ signal }) => parseReferences(await (await apiFetch(`${base}/versions/${viewedVersion}/references?purpose=${kind}&limit=20${after ? `&after=${after}` : ''}`, { signal, cache: 'no-store' })).json(), { ...context, contractVersion: viewedVersion! }, kind, after) });
  const selected = references.data?.items.find(row => row.artifact_id === artifact);
  const fresh = !!selected && !disabled && !references.isFetching && !references.isError && now - Date.parse(selected.checked_at) <= 30000 && now - Date.parse(selected.checked_at) >= -5000;
  const sourceChosen = mode === 'link' && !versions.isFetching && !versions.isError && versions.data?.items.some(row => row.version === sourceVersion && row.version < context.contractVersion);
  const canSave = fresh && note.trim().length >= 20 && note.length <= 4000 && !note.includes('\0') && (mode === 'link'
    ? sourceChosen && selected!.status === 'available_for_review' && selected!.source_version < context.contractVersion
    : mode === 'withdraw' && selected!.reference_type === 'linked' && !!selected!.link_id && selected!.status !== 'reference_withdrawn');
  function switchMode(value: 'link' | 'withdraw' | null) { if (locked) return; setMode(value); setArtifact(''); setSourceVersion(null); setCursors([null]); setVersionCursors([null]); setNote(''); setMessage(''); }
  function refresh() { if (disabled || locked) return; if (mode === 'link') void versions.refetch(); if (viewedVersion !== null) void references.refetch(); }
  async function save() {
    if (lock.current || disabled || blocked || (!pending && !canSave)) return;
    const firstAttempt = !pending; let saved = pending, sent = false;
    lock.current = true; setBusy(true); setMessage('Saving the document reference…');
    try {
      if (!saved) {
        if (!selected || Date.now() - Date.parse(selected.checked_at) > 30000) throw new Error('Refresh source choices before saving.');
        const value = pendingLinkSchema.parse(mode === 'link' ? { version: 1, kind: 'link', context,
          request: { id: crypto.randomUUID(), source_version: selected.source_version, artifact_id: selected.artifact_id,
            verification_id: selected.verification_id, sha256: selected.sha256, note } }
          : { version: 1, kind: 'withdraw', context, linkId: selected.link_id, request: { id: crypto.randomUUID(), reason: note } });
        saved = preserveLink(sessionStorage, value); setPending(saved);
      }
      sent = true;
      const path = `${base}/versions/${saved.context.contractVersion}/document-links${saved.kind === 'withdraw' ? `/${saved.linkId}/withdrawals` : ''}`;
      const response = await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      clearConfirmedLink(sessionStorage, saved, await response.json());
      void client.invalidateQueries({ predicate: query => query.queryKey.includes(context.workspaceId) && query.queryKey.includes(context.contractId) });
      if (mounted.current) { setPending(null); setMode(null); setNote(''); setArtifact(''); setMessage(saved.kind === 'link'
        ? 'Original document referenced. Complete a new review for this contract version.' : 'Reference withdrawn. The original document and previous review history are preserved.'); onSaved(); }
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && error instanceof ApiError && error.rejectedLink) {
        try { clearRejectedLink(sessionStorage, saved, true, true); setPending(null); setMode(null); setMessage('The reference change was not saved. Refresh the contract and resolve its current restriction.'); onSaved(); return; }
        catch { /* Keep uncertain storage held. */ }
      }
      if (!saved && sent === false && !(error instanceof Error && error.message.startsWith('Refresh source'))) setBlocked(true);
      setMessage(saved ? 'Save is unconfirmed. Retry the same saved reference request; do not replace it.' : error instanceof Error ? error.message : 'Document reference preparation is unavailable.');
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Supporting document references" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <h3 className="font-semibold">Reuse an earlier document</h3><p className="text-sm">Keep the original file and its history while referencing it for contract version {context.contractVersion}. A reference does not carry approval forward.</p>
    {blocked ? <p role="alert">The saved reference could not be read safely. Reconcile it before starting another change.</p> : pending ? <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-2">
      <h4 className="font-semibold">Recover the saved reference</h4><p>{pending.kind === 'link' ? `Reference original document version ${pending.request.source_version}` : 'Withdraw an explicit reference'} · Contract version {pending.context.contractVersion}</p>
      <p className="whitespace-pre-wrap break-words">{pending.kind === 'link' ? pending.request.note : pending.request.reason}</p><p className="text-sm">The original source and request stay fixed until confirmed.</p>
    </div> : context.contractVersion < 2 ? <p className="text-sm">Earlier documents become available after a new draft version is saved.</p> : <>
      {disabled && <p role="alert">Finish the open document, terms or review step before changing references.</p>}
      {mode === null ? <div className="flex flex-wrap gap-2"><button className={button} disabled={disabled || locked} onClick={() => switchMode('link')}>Choose an earlier document</button><button className={button} disabled={disabled || locked} onClick={() => switchMode('withdraw')}>Withdraw a reference</button></div>
        : <fieldset disabled={disabled || locked} className="space-y-3 min-w-0"><legend className="font-medium">{mode === 'link' ? 'Choose the original source' : 'Withdraw an explicit reference'}</legend>
          {mode === 'link' && <><p className="text-sm">Documents already cited by saved terms are carried forward automatically. They do not need another reference.</p>
            <label className="block text-sm">Earlier contract version<select className={input} value={sourceVersion ?? ''} onChange={e => { setSourceVersion(e.target.value ? Number(e.target.value) : null); setArtifact(''); setCursors([null]); }}><option value="">Choose a saved version</option>{versions.data?.items.filter(row => row.version < context.contractVersion).map(row => <option key={row.id} value={row.version}>Version {row.version} · {new Date(row.created_at).toLocaleDateString()}</option>)}</select></label>
            {versions.isError && <p role="alert">Version history could not be confirmed. Refresh the contract.</p>}
            <nav aria-label="Earlier version pages" className="flex flex-wrap gap-2"><button type="button" className={button} disabled={versions.isFetching || versionCursors.length === 1} onClick={() => { setVersionCursors(c => c.slice(0, -1)); setSourceVersion(null); setArtifact(''); setCursors([null]); }}>Previous versions</button><button type="button" className={button} disabled={versions.isFetching || versions.isError || !versions.data?.next_after} onClick={() => { setVersionCursors(c => [...c, versions.data!.next_after]); setSourceVersion(null); setArtifact(''); setCursors([null]); }}>More versions</button></nav></>}
          <label className="block text-sm">Reference document type<select className={input} value={kind} onChange={e => { setKind(e.target.value as keyof typeof purposes); setArtifact(''); setCursors([null]); }}>{Object.entries(purposes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label className="block text-sm">{mode === 'link' ? 'Original document to reference' : 'Reference to withdraw'}<select className={input} value={artifact} onChange={e => setArtifact(e.target.value)}><option value="">Choose a document</option>{references.data?.items.filter(row => mode === 'link' || row.reference_type === 'linked').map((row, index) => <option key={row.artifact_id} value={row.artifact_id} disabled={mode === 'link' ? row.status !== 'available_for_review' : row.status === 'reference_withdrawn'}>{index + 1}. {new Date(row.source_created_at).toLocaleDateString()} · Original version {row.source_version} · {row.status === 'reference_withdrawn' ? 'Withdrawn' : row.status === 'available_for_review' ? 'Available' : 'Needs review'}</option>)}</select></label>
          {references.isFetching && <p role="status">Loading original document choices…</p>}
          {references.isError && <p role="alert">Document references could not be confirmed.</p>}
          {!references.isFetching && !references.isError && references.data && !references.data.items.some(row => mode === 'link' || row.reference_type === 'linked') && <p className="text-sm">{mode === 'link' ? 'No supporting documents on this page. Choose another version or document type.' : 'No explicit references on this page. Documents carried by terms are managed through a new terms version.'}</p>}
          {selected && <p className="rounded-lg border bg-white p-3 text-sm">Original document version {selected.source_version} → Contract version {context.contractVersion}. {mode === 'withdraw' ? 'Withdrawal removes this reference from current review authority; it does not delete the original file.' : 'The original file, verification and creation record are retained.'}</p>}
          {selected && !fresh && <p role="alert">Refresh choices before saving this change.</p>}
          {mode === 'withdraw' && <p className="text-xs">Only explicit references can be withdrawn here. Documents cited by terms require a new terms version. A withdrawn reference is retained in history and cannot be silently reinstated.</p>}
          <nav aria-label="Reference document pages" className="flex flex-wrap gap-2"><button type="button" className={button} disabled={references.isFetching || cursors.length === 1} onClick={() => { setCursors(c => c.slice(0, -1)); setArtifact(''); }}>Previous reference documents</button><button type="button" className={button} disabled={references.isFetching || references.isError || !references.data?.next_after} onClick={() => { setCursors(c => [...c, references.data!.next_after]); setArtifact(''); }}>More reference documents</button><button type="button" className={button} disabled={versions.isFetching || references.isFetching} onClick={refresh}>Refresh reference choices</button></nav>
          <label className="block text-sm">Reason for this reference change<textarea className={input} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label><p className="text-xs">Explain the change in at least 20 characters.</p>
          <button type="button" className={button} onClick={() => switchMode(null)}>Cancel unsaved reference change</button>
        </fieldset>}
    </>}
    {(pending || mode) && <button className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || locked && !pending || busy || blocked || (!pending && !canSave)} onClick={() => { void save(); }}>{busy ? 'Saving…' : pending ? 'Retry saved reference' : mode === 'link' ? 'Save document reference' : 'Confirm reference withdrawal'}</button>}
    {message && <p role="status" className="text-sm">{message}</p>}<p className="text-xs">Reference changes do not approve, sign, send, market or assign an agreement.</p>
  </section>;
}
