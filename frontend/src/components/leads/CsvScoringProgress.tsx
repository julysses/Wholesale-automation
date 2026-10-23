import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';

type Progress = {
  status: 'ok'; request_id: string; scoring_eligible: number;
  scoring_state: 'pending' | 'submitting' | 'completed' | 'review';
  scored: number; scoring_held: number; scoring_remaining: number; scoring_in_flight: number;
};
async function progressRequest(id: string, method: 'GET' | 'POST'): Promise<Progress> {
  const response = await apiFetch(`/api/ai/imports/${id}/scoring`, { method });
  const result = await response.json();
  const counts = ['scored', 'scoring_held', 'scoring_remaining', 'scoring_in_flight'] as const;
  if (result.scoring_state === 'unconfirmed') throw new Error('Scoring outcome is unconfirmed. Refresh progress before continuing.');
  if (!response.ok || result.status !== 'ok' || result.request_id !== id
    || !Number.isInteger(result.scoring_eligible) || result.scoring_eligible < 0
    || counts.some(key => !Number.isInteger(result[key]) || result[key] < 0)
    || counts.reduce((sum, key) => sum + result[key], 0) !== result.scoring_eligible
    || !['pending', 'submitting', 'completed', 'review'].includes(result.scoring_state)
    || (result.scoring_state === 'pending' && (!result.scoring_remaining || result.scoring_in_flight))
    || (result.scoring_state === 'submitting' && !(result.scoring_in_flight >= 1 && result.scoring_in_flight <= 25))
    || (result.scoring_state === 'completed' && (result.scoring_held || result.scoring_remaining || result.scoring_in_flight))
    || (result.scoring_state === 'review' && result.scoring_in_flight)) {
    throw new Error('Scoring progress could not be confirmed for this import.');
  }
  return result as Progress;
}

/** No interval, automatic continuation or mutation retry. GET never calls a model. */
export function CsvScoringProgress({ importId }: { importId: string }) {
  const valid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(importId);
  const id = importId.toLowerCase();
  const client = useQueryClient();
  const key = ['csv-scoring-progress', id];
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [pauseRequested, setPauseRequested] = useState(false);
  const stopAfterBatch = useRef(false);
  const allActive = useRef(false);
  useEffect(() => () => { stopAfterBatch.current = true; }, []);
  const query = useQuery({ queryKey: key, queryFn: () => progressRequest(id, 'GET'), enabled: valid, retry: false,
    refetchOnWindowFocus: false, refetchOnReconnect: false });
  const continuation = useMutation({ mutationFn: () => progressRequest(id, 'POST'), retry: false,
    onSuccess: async next => {
      client.setQueryData(key, next); setNeedsRefresh(false);
      await Promise.all([client.invalidateQueries({ queryKey: ['leads'] }), client.invalidateQueries({ queryKey: ['kpi'] })]);
    }, onError: () => setNeedsRefresh(true) });
  const scoreRemaining = async () => {
    if (allActive.current) return;
    allActive.current = true; stopAfterBatch.current = false;
    setRunningAll(true); setPauseRequested(false);
    try {
      while (!stopAfterBatch.current) {
        const next = await continuation.mutateAsync();
        if (next.scoring_state !== 'pending') break;
      }
    } catch {
      // The mutation surfaces uncertainty. Never retry or advance automatically.
    } finally {
      allActive.current = false; setRunningAll(false);
    }
  };
  if (!valid) return <div role="alert">This CSV import link is invalid.</div>;
  const data = query.data;
  const canContinue = data?.scoring_state === 'pending' && data.scoring_remaining > 0
    && !needsRefresh && !query.isError && !query.isFetching && !continuation.isPending && !runningAll;
  return <section aria-label="CSV AI scoring progress" className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
    <h2 className="font-semibold">CSV AI scoring</h2>
    <p className="text-sm">Each continuation scores up to 25 unprocessed leads. Completed batches stay saved.
      Uncertain batches require review and cannot be repeated. Score all processes remaining batches until complete or paused.</p>
    {!data && query.isPending && <p role="status">Loading saved progress…</p>}
    {query.isError && <p role="alert">Saved progress is unavailable. {query.error.message}</p>}
    {data && <>
      {(query.isError || needsRefresh) && <p>Showing last confirmed progress.</p>}
      <dl className="flex flex-wrap gap-5 text-sm">
        <div><dt>Scored</dt><dd>{data.scored}</dd></div>
        <div><dt>Held for review</dt><dd>{data.scoring_held}</dd></div>
        <div><dt>Remaining</dt><dd>{data.scoring_remaining}</dd></div>
        <div><dt>In progress</dt><dd>{data.scoring_in_flight}</dd></div>
      </dl>
      {data.scoring_state === 'completed' && <p role="status">AI scoring complete.</p>}
      {data.scoring_state === 'review' && <p role="status">This import needs review. No further model request will run.</p>}
      {data.scoring_state === 'submitting' && <p role="status">A batch was submitted. Refresh to check its outcome; it will not be dispatched again.</p>}
    </>}
    {continuation.isError && <p role="alert">{continuation.error.message} Refresh progress before continuing.</p>}
    <div className="flex gap-2">
      <Button variant="outline" disabled={query.isFetching || continuation.isPending || runningAll} onClick={() => {
        void query.refetch().then(result => { if (result.isSuccess) { setNeedsRefresh(false); continuation.reset(); } });
      }}>Refresh scoring progress</Button>
      {data?.scoring_state === 'pending' && <>
        <Button disabled={!canContinue} onClick={() => { void scoreRemaining(); }}>Score all remaining (paid)</Button>
        <Button variant="outline" disabled={!canContinue} loading={continuation.isPending}
          onClick={() => continuation.mutate()}>Continue AI scoring (paid)</Button>
      </>}
      {runningAll && <Button variant="outline" disabled={pauseRequested} onClick={() => {
        stopAfterBatch.current = true; setPauseRequested(true);
      }}>{pauseRequested ? 'Pausing after current batch…' : 'Pause after current batch'}</Button>}
    </div>
  </section>;
}
