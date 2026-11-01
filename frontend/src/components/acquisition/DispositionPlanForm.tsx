import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import type { DocumentContext } from '@/lib/acquisition/contract-documents';
import { exitLabels, parsePlanState, readPendingPlan, preservePlan, pendingPlanSchema, clearConfirmedPlan, clearRejectedPlan, type PendingPlan } from '@/lib/acquisition/disposition-plan';
const button = 'rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
const holds = { ready_for_planning: 'Choose an internal proposal for the next review.', paused: 'Acquisition is paused. You may withdraw your latest personal proposal.', contract_unavailable: 'Confirm the current contract is in title review before proposing a path.', history_limit_reached: 'Proposal history needs administrator attention.' };
type Props = { context: DocumentContext; disabled: boolean; onPending: (value: boolean) => void; onSaved: () => void };
export function DispositionPlanForm(props: Props) {
  return <PlanEditor key={`${props.context.userId}:${props.context.workspaceId}:${props.context.contractId}:${props.context.contractVersion}`} {...props} />;
}
function PlanEditor({ context, disabled, onPending, onSaved }: Props) {
  const [initial] = useState(() => { try {
    const saved = readPendingPlan(sessionStorage, context.userId, context.workspaceId);
    if (saved && Object.entries(saved.context).some(([k, v]) => context[k as keyof DocumentContext] !== v)) throw new Error('Proposal context changed');
    return { saved, blocked: false };
  } catch { return { saved: null, blocked: true }; } });
  const [pending, setPending] = useState<PendingPlan | null>(initial.saved), [blocked, setBlocked] = useState(initial.blocked);
  const [expanded, setExpanded] = useState(!!initial.saved), [busy, setBusy] = useState(false);
  const [exit, setExit] = useState<PendingPlan['request']['exit_type'] | ''>(''), [note, setNote] = useState('');
  const [withdraw, setWithdraw] = useState(false), [message, setMessage] = useState(''), [now, setNow] = useState(Date.now()), [retryAt, setRetryAt] = useState(0);
  const lock = useRef(false), mounted = useRef(true), queryClient = useQueryClient();
  const held = expanded || busy || !!pending || blocked;
  const scope = [context.userId, context.workspaceId, context.contractId, context.contractVersion];
  const path = `/api/acquisition/workspaces/${context.workspaceId}/contracts/${context.contractId}/versions/${context.contractVersion}/disposition-plan`;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { onPending(held); }, [held, pending, onPending]);
  useEffect(() => { if (!held) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [held]);
  useEffect(() => { if (!held) return; const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [held]);
  const state = useQuery({ queryKey: ['purchase-path', ...scope], enabled: expanded && !disabled && !blocked && !pending,
    queryFn: async ({ signal }) => parsePlanState(await (await apiFetch(path, { signal, cache: 'no-store' })).json(), context),
    retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false });
  const fresh = !disabled && !blocked && !state.isError && !state.isFetching && !!state.data
    && now - Date.parse(state.data.checked_at) <= 30000 && Date.parse(state.data.checked_at) - now <= 5000;
  const validNote = note.trim().length >= 20 && note.length <= 4000 && !note.includes('\0');
  const canSave = fresh && validNote && (withdraw ? !!state.data?.withdrawal : !!exit && state.data?.readiness === 'ready_for_planning');
  function close() { if (busy || pending || blocked) return; setExpanded(false); setExit(''); setNote(''); setWithdraw(false); }
  async function save() {
    if (lock.current || disabled || blocked || Date.now() < retryAt || (!pending && !canSave)) return;
    lock.current = true; setBusy(true); const firstAttempt = !pending; let saved = pending, sent = false;
    try {
      if (!saved) {
        const current = parsePlanState(state.data, context), original = current.withdrawal;
        if (withdraw ? !original : current.readiness !== 'ready_for_planning') throw new Error('Refresh purchase-path checks');
        saved = pendingPlanSchema.parse({ version: 1, context, request: { id: crypto.randomUUID(), expected_version: context.contractVersion,
          expected_sequence: current.sequence, status: withdraw ? 'withdrawn' : 'proposed', exit_type: withdraw ? original!.exit_type : exit,
          original_plan_id: withdraw ? original!.plan_id : null, note } });
        try { saved = preservePlan(sessionStorage, saved); setPending(saved); } catch (error) { setBlocked(true); throw error; }
      }
      sent = true;
      const response = await apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(saved.request), signal: AbortSignal.timeout(30000) });
      const receipt = await response.json(); if (!mounted.current) return;
      clearConfirmedPlan(sessionStorage, saved, receipt); setPending(null); setExpanded(false); setExit(''); setNote(''); setWithdraw(false);
      setMessage(saved.request.status === 'withdrawn' ? 'Proposal withdrawn. The original remains in history.' : 'Internal proposal saved. Title and disposition approval are still required before marketing, assignment or closing.');
      void queryClient.invalidateQueries({ queryKey: ['purchase-path', context.userId, context.workspaceId, context.contractId] }); onSaved();
    } catch (error) {
      if (!mounted.current) return;
      if (saved && firstAttempt && sent && error instanceof ApiError && error.rejectedPlan) {
        try { clearRejectedPlan(sessionStorage, saved, true, true); setPending(null); setMessage('The proposal was not saved. Refresh checks and resolve the restriction.'); void state.refetch(); }
        catch { setBlocked(true); setMessage('Saved proposal recovery needs reconciliation. Keep the original request.'); }
      } else setMessage(sent ? 'Save is unconfirmed. Retry the same saved proposal to avoid duplicates.' : 'Proposal preparation could not be confirmed. Refresh checks or reconcile the original request.');
      if (error instanceof ApiError && error.status === 429) setRetryAt(Date.now() + (error.retryAfterSeconds ?? 30) * 1000);
    } finally { lock.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Purchase path" className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 space-y-3 text-[#1B3A5C] min-w-0">
    <h3 className="font-semibold">Plan the purchase path</h3><p className="text-sm text-gray-600">Choose how Hilltop proposes to proceed. Title, legal and disposition approvals remain separate next steps.</p>
    {blocked && <p role="alert">Saved purchase-path details could not be read safely. Reconcile the original request before continuing.</p>}
    {!expanded && !blocked && <button type="button" className={button} disabled={disabled} onClick={() => setExpanded(true)}>Open purchase path</button>}
    {expanded && !pending && !blocked && <>
      {disabled && <p role="alert">Confirm the contract and finish the adjacent pending step first.</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className={button} disabled={disabled || busy || state.isFetching} onClick={() => { setNow(Date.now()); void state.refetch(); }}>Refresh purchase-path checks</button><button type="button" className={button} disabled={busy} onClick={close}>Close without saving</button></div>
      {state.isError && <p role="alert">Current purchase-path details could not be confirmed.</p>}
      {!fresh && !state.isFetching && <p role="status">Refresh purchase-path checks before saving.</p>}
      {fresh && state.data && <><p role="status" className="text-sm">{holds[state.data.readiness]}</p>
        {state.data.latest && <div className="rounded-lg border bg-white p-3 text-sm space-y-1"><p className="font-semibold">{state.data.latest.status === 'withdrawn' ? 'Withdrawn proposal' : 'Current internal proposal'}: {exitLabels[state.data.latest.exit_type]}</p><p className="whitespace-pre-wrap break-words">{state.data.latest.note}</p><p>This record grants no authority to market, assign or close.</p></div>}</>}
      <fieldset disabled={disabled || busy} className="space-y-3 min-w-0"><legend className="font-medium">{withdraw ? 'Withdraw your original proposal' : '1. Choose a purchase path'}</legend>
        {!withdraw ? <label className="block text-sm">Proposed purchase path<select className={input} value={exit} onChange={e => setExit(e.target.value as typeof exit)}><option value="">Choose a path for review</option>{Object.entries(exitLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          : <p className="text-sm">Your latest personal proposal will be withdrawn. Its original path and explanation remain in history.</p>}
        {exit === 'wholesale_assignment' && !withdraw && <p className="text-sm">Assignment requires separate review of the executed contract, title, legal basis and disclosures before any buyer distribution.</p>}
        <label className="block text-sm">{withdraw ? 'Withdrawal reason' : '2. Explain the proposed path'}<textarea className={input} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label><p className="text-xs">At least 20 characters. This is an internal proposal, not an offer or approval.</p>
        <div className="flex flex-wrap gap-2"><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={!canSave || now < retryAt} onClick={() => { void save(); }}>{withdraw ? 'Record proposal withdrawal' : '3. Save internal proposal'}</button>
          {withdraw ? <button type="button" className={button} onClick={() => { setWithdraw(false); setNote(''); }}>Back to purchase path</button> : fresh && state.data?.withdrawal && <button type="button" className={button} onClick={() => { setWithdraw(true); setNote(''); }}>Withdraw my latest proposal</button>}</div>
      </fieldset>
    </>}
    {pending && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-3 min-w-0"><h4 className="font-semibold">Recover the saved purchase-path request</h4><p className="text-sm">Original contract version {pending.context.contractVersion}. {pending.request.status === 'withdrawn' ? 'Withdrawal' : 'Proposal'}: {exitLabels[pending.request.exit_type]}.</p><p className="text-sm whitespace-pre-wrap break-words">{pending.request.note}</p><button type="button" className={`${button} bg-[#1B3A5C] text-white`} disabled={disabled || busy || blocked || now < retryAt} onClick={() => { void save(); }}>{busy ? 'Checking saved proposal…' : 'Retry saved proposal'}</button></div>}
    {now < retryAt && <p role="status">Retry available in {Math.ceil((retryAt - now) / 1000)} seconds.</p>}{message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
