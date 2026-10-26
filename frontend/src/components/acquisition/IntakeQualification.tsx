import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiError, apiFetch } from '@/lib/api';

import { loadQualification as load, validSaved, classifications } from '@/lib/intakeQualification';
import type { Saved } from '@/lib/intakeQualification';
import { ScenarioEditor } from '@/pages/AcquisitionUnderwriting';
import type { Analysis } from '@/pages/AcquisitionUnderwriting';
import { ScenarioSummary } from './ScenarioSummary';
type Request = { id: string; expected_sequence: number; evidence_hash: string };
const button = 'rounded-lg border px-3 py-2 text-sm disabled:opacity-40';
const options = { retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false } as const;

export function IntakeQualification({ userId, workspace, intake, revision, locked, onPending }: {
  userId: string; workspace: string; intake: string; revision: number; locked: boolean; onPending: (value: boolean) => void;
}) {
  const path = `/api/acquisition/workspaces/${workspace}/intakes/${intake}`;
  const [pending, setPending] = useState<Request | null>(null); const [busy, setBusy] = useState(false);
  const [underwriting, setUnderwriting] = useState<{ lead: string; hash: string } | null>(null);
  const [underwritingPending, setUnderwritingPending] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [qualificationCurrent, setQualificationCurrent] = useState(false);
  const [feedback, setFeedback] = useState(''); const inFlight = useRef(false); const [before, setBefore] = useState<number | null>(null);
  useEffect(() => { onPending(busy || !!pending || underwritingPending); }, [busy, pending, underwritingPending, onPending]);
  const state = useQuery({ ...options, queryKey: ['intake-qualification', userId, workspace, intake, revision], queryFn: ({ signal }) => load(`${path}/qualification-state`, signal) });
  const history = useQuery({ ...options, queryKey: ['intake-assessments', userId, workspace, intake, revision, before], queryFn: async ({ signal }): Promise<Saved[]> => {
    const rows = await (await apiFetch(`${path}/assessments?limit=20${before ? `&before=${before}` : ''}`, { signal })).json();
    if (!Array.isArray(rows) || !rows.every(validSaved)) throw new Error('Invalid assessment history');
    return rows;
  } });
  async function save() {
    if (inFlight.current || locked || underwritingPending || (!pending && (!state.data || state.isFetching || state.isError || state.data.assessment_current))) return;
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
    <div className="flex flex-wrap gap-2"><button className={button} disabled={locked || underwritingPending || busy || (!pending && (!state.data || state.isError || state.isFetching || state.data.assessment_current))} onClick={() => { void save(); }}>{busy ? 'Saving assessment…' : pending ? 'Retry exact assessment request' : 'Save assessment snapshot'}</button>
      <button className={button} disabled={locked || underwritingPending || busy || !!pending || state.isFetching} onClick={() => { void state.refetch(); void history.refetch(); }}>Refresh qualification</button></div>
    {feedback && <p role="status">{feedback}</p>}
    {!underwriting && <button className={button} disabled={locked || busy || !!pending || state.isFetching || state.isError || state.data?.assessment.classification !== 'qualified' || !state.data?.assessment.identity_link_current || !/^[a-f0-9-]{36}$/i.test(state.data?.assessment.target_lead_id ?? '')}
      onClick={() => { setUnderwriting({ lead: state.data!.assessment.target_lead_id!, hash: state.data!.evidence_hash }); setAnalysis(null); }}>Underwrite qualified intake</button>}
    {underwriting && <section aria-label="Intake underwriting" className="space-y-3">
      <p>Use sourced market and cost assumptions. Qualification is saved automatically with the scenario.</p>
      <ScenarioEditor path={`/api/acquisition/workspaces/${workspace}/leads/${underwriting.lead}/underwriting`}
        intake={{ path, id: intake, evidenceHash: underwriting.hash }} disabled={locked || busy || !!pending}
        onPending={setUnderwritingPending} onSaved={(value, current) => { setAnalysis(value); setQualificationCurrent(current === true); void state.refetch(); void history.refetch(); }} />
      {analysis && <><p>Saved scenario: {analysis.id}. Status: {analysis.acquisition_status}.</p>
        <p>{qualificationCurrent ? 'Intake qualification was current when saved. Proposal and approval recheck it.' : 'Intake qualification changed. This scenario is historical; review the intake before proceeding.'}</p>
        {analysis.acquisition_outputs && <ScenarioSummary output={analysis.acquisition_outputs} />}
        <p>Review saved scenarios for the linked property in “Underwrite a property and propose an offer”. No offer has been sent.</p></>}
      <button className={button} disabled={underwritingPending} onClick={() => { setUnderwriting(null); setAnalysis(null); }}>Close underwriting draft</button>
    </section>}
    <h5 className="font-medium">Saved screening history</h5>
    {history.isFetching ? <p>Loading screening history…</p> : history.isError ? <p role="alert">Screening history unavailable.</p> : <>
      {!history.data?.length && <p>No saved assessments on this page.</p>}
      {history.data?.map(row => <div key={row.id} className="border rounded p-2 text-sm"><p>Version {row.sequence} · {row.classification.replaceAll('_', ' ')} · {row.created_at}</p><p>{row.assessment.reason_codes.map(code => code.replaceAll('_', ' ').toLowerCase()).join(' · ')}</p></div>)}
      <div className="flex gap-2"><button className={button} disabled={underwritingPending || busy || !!pending || before === null} onClick={() => setBefore(null)}>Latest assessments</button>
        <button className={button} disabled={underwritingPending || busy || !!pending || history.data?.length !== 20} onClick={() => setBefore(history.data!.at(-1)!.sequence)}>Older assessments</button></div>
    </>}
  </section>;
}
