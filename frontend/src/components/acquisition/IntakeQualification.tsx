import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

type Assessment = { classification: string; reason_codes: string[]; missing_fields: string[]; policy_version: string;
  canonical_county: string | null; canonical_state: string | null; identity_link_current: boolean;
  ownership_verified: false; outreach_authorized: false; binding_offer: false; contact_permission_granted: false };
type Saved = { id: string; sequence: number; classification: string; created_at: string; assessment: Assessment };
type State = { assessment: Assessment; evidence_hash: string; sequence: number; latest_assessment: Saved | null; assessment_current: boolean };
type Request = { id: string; expected_sequence: number; evidence_hash: string };
const classifications = ['qualified', 'incomplete', 'duplicate', 'unqualified', 'requires_human_review'];
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const options = { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false } as const;
function validAssessment(value: Assessment) {
  return value && classifications.includes(value.classification) && typeof value.policy_version === 'string'
    && Array.isArray(value.reason_codes) && value.reason_codes.every(code => typeof code === 'string')
    && Array.isArray(value.missing_fields) && value.missing_fields.every(field => typeof field === 'string')
    && (value.canonical_county === null || typeof value.canonical_county === 'string')
    && (value.canonical_state === null || typeof value.canonical_state === 'string')
    && typeof value.identity_link_current === 'boolean' && value.ownership_verified === false && value.outreach_authorized === false
    && value.binding_offer === false && value.contact_permission_granted === false;
}
function validSaved(value: Saved) {
  return value && typeof value.id === 'string' && Number.isInteger(value.sequence) && value.sequence > 0
    && typeof value.created_at === 'string' && classifications.includes(value.classification)
    && validAssessment(value.assessment) && value.classification === value.assessment.classification;
}
async function load(path: string, signal?: AbortSignal): Promise<State> {
  const data = await (await apiFetch(path, { signal })).json();
  if (!validAssessment(data?.assessment) || !/^[a-f0-9]{64}$/.test(data.evidence_hash) || !Number.isInteger(data.sequence)
    || data.sequence < 0 || typeof data.assessment_current !== 'boolean'
    || (data.latest_assessment !== null && !validSaved(data.latest_assessment)) || (data.assessment_current && data.latest_assessment === null))
    throw new Error('Invalid qualification response');
  return data;
}

export function IntakeQualification({ userId, workspace, intake, revision, locked, onPending }: {
  userId: string; workspace: string; intake: string; revision: number; locked: boolean; onPending: (value: boolean) => void;
}) {
  const path = `/api/acquisition/workspaces/${workspace}/intakes/${intake}`;
  const [pending, setPending] = useState<Request | null>(null); const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(''); const inFlight = useRef(false); const [before, setBefore] = useState<number | null>(null);
  useEffect(() => { onPending(busy || !!pending); }, [busy, pending, onPending]);
  const state = useQuery({ ...options, queryKey: ['intake-qualification', userId, workspace, intake, revision], queryFn: ({ signal }) => load(`${path}/qualification-state`, signal) });
  const history = useQuery({ ...options, queryKey: ['intake-assessments', userId, workspace, intake, revision, before], queryFn: async ({ signal }): Promise<Saved[]> => {
    const rows = await (await apiFetch(`${path}/assessments?limit=20${before ? `&before=${before}` : ''}`, { signal })).json();
    if (!Array.isArray(rows) || !rows.every(validSaved)) throw new Error('Invalid assessment history');
    return rows;
  } });
  async function save() {
    if (inFlight.current || locked || (!pending && (!state.data || state.isFetching || state.isError || state.data.assessment_current))) return;
    inFlight.current = true; setBusy(true); setFeedback(''); let request = pending;
    try {
      if (!request) {
        const fresh = await load(`${path}/qualification-state`);
        if (fresh.evidence_hash !== state.data!.evidence_hash || fresh.sequence !== state.data!.sequence) throw new Error('Assessment changed');
        request = { id: crypto.randomUUID(), expected_sequence: fresh.sequence, evidence_hash: fresh.evidence_hash }; setPending(request);
      }
      const result = await (await apiFetch(`${path}/assessments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) })).json();
      if (result?.assessment_id !== request.id || result.sequence !== request.expected_sequence + 1 || !classifications.includes(result.classification)
        || typeof result.duplicate !== 'boolean' || result.outreach_authorized !== false) throw new Error('Unconfirmed result');
      setPending(null); setBefore(null); setFeedback('Assessment snapshot saved. No seller contact or offer was authorized.');
      void state.refetch(); void history.refetch();
    } catch (error) {
      const definite = error instanceof ApiError && [400, 401, 403, 404, 409, 422].includes(error.status);
      if (definite) { setPending(null); void state.refetch(); }
      setFeedback(request && !definite ? 'Save result unconfirmed. Retry the exact assessment request before closing this review.' : 'Assessment changed or access is unavailable. Refresh qualification before saving.');
    } finally { inFlight.current = false; setBusy(false); }
  }
  return <section aria-label="Intake qualification" className="rounded-lg border p-4 space-y-3">
    <h4 className="font-semibold">Current acquisition screening</h4>
    <p className="text-sm">Qualified means ready for further analysis. It does not verify title, grant permission to contact, or approve an offer.</p>
    {state.isFetching ? <p role="status">Checking qualification…</p> : state.isError ? <p role="alert">Current qualification unavailable. Saved results must not be treated as current.</p> : state.data && <>
      <p className="font-medium capitalize">{state.data.assessment.classification.replaceAll('_', ' ')}</p>
      <p className="text-sm">{state.data.assessment.reason_codes.map(code => code.replaceAll('_', ' ').toLowerCase()).join(' · ')}</p>
      <p className="text-sm">Missing: {state.data.assessment.missing_fields.join(', ') || 'None reported'}</p>
      <p className="text-sm">Canonical territory: {state.data.assessment.canonical_county ?? 'Unknown'}, {state.data.assessment.canonical_state ?? 'Unknown'}. Policy: {state.data.assessment.policy_version}.</p>
      <p className="text-sm">{state.data.assessment_current ? 'Latest saved assessment matches current evidence.' : state.data.latest_assessment ? 'Saved assessment is stale. Use the current screening above.' : 'This screening has not been saved yet.'}</p>
    </>}
    <div className="flex flex-wrap gap-2"><button className={button} disabled={locked || busy || (!pending && (!state.data || state.isError || state.isFetching || state.data.assessment_current))} onClick={() => { void save(); }}>{busy ? 'Saving assessment…' : pending ? 'Retry exact assessment request' : 'Save assessment snapshot'}</button>
      <button className={button} disabled={locked || busy || !!pending || state.isFetching} onClick={() => { void state.refetch(); void history.refetch(); }}>Refresh qualification</button></div>
    {feedback && <p role="status">{feedback}</p>}
    <h5 className="font-medium">Saved screening history</h5>
    {history.isFetching ? <p>Loading screening history…</p> : history.isError ? <p role="alert">Screening history unavailable.</p> : <>
      {!history.data?.length && <p>No saved assessments on this page.</p>}
      {history.data?.map(row => <div key={row.id} className="border rounded p-2 text-sm"><p>Version {row.sequence} · {row.classification.replaceAll('_', ' ')} · {row.created_at}</p><p>{row.assessment.reason_codes.map(code => code.replaceAll('_', ' ').toLowerCase()).join(' · ')}</p></div>)}
      <div className="flex gap-2"><button className={button} disabled={busy || !!pending || before === null} onClick={() => setBefore(null)}>Latest assessments</button>
        <button className={button} disabled={busy || !!pending || history.data?.length !== 20} onClick={() => setBefore(history.data!.at(-1)!.sequence)}>Older assessments</button></div>
    </>}
  </section>;
}
