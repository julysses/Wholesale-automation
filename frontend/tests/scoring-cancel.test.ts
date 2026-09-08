import { expect, it, vi } from 'vitest';
const fetcher = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch: fetcher }));
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';

it('does not repopulate cleared progress or start a batch after sign-out', async () => {
  let resolve!: (response: Response) => void;
  fetcher.mockReturnValue(new Promise<Response>(done => { resolve = done; }));
  const running = useAutoScoreStore.getState().start();
  useAutoScoreStore.getState().cancel();
  useAutoScoreStore.getState().dismiss();
  resolve(new Response(JSON.stringify({ total: 100, scored: 10, unscored: 90, complete: false })));
  await running;
  expect(useAutoScoreStore.getState().total).toBe(0);
  expect(useAutoScoreStore.getState().scoring).toBe(false);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
