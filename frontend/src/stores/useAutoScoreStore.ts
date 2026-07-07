/**
 * useAutoScoreStore — database-backed Claude lead scoring progress.
 *
 * The first implementation kept a 17k-lead queue in browser memory and wrote
 * scores directly from the client. Mobile sleep, reloads, API errors, or tab
 * throttling could strand the run. This store now asks the backend to process
 * bounded batches from Supabase and uses database counts for progress.
 */

import { create } from 'zustand';

export interface ScorableLead {
  id: string;
  property_address: string;
  city?: string | null;
  state?: string | null;
  owner_first_name?: string | null;
  owner_last_name?: string | null;
  motivation_tag?: string | null;
}

interface ScoringProgress {
  total: number;
  scored: number;
  unscored: number;
  hot: number;
  warm: number;
  cold: number;
  complete: boolean;
}

const EMPTY_PROGRESS: ScoringProgress = {
  total: 0,
  scored: 0,
  unscored: 0,
  hot: 0,
  warm: 0,
  cold: 0,
  complete: false,
};

const SERVER_BATCH_SIZE = 25;

interface AutoScoreStore {
  scoring: boolean;
  total: number;
  done: number;
  failed: number;
  error: string | null;
  tierCounts: { HOT: number; WARM: number; COLD: number };
  cancelRequested: boolean;
  refreshStatus: () => Promise<ScoringProgress>;
  start: (leads?: ScorableLead[]) => Promise<void>;
  cancel: () => void;
  dismiss: () => void;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

function applyProgress(set: (partial: Partial<AutoScoreStore>) => void, progress: ScoringProgress) {
  set({
    total: progress.total,
    done: progress.scored,
    tierCounts: { HOT: progress.hot, WARM: progress.warm, COLD: progress.cold },
  });
}

export const useAutoScoreStore = create<AutoScoreStore>((set, get) => ({
  scoring: false,
  total: 0,
  done: 0,
  failed: 0,
  error: null,
  tierCounts: { HOT: 0, WARM: 0, COLD: 0 },
  cancelRequested: false,

  cancel: () => set({ cancelRequested: true, scoring: false }),
  dismiss: () => set({
    total: 0,
    done: 0,
    failed: 0,
    error: null,
    tierCounts: { HOT: 0, WARM: 0, COLD: 0 },
  }),

  refreshStatus: async () => {
    const progress = await fetchJson<ScoringProgress>('/api/ai/lead-scoring-status');
    applyProgress(set, progress);
    return progress;
  },

  start: async () => {
    if (get().scoring) return;

    set({ scoring: true, failed: 0, error: null, cancelRequested: false });

    try {
      let progress = await get().refreshStatus();
      if (progress.complete) {
        set({ scoring: false });
        return;
      }

      while (!progress.complete && !get().cancelRequested) {
        const result = await fetchJson<{
          processed: number;
          scored: number;
          progress: ScoringProgress;
        }>('/api/ai/score-unscored-leads', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ batch_size: SERVER_BATCH_SIZE }),
        });

        if (result.processed > 0 && result.scored < result.processed) {
          set((s) => ({ failed: s.failed + (result.processed - result.scored) }));
        }

        progress = result.progress || EMPTY_PROGRESS;
        applyProgress(set, progress);

        if (result.processed === 0) break;
      }

      set({ scoring: false });
    } catch (err) {
      set({
        scoring: false,
        error: err instanceof Error ? err.message : 'Claude scoring failed',
      });
    }
  },
}));
