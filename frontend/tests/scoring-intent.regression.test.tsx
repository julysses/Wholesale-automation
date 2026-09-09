import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const fetcher = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch: fetcher }));
vi.mock('sonner', () => ({ toast: { info: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));

import { AutoScoreStatusBar } from '@/components/AutoScoreStatusBar';
import { useResumeAutoScore } from '@/hooks/useResumeAutoScore';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';

const backlog = { total: 100, scored: 10, unscored: 90, failed: 0, hot: 0, warm: 0, cold: 10, complete: false };
const complete = { ...backlog, scored: 100, unscored: 0, cold: 100, complete: true };
const response = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
const posts = () => fetcher.mock.calls.filter(([, init]) => init?.method === 'POST');

function ScoringShell() {
  useResumeAutoScore();
  return <AutoScoreStatusBar />;
}

beforeEach(() => {
  fetcher.mockReset();
  useAutoScoreStore.getState().cancel();
  useAutoScoreStore.setState({ scoring: false, total: 0, done: 0, failed: 0, error: null, cancelRequested: false, tierCounts: { HOT: 0, WARM: 0, COLD: 0 } });
});

it('only reads an unscored backlog on mount and starts work from the explicit action', async () => {
  fetcher.mockImplementation(async (_url: string, init?: RequestInit) => response(init?.method === 'POST'
    ? { processed: 90, scored: 90, failed: 0, progress: complete }
    : backlog));

  const view = render(<ScoringShell />);
  const start = await screen.findByRole('button', { name: 'Score 90 remaining leads' });
  expect(screen.getByText('Uses Claude to score the entire unscored backlog.')).toBeInTheDocument();
  view.rerender(<ScoringShell />);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher).toHaveBeenCalledWith('/api/ai/lead-scoring-status', undefined);
  expect(posts()).toHaveLength(0);

  fireEvent.click(start);
  await waitFor(() => expect(screen.getByText('Scoring complete')).toBeInTheDocument());
  expect(posts()).toEqual([['/api/ai/score-unscored-leads', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ batch_size: 25 }),
  }]]);
});

it('keeps cancellation stopped across rerenders and reloads until another explicit action', async () => {
  let finishBatch!: (result: Response) => void;
  fetcher.mockImplementation((_url: string, init?: RequestInit) => init?.method === 'POST'
    ? new Promise<Response>(resolve => { finishBatch = resolve; })
    : Promise.resolve(response(backlog)));

  const view = render(<ScoringShell />);
  fireEvent.click(await screen.findByRole('button', { name: 'Score 90 remaining leads' }));
  await waitFor(() => expect(posts()).toHaveLength(1));
  fireEvent.click(screen.getByTitle('Cancel scoring'));
  expect(screen.getByText('Scoring stopped')).toBeInTheDocument();
  view.rerender(<ScoringShell />);

  // A batch already accepted by the server may finish after cancellation.
  // Its late result must not restart the client loop or overwrite its state.
  await act(async () => finishBatch(response({ processed: 25, scored: 25, failed: 0, progress: { ...backlog, scored: 35, unscored: 65 } })));
  expect(posts()).toHaveLength(1);
  expect(useAutoScoreStore.getState().scoring).toBe(false);
  expect(useAutoScoreStore.getState().done).toBe(10);
  view.unmount();

  // A browser reload loses the in-memory cancellation flag. Mount still only
  // reads progress; it does not interpret unfinished work as permission to run.
  useAutoScoreStore.setState({ cancelRequested: false, total: 0, done: 0 });
  fetcher.mockImplementation(async (_url: string, init?: RequestInit) => response(init?.method === 'POST'
    ? { processed: 65, scored: 65, failed: 0, progress: complete }
    : { ...backlog, scored: 35, unscored: 65 }));
  render(<ScoringShell />);
  const resume = await screen.findByRole('button', { name: 'Score 65 remaining leads' });
  expect(posts()).toHaveLength(1);
  fireEvent.click(resume);
  await waitFor(() => expect(screen.getByText('Scoring complete')).toBeInTheDocument());
  expect(posts()).toHaveLength(2);
});

it('does not fall back to paid scoring when the mount status request fails', async () => {
  fetcher.mockRejectedValue(new Error('Status unavailable'));
  render(<ScoringShell />);
  await act(async () => {});
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(posts()).toHaveLength(0);
  expect(useAutoScoreStore.getState().scoring).toBe(false);
});
