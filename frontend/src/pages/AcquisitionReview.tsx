import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { AcquisitionUnderwriting } from '@/pages/AcquisitionUnderwriting';
import { InboundRequestQueue } from '@/components/acquisition/InboundRequestQueue';
import { IntakeReview } from '@/components/acquisition/IntakeReview';
import { CampaignDrafts } from '@/components/acquisition/CampaignDrafts';
import { InquiryHealth } from '@/components/acquisition/InquiryHealth';
import { ScenarioSummary } from '@/components/acquisition/ScenarioSummary';

type Workspace = { id: string; name: string };
type Action = 'amount_approved' | 'rejected' | 'withdrawn' | 'approval_revoked';
type Offer = {
  offer_id: string; workspace_id: string; lead_id: string; property_id: string;
  analysis_id: string; analysis_revision: number; latest_analysis_revision: number;
  case: string; amount: number; ceiling: number; proposal_note: string;
  historical_status: string; sequence: number; amount_approval_current: boolean;
  amount_review_blockers: string[]; available_review_actions: Action[]; checked_at: string;
};
type Page = { items: Offer[]; next_after: string | null };
type Scenario = { address?: string; city?: string; id: string; acquisition_inputs: unknown; acquisition_outputs: unknown; calculation_version: string };
type Review = { id: string; expected_sequence: number; status: Action; note: string; review_notes: Record<string, string> };
const labels: Record<Action, string> = { amount_approved: 'Approve amount', rejected: 'Reject proposal', withdrawn: 'Withdraw proposal', approval_revoked: 'Revoke amount approval' };
const diligence = ['title', 'liens', 'occupancy', 'valuation', 'repairs', 'financing', 'downside'];
const button = 'rounded-lg border px-4 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed';
const input = 'w-full rounded-lg border border-gray-300 p-2 bg-white';
const money = (value: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
const message = (error: unknown) => error instanceof Error ? error.message : 'Request unavailable. Refresh and try again.';
async function read<T>(path: string, signal?: AbortSignal): Promise<T> { return (await apiFetch(path, { signal })).json(); }

export function AcquisitionReview({ userId }: { userId: string }) {
  const [workspace, setWorkspace] = useState('');
  const [campaignPending, setCampaignPending] = useState(false);
  const spaces = useQuery({ queryKey: ['acquisition-review', userId, 'workspaces'],
    queryFn: ({ signal }) => read<Workspace[]>('/api/acquisition/workspaces', signal), retry: false, gcTime: 0, staleTime: 0 });
  return <main className="max-w-6xl mx-auto p-6 space-y-6">
    <header><h1 className="text-2xl font-bold text-[#1B3A5C]">Acquisition workflow</h1>
      <p className="text-gray-600 mt-2">Prepare campaigns, review seller inquiries, evaluate the property, and review the proposed amount in one workspace.</p><p className="text-sm text-gray-500 mt-2">These review steps support your existing acquisition process. Amount approval does not send an offer or approve a contract.</p></header>
    {spaces.isPending && <p role="status">Loading your workspaces…</p>}
    {spaces.isError && <p role="alert">{message(spaces.error)}</p>}
    {spaces.data && <label className="block max-w-md">Workspace<select className={input} disabled={campaignPending} value={workspace} onChange={e => setWorkspace(e.target.value)}>
      <option value="">Select a workspace</option>{spaces.data.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></label>}
    {spaces.data?.length === 0 && <p>No acquisition workspace is available to your account.</p>}
    {workspace && spaces.data?.some(w => w.id === workspace) && <WorkspaceReview key={`${userId}:${workspace}`} userId={userId} workspace={workspace} onCampaignPending={setCampaignPending} />}
  </main>;
}

const reviewSteps = [
  { id: 'prepare', title: 'Prepare campaigns', detail: 'Choose the channel and budget. For mail, prepare the message and verify where sellers will respond.' },
  { id: 'sellers', title: 'Review seller inquiries', detail: 'Resolve intake issues, review callback requests, and confirm the seller and property information.' },
  { id: 'evaluate', title: 'Evaluate the property', detail: 'Review the evidence and costs, then prepare a proposed amount.' },
  { id: 'decide', title: 'Review the proposed amount', detail: 'Check the supporting analysis and record your decision. Contract approval and delivery are separate steps.' },
];

function ReviewStep({ index, children }: { index: number; children: ReactNode }) {
  const step = reviewSteps[index];
  return <section id={`acquisition-${step.id}`} aria-labelledby={`acquisition-${step.id}-title`} tabIndex={-1} className="scroll-mt-6 rounded-xl border border-gray-200 bg-gray-50 p-4 sm:p-5 space-y-4 focus:outline-none focus:ring-2 focus:ring-[#E8720C]">
    <header className="flex gap-3 items-start">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#1B3A5C] text-[#E8720C] font-bold" aria-hidden="true">{index + 1}</span>
      <div><p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Review step {index + 1} of 4</p><h2 id={`acquisition-${step.id}-title`} className="text-lg font-bold text-[#1B3A5C]">{step.title}</h2><p className="text-sm text-gray-600 mt-1">{step.detail}</p></div>
    </header>
    {children}
  </section>;
}

function WorkspaceReview({ userId, workspace, onCampaignPending }: { userId: string; workspace: string; onCampaignPending: (pending: boolean) => void }) {
  const [inboundPending,setInboundPending] = useState(false);
  const [draftPending,setDraftPending] = useState(false);
  useEffect(()=>{onCampaignPending(inboundPending || draftPending);},[inboundPending,draftPending,onCampaignPending]);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selected, setSelected] = useState<Offer | null>(null);
  const after = cursors[cursors.length - 1];
  const base = `/api/acquisition/workspaces/${workspace}`;
  const queue = useQuery({ queryKey: ['acquisition-review', userId, workspace, 'queue', after],
    queryFn: ({ signal }) => read<Page>(`${base}/offers?limit=20${after ? `&after=${after}` : ''}`, signal), retry: false, gcTime: 0, staleTime: 0 });
  return <section className="space-y-6">
    <nav aria-label="Acquisition review steps" className="rounded-xl bg-[#1B3A5C] p-4 sm:p-5 text-white">
      <p className="font-semibold">Your acquisition review path</p><p className="text-sm text-white/80 mt-1">Jump to the work you need. Step numbers show the order of review, not completion or launch approval.</p>
      <ol className="grid gap-2 mt-4 sm:grid-cols-2 lg:grid-cols-4">{reviewSteps.map((step, index) => <li key={step.id}><a href={`#acquisition-${step.id}`} className="flex gap-2 items-center rounded-lg bg-white/10 p-3 text-sm hover:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#E8720C]"><span className="font-bold text-[#E8720C]">{index + 1}</span>{step.title}</a></li>)}</ol>
    </nav>
    <ReviewStep index={0}><CampaignDrafts userId={userId} workspace={workspace} onPending={setDraftPending} /></ReviewStep>
    <ReviewStep index={1}><InquiryHealth userId={userId} workspace={workspace} />
    <InboundRequestQueue key={`${userId}:${workspace}`} userId={userId} workspace={workspace} onPending={setInboundPending} />
    <IntakeReview userId={userId} workspace={workspace} /></ReviewStep>
    <ReviewStep index={2}><AcquisitionUnderwriting userId={userId} workspace={workspace} onProposed={() => { void queue.refetch(); }} /></ReviewStep>
    <ReviewStep index={3}>
    <div className="flex justify-between items-center"><h2 className="text-lg font-semibold">Proposals and review history</h2>
      <button className={button} disabled={queue.isFetching} onClick={() => { setSelected(null); void queue.refetch(); }}>Refresh queue</button></div>
    {queue.isFetching ? <p role="status">Loading proposals…</p> : queue.isError ? <p role="alert">{message(queue.error)}</p> : <>
      {queue.data?.items.length === 0 && <p>No proposals on this page.</p>}
      <div className="grid gap-3 md:grid-cols-2">{queue.data?.items.map(offer => <button key={offer.offer_id} className="border rounded-xl bg-white p-4 text-left hover:border-blue-500" onClick={() => setSelected(offer)}>
        <span className="font-semibold text-lg">{money(offer.amount)}</span><span className="block text-sm">Scenario {offer.analysis_revision} · {offer.case} case</span>
        <span className="block text-sm text-gray-600">{offer.historical_status.replaceAll('_', ' ')}{offer.historical_status === 'amount_approved' && !offer.amount_approval_current ? ' · review required' : ''}</span>
        <span className="block text-xs break-all mt-2">Lead {offer.lead_id}</span><span className="block mt-2 text-blue-700">Open review</span>
      </button>)}</div>
    </>}
    <nav aria-label="Proposal pages" className="flex gap-2"><button className={button} disabled={cursors.length === 1 || queue.isFetching} onClick={() => { setSelected(null); setCursors(c => c.slice(0, -1)); }}>Previous</button>
      <button className={button} disabled={!queue.data?.next_after || queue.isFetching || queue.isError} onClick={() => { const next = queue.data?.next_after; if (next) { setSelected(null); setCursors(c => [...c, next]); } }}>Next</button></nav>
    {selected && <OfferReview key={selected.offer_id} userId={userId} workspace={workspace} selected={selected} onSaved={() => { void queue.refetch(); }} />}
    </ReviewStep>
  </section>;
}

function OfferReview({ userId, workspace, selected, onSaved }: { userId: string; workspace: string; selected: Offer; onSaved: () => void }) {
  const base = `/api/acquisition/workspaces/${workspace}`;
  const [action, setAction] = useState<Action | ''>('');
  const [note, setNote] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [acknowledged, setAcknowledged] = useState(false);
  const [pending, setPending] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [feedback, setFeedback] = useState('');
  const state = useQuery({ queryKey: ['acquisition-review', userId, workspace, selected.offer_id, 'state'],
    queryFn: ({ signal }) => read<Offer>(`${base}/offers/${selected.offer_id}/state`, signal), retry: false, gcTime: 0, staleTime: 0 });
  const evidence = useQuery({ queryKey: ['acquisition-review', userId, workspace, selected.analysis_id, 'evidence'],
    queryFn: async ({ signal }) => {
      const [rows, property] = await Promise.all([
        read<Scenario[]>(`${base}/leads/${selected.lead_id}/underwriting/scenarios?after=${selected.analysis_revision - 1}&limit=1`, signal),
        read<{ id: string; property_id: string; property_address: string; city: string }>(`${base}/leads/${selected.lead_id}/summary`, signal),
      ]);
      if (property.id !== selected.lead_id || property.property_id !== selected.property_id || !property.property_address) throw new Error('The property identity could not be confirmed.');
      if (rows.length !== 1 || rows[0].id !== selected.analysis_id) throw new Error('The exact underwriting revision could not be loaded.');
      return { ...rows[0], address: property.property_address, city: property.city };
    }, retry: false, gcTime: 0, staleTime: 0 });
  const history = useQuery({ queryKey: ['acquisition-review', userId, workspace, selected.offer_id, 'history'],
    queryFn: ({ signal }) => read<{ id: string; sequence: number; status: string; note: string; review_notes: Record<string, string> }[]>(`${base}/offers/${selected.offer_id}/reviews?limit=50`, signal), retry: false, gcTime: 0, staleTime: 0 });
  const offer = state.data;
  const valid = action && note.trim() && acknowledged && (action !== 'amount_approved' || diligence.every(key => notes[key]?.trim()));
  async function submit() {
    if (inFlight.current || (!pending && (!valid || !offer || !evidence.data || state.isError || evidence.isError))) return;
    inFlight.current = true; setBusy(true); setFeedback('');
    let request = pending;
    try {
      if (!request) {
        const fresh = await read<Offer>(`${base}/offers/${selected.offer_id}/state`);
        if (fresh.sequence !== offer!.sequence || fresh.analysis_id !== selected.analysis_id || !fresh.available_review_actions.includes(action as Action)) {
          await state.refetch(); throw new Error('This proposal changed. Review the refreshed state before deciding.');
        }
        request = { id: crypto.randomUUID(), expected_sequence: fresh.sequence, status: action as Action, note: note.trim(), review_notes: action === 'amount_approved' ? notes : {} };
        setPending(request);
      }
      const result = await readResult(request);
      if (!(result.status in labels)) throw new Error('Decision result unconfirmed');
      setPending(null); setAction(''); setNote(''); setNotes({}); setAcknowledged(false);
      setFeedback(`Decision recorded: ${result.status.replaceAll('_', ' ')}. No offer was sent.`);
      await Promise.all([state.refetch(), history.refetch()]); onSaved();
    } catch (error) {
      const definite = error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (definite) { setPending(null); await state.refetch(); }
      setFeedback(request && !definite ? 'The result is unconfirmed. Retry this same decision to reconcile it, or refresh the history before leaving.' : message(error));
    } finally { inFlight.current = false; setBusy(false); }
  }
  async function readResult(request: Review): Promise<{ status: string }> {
    return (await apiFetch(`${base}/offers/${selected.offer_id}/reviews`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
  }
  return <section aria-label="Selected offer review" className="border rounded-xl bg-white p-5 space-y-4">
    <h2 className="text-xl font-semibold">Review {money(selected.amount)}</h2>
    {evidence.data && !evidence.isError && <p className="font-medium">{evidence.data.address}, {evidence.data.city}</p>}
    {state.isFetching && <p role="status">Checking current review state…</p>}
    {state.isError && <p role="alert">{message(state.error)}</p>}
    {offer && !state.isError && <>
      <dl className="grid gap-2 text-sm"><div><dt className="font-semibold">Property reference</dt><dd className="break-all">{offer.property_id}</dd></div>
        <div><dt className="font-semibold">Underwriting</dt><dd>Revision {offer.analysis_revision}, {offer.case} case · latest revision {offer.latest_analysis_revision} · ceiling {money(offer.ceiling)}</dd></div>
        <div><dt className="font-semibold">Proposal rationale</dt><dd>{offer.proposal_note}</dd></div>
        <div><dt className="font-semibold">Historical decision</dt><dd>{offer.historical_status.replaceAll('_', ' ')}</dd></div></dl>
      {offer.amount_review_blockers.length > 0 && <ul className="text-amber-800 list-disc pl-5">{offer.amount_review_blockers.map(reason => <li key={reason}>{reason.toLowerCase().replaceAll('_', ' ')}</li>)}</ul>}
      <p className="text-sm text-gray-600">Checked {new Date(offer.checked_at).toLocaleString()}. Document approval and delivery checks are separate.</p>
    </>}
    {evidence.isPending && <p role="status">Loading exact underwriting evidence…</p>}
    {evidence.isError && <p role="alert">{message(evidence.error)}</p>}
    {evidence.data && !evidence.isError && <ScenarioSummary output={evidence.data.acquisition_outputs} />}
    {evidence.data && !evidence.isError && <details><summary className="cursor-pointer font-medium">Underwriting inputs, provenance and results — {evidence.data.calculation_version}</summary>
      <pre className="text-xs whitespace-pre-wrap break-words max-h-96 overflow-auto bg-gray-50 p-3 mt-2">{JSON.stringify({ inputs: evidence.data.acquisition_inputs, results: evidence.data.acquisition_outputs }, null, 2)}</pre></details>}
    <details><summary className="cursor-pointer font-medium">Decision history</summary>
      {history.isError ? <p role="alert">{message(history.error)}</p> : history.isPending ? <p>Loading decisions…</p> : <ol className="space-y-3 mt-2">{history.data?.map(event => <li key={event.id}><strong>{event.sequence}. {event.status.replaceAll('_', ' ')}</strong><p>{event.note}</p>{Object.entries(event.review_notes).map(([key, value]) => <p key={key} className="text-sm">{key}: {value}</p>)}</li>)}</ol>}
    </details>
    <fieldset disabled={busy || !!pending || state.isFetching || state.isError || !evidence.data || evidence.isError} className="space-y-3">
      <legend className="font-semibold">Your decision</legend>
      <label className="block">Action<select className={input} value={action} onChange={e => setAction(e.target.value as Action | '')}><option value="">Choose a decision</option>{offer?.available_review_actions.map(a => <option key={a} value={a}>{labels[a]}</option>)}</select></label>
      <label className="block">Decision note<textarea className={input} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label>
      {action === 'amount_approved' && <div className="grid gap-3 md:grid-cols-2">{diligence.map(key => <label key={key} className="block capitalize">{key} review<textarea className={input} maxLength={4000} value={notes[key] ?? ''} onChange={e => setNotes(n => ({ ...n, [key]: e.target.value }))} /></label>)}</div>}
      <label className="flex gap-2 items-start"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} />I reviewed this proposal and its evidence. This decision does not send an offer or approve a binding document.</label>
    </fieldset>
    <button className={`${button} bg-[#1B3A5C] text-white`} disabled={busy || (!pending && (!valid || state.isFetching || state.isError || evidence.isError || !evidence.data || !offer?.available_review_actions.includes(action as Action)))} onClick={() => { void submit(); }}>{busy ? 'Recording…' : pending ? 'Retry same decision' : 'Record decision'}</button>
    {feedback && <p role="status">{feedback}</p>}
  </section>;
}
