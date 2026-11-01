import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import type { DocumentContext } from '@/lib/acquisition/contract-documents';
import { parseTransitionChoice, readPendingTransition, preserveTransition, clearConfirmedTransition,
  clearRejectedTransition, type PendingTransition } from '@/lib/acquisition/contract-transition';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const holds = { version_changed: 'The contract version changed. Refresh the draft information above.', paused: 'Acquisition review is paused.',
  awaiting_signature: 'This contract is already awaiting signature. A signed agreement still needs separate confirmation.',
  execution_review_required: 'Complete a current returned-agreement execution review above.',
  execution_recorded: 'Execution is already recorded. Title and disposition review are separate next steps.',
  history_requires_review: 'The contract history needs administrator review.', signature_review_required: 'Complete a current signature-release review above.',
  ready_for_human_review: 'Current review checks passed. Confirm the proposed status below.' };
type Props = { currentStatus?: 'draft' | 'pending_signature' | 'executed'; context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function ContractTransitionForm(props: Props) {
  return <TransitionEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function TransitionEditor({ context, disabled, onPending, onSaved, currentStatus = 'draft' }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingTransition(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([key, value]) => context[key as keyof DocumentContext] !== value)) throw new Error('Context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingTransition | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false);
  const [reason, setReason] = useState(''), [confirmed, setConfirmed] = useState(false), [message, setMessage] = useState('');
  const [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), client = useQueryClient();
  const held = expanded || busy || !!pending || blocked;
  const base = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/transitions`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!expanded && !pending) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [expanded, pending]);
  useEffect(() => { if (!held) return; const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const choice = useQuery({ queryKey: ['contract-transition-choice', context.userId, context.workspaceId, context.contractId, context.contractVersion],
    enabled: expanded && !disabled && !pending && !blocked, retry: false, staleTime: 0, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
    queryFn: async ({ signal }) => parseTransitionChoice(await (await apiFetch(`${base}/candidate?contract_version=${context.contractVersion}`, { signal, cache: 'no-store' })).json(), context) });
  const fresh = !disabled && !blocked && !choice.isError && !choice.isFetching && choice.data
    && (!choice.data.candidate || Date.parse(choice.data.candidate.expires_at) > now)
    && now - Date.parse(choice.data.checked_at) <= 30000 && now - Date.parse(choice.data.checked_at) >= -5000;
  const candidate = fresh && choice.data?.candidate && Date.parse(choice.data.candidate.expires_at) > now ? choice.data.candidate : null;
  const executionStep = (pending?.request.target_status ?? candidate?.target_status ?? (currentStatus === 'draft' ? 'pending_signature' : 'executed')) === 'executed';
  const canSave = !!candidate && confirmed && reason.trim().length >= 20 && reason.length <= 4000 && !reason.includes('\0');
  function close() { if (pending || busy || blocked) return; setExpanded(false); setReason(''); setConfirmed(false); setMessage(''); }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !canSave)) return;
    const firstAttempt = !pending; let saved = pending, sent = false;
    lock.current = true; setBusy(true); setMessage('Saving the contract status…');
    try {
      if (!saved) {
        if (!candidate || !choice.data || Date.now() - Date.parse(choice.data.checked_at) > 30000 || Date.parse(candidate.expires_at) <= Date.now()) throw new Error('Choice expired');
        try { saved = preserveTransition(sessionStorage, { version: 1, context, request: { id: crypto.randomUUID(),
          expected_version: candidate.expected_version, expected_sequence: candidate.expected_sequence,
          expected_status: candidate.expected_status, target_status: candidate.target_status, reason } }); setPending(saved); }
        catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(base, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedTransition(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setReason(''); setConfirmed(false);
      setMessage(saved.request.target_status === 'executed' ? 'Executed status recorded. Title and disposition review remain separate steps.' : 'Contract recorded as awaiting signature. No agreement was sent or signed.');
      void client.invalidateQueries({ queryKey: ['contract-transition-choice', context.userId, context.workspaceId, context.contractId] }); onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedTransition) {
        try { clearRejectedTransition(sessionStorage, saved, true, true); setPending(null); setConfirmed(false);
          setMessage('The status change was not saved. Refresh the current checks before trying again.'); void choice.refetch(); }
        catch { setBlocked(true); setMessage('Saved status recovery needs reconciliation. Keep this tab and request details.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved status change; do not create another request.' : 'Status preparation could not be confirmed. Refresh checks or reconcile the saved request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Contract status handoff" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C]">
    <h3 className="font-semibold">{executionStep ? 'Record reviewed execution' : 'Move to awaiting signature'}</h3>
    <p className="text-sm text-gray-600">{executionStep ? 'After review of the returned agreement, record its executed status. This does not sign an agreement or authorize marketing or assignment.' : 'After signature-release review, record the next contract status. This does not send or sign an agreement.'}</p>
    {blocked && <p role="alert">Saved status-change details could not be read or preserved. Reconcile this tab before starting another request.</p>}
    {disabled && <p className="text-sm">Finish the current document, terms or review step before continuing.</p>}
    {!expanded && !pending ? <button type="button" className={button} disabled={disabled || blocked} onClick={() => { setNow(Date.now()); setExpanded(true); setMessage(''); }}>Review next contract status</button> : <>
      {pending ? <div className="rounded-lg border bg-white p-3 space-y-2"><h4 className="font-semibold">Recover the saved status change</h4><p>Contract version {context.contractVersion} · {pending.request.target_status === 'executed' ? 'Executed' : 'Awaiting signature'}</p><p className="whitespace-pre-wrap break-words">{pending.request.reason}</p><p className="text-sm">The original version, status and reason remain fixed until confirmed.</p></div>
        : <fieldset disabled={disabled || busy || blocked} className="space-y-3">
          <button type="button" className={button} disabled={choice.isFetching} onClick={() => { setConfirmed(false); setNow(Date.now()); void choice.refetch(); }}>Refresh contract status checks</button>
          {choice.isFetching && <p role="status">Checking this contract version and current review…</p>}
          {choice.isError && <p role="alert">Contract status choices could not be confirmed. Refresh before continuing.</p>}
          {fresh && choice.data && <p className="text-sm">{holds[choice.data.status]}</p>}
          {choice.data && !fresh && !choice.isFetching && !choice.isError && <p>These checks are out of date. Refresh before continuing.</p>}
          <div hidden={!candidate}><label className="block text-sm font-medium">Reason for the status change<textarea className="block w-full rounded-lg border border-gray-300 bg-white p-2" value={reason} maxLength={4000} onChange={event => setReason(event.target.value)} /></label>
          <p className="text-xs text-gray-600">Explain the handoff in at least 20 characters.</p>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />{executionStep ? 'I am recording execution based on the reviewed returned agreement. Title and disposition require separate review.' : 'I am recording this reviewed version as awaiting signature. This does not confirm a signed agreement.'}</label></div>
        </fieldset>}
      <div className="flex flex-wrap gap-2"><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || now < retryAt || (!pending && !canSave)} onClick={() => { void save(); }}>{pending ? 'Retry saved status change' : executionStep ? 'Record executed status' : 'Record awaiting signature'}</button>
        {!pending && <button type="button" className={button} disabled={busy || blocked} onClick={close}>Close status review without saving</button>}</div>
    </>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
