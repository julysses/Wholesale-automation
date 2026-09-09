import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { queryAll } from '@/lib/queryAll';
import { latestByLead } from '@/lib/qualificationHistory';
import { formatDate, daysUntil } from '@/lib/utils';

const mocks = vi.hoisted(() => ({ from: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('sonner', () => ({ toast: mocks }));
import { useLeads } from '@/hooks/useLeads';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';
import { AutoScoreStatusBar } from '@/components/AutoScoreStatusBar';

beforeEach(() => {
  vi.clearAllMocks();
  useAutoScoreStore.setState({ scoring: false, total: 0, done: 0, failed: 0, error: null, cancelRequested: false, tierCounts: { HOT: 0, WARM: 0, COLD: 0 } });
});

it('reads beyond a server row cap without skipping or duplicating records', async () => {
  const all = Array.from({ length: 1201 }, (_, id) => ({ id }));
  const page = vi.fn(async (from: number, to: number) => ({ data: all.slice(from, Math.min(to + 1, from + 200)), error: null }));
  expect(await queryAll(page)).toEqual(all);
  expect(page.mock.calls[1][0]).toBe(200);
});

it('rejects a later query failure instead of returning a partial total', async () => {
  await expect(queryAll(async from => from === 0 ? { data: [{ id: 1 }], error: null } : { data: null, error: { message: 'connection lost' } })).rejects.toThrow('connection lost');
});

it('does not revive an old HOT qualification after a seller becomes COLD', () => {
  const history = [{ lead_id: 'a', classification: 'COLD' }, { lead_id: 'b', classification: 'HOT' }, { lead_id: 'a', classification: 'HOT' }];
  expect(latestByLead(history).filter(row => row.classification === 'HOT')).toEqual([history[1]]);
});

it('filters the server query before calculating page counts', async () => {
  const query = { select: vi.fn(), order: vi.fn(), range: vi.fn(), eq: vi.fn(), then: (resolve: (value: unknown) => void) => resolve({ data: [{ id: 'match' }], count: 51, error: null }) };
  for (const method of [query.select, query.order, query.range, query.eq]) method.mockReturnValue(query);
  mocks.from.mockReturnValue(query);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useLeads({ tier: 'A', motivation: 'vacant', page: 2 }), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(query.eq).toHaveBeenCalledWith('priority_tier', 'A');
  expect(query.eq).toHaveBeenCalledWith('motivation_tag', 'vacant');
  expect(query.range).toHaveBeenCalledWith(50, 99);
  expect(result.current.data?.count).toBe(51);
});

it('keeps date-only closings on the intended local calendar day', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 8, 8, 23, 0));
  expect(formatDate('2026-09-09')).toBe('Sep 9, 2026');
  expect(daysUntil('2026-09-09')).toBe(1);
  vi.useRealTimers();
});

it('reports scoring cancellation without a completion success', () => {
  useAutoScoreStore.setState({ scoring: true, total: 10, done: 2 });
  render(<AutoScoreStatusBar />);
  act(() => useAutoScoreStore.getState().cancel());
  expect(screen.getByText('Scoring stopped')).toBeInTheDocument();
  expect(mocks.success).not.toHaveBeenCalled();
  expect(mocks.info).toHaveBeenCalledWith('Scoring stopped at 2/10 leads');
});

it('reports a scoring error without a success toast', () => {
  useAutoScoreStore.setState({ scoring: true, total: 10, done: 2 });
  render(<AutoScoreStatusBar />);
  act(() => useAutoScoreStore.setState({ scoring: false, error: 'Provider unavailable' }));
  expect(screen.getByText('Claude scoring paused')).toBeInTheDocument();
  expect(mocks.success).not.toHaveBeenCalled();
  expect(mocks.error).toHaveBeenCalledWith('Scoring paused: Provider unavailable');
});
