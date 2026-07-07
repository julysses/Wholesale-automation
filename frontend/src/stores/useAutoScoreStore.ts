/**
 * useAutoScoreStore — drives the "Claude automatically scores newly imported
 * leads" background loop.
 *
 * Runs as a plain async function kicked off from a zustand action (not a
 * React effect), so — like useMasterListStore — it keeps running across SPA
 * navigation. Progress (queue, done/total, tier counts, failed leads) is
 * persisted to localStorage, so a page reload doesn't lose work: the status
 * bar offers a "Resume" action that picks up exactly where it left off.
 *
 * Large imports (thousands of leads) can take a long time to fully score.
 * Two real-world failure modes this is built to survive:
 *   1. Mobile browsers suspend network activity for backgrounded tabs — the
 *      loop detects this via the Page Visibility API, pauses cleanly with an
 *      honest status message, and resumes automatically when the tab is
 *      foregrounded again (instead of burning retries against a tab the OS
 *      has throttled).
 *   2. Transient network/server errors — each batch gets up to 3 attempts
 *      with backoff before its leads are set aside as "failed" (never
 *      silently dropped — the status bar exposes a one-click retry).
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { supabase } from '@/lib/supabase';

export interface ScorableLead {
  id: string;
  property_address: string;
  city?: string | null;
  state?: string | null;
  owner_first_name?: string | null;
  owner_last_name?: string | null;
  motivation_tag?: string | null;
}

interface BatchResult {
  lead_id: string;
  score_motivation: number;
  score_timeline: number;
  score_equity: number;
  score_condition: number;
  score_flexibility: number;
  tier: 'HOT' | 'WARM' | 'COLD';
  qualification_summary: string;
}

// Kept small deliberately: the Vercel Python function runs under the older
// `builds` config, which cannot set maxDuration and defaults to a short
// per-request timeout. A 20-lead batch occasionally ran long enough for
// Claude's generation to exceed that window, which Vercel kills mid-flight —
// the client sees a bare network failure ("Load failed" in Safari), not a
// clean HTTP error. Smaller batches finish comfortably inside the limit.
const BATCH_SIZE = 10;
const MAX_ATTEMPTS = 3;
const RETRY_DELAYS_MS = [1500, 3500, 7000];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function isTabHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

function waitUntilVisible(): Promise<void> {
  return new Promise((resolve) => {
    if (!isTabHidden()) { resolve(); return; }
    const handler = () => {
      if (!isTabHidden()) {
        document.removeEventListener('visibilitychange', handler);
        resolve();
      }
    };
    document.addEventListener('visibilitychange', handler);
  });
}

interface AutoScoreStore {
  scoring: boolean;
  paused: boolean;
  pausedReason: string | null;
  lastError: string | null;
  total: number;
  done: number;
  tierCounts: { HOT: number; WARM: number; COLD: number };
  queue: ScorableLead[];        // remaining, not yet scored — persisted
  failedLeads: ScorableLead[];  // exhausted retries — persisted, retryable
  cancelRequested: boolean;

  start: (leads: ScorableLead[]) => void;
  resume: () => void;
  retryFailed: () => void;
  cancel: () => void;
  dismiss: () => void;
}

// Guards against a duplicate concurrent loop (e.g. resume() called twice, or
// a rehydrated store + a fresh start() racing each other).
let loopRunning = false;

export const useAutoScoreStore = create<AutoScoreStore>()(
  persist(
    (set, get) => {
      async function runLoop() {
        if (loopRunning) return;
        loopRunning = true;
        set({ scoring: true, cancelRequested: false, paused: false, pausedReason: null, lastError: null });

        while (get().queue.length > 0) {
          if (get().cancelRequested) break;

          if (isTabHidden()) {
            set({ paused: true, pausedReason: 'Tab is in the background — scoring will resume automatically when you return.' });
            await waitUntilVisible();
            if (get().cancelRequested) break;
            set({ paused: false, pausedReason: null });
          }

          const batch = get().queue.slice(0, BATCH_SIZE);
          let succeeded = false;
          let lastErrorMsg = '';

          for (let attempt = 0; attempt < MAX_ATTEMPTS && !succeeded; attempt++) {
            if (get().cancelRequested) break;

            if (attempt > 0) {
              if (isTabHidden()) {
                set({ paused: true, pausedReason: 'Tab is in the background — scoring will resume automatically when you return.' });
                await waitUntilVisible();
                set({ paused: false, pausedReason: null });
              } else {
                await sleep(RETRY_DELAYS_MS[Math.min(attempt - 1, RETRY_DELAYS_MS.length - 1)]);
              }
            }

            try {
              const res = await fetch('/api/ai/qualify-leads-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  leads: batch.map((l) => ({
                    lead_id: l.id,
                    property_address: l.property_address,
                    city: l.city || undefined,
                    state: l.state || undefined,
                    owner_first_name: l.owner_first_name || undefined,
                    owner_last_name: l.owner_last_name || undefined,
                    motivation_tag: l.motivation_tag || undefined,
                  })),
                }),
              });

              if (!res.ok) {
                const body = await res.json().catch(() => ({ detail: res.statusText }));
                lastErrorMsg = `Server error ${res.status}: ${body.detail ?? res.statusText}`;
                continue;
              }

              const { results } = (await res.json()) as { results: BatchResult[] };
              const rows = results.map((r) => ({
                id: r.lead_id,
                score_motivation: r.score_motivation,
                score_timeline: r.score_timeline,
                score_equity: r.score_equity,
                score_condition: r.score_condition,
                score_flexibility: r.score_flexibility,
                ai_qualification_summary: r.qualification_summary,
                status: r.tier === 'HOT' ? 'qualified_hot' : r.tier === 'WARM' ? 'qualified_warm' : 'qualified_cold',
              }));

              if (rows.length > 0) {
                const { error } = await supabase.from('leads').upsert(rows, { onConflict: 'id' });
                if (error) {
                  // The save itself failed — do NOT count this batch as scored.
                  lastErrorMsg = `Save failed: ${error.message}`;
                  continue;
                }
              }

              const scoredIds = new Set(results.map((r) => r.lead_id));
              const notScored = batch.filter((l) => !scoredIds.has(l.id));
              const counts = { ...get().tierCounts };
              for (const r of results) counts[r.tier] = (counts[r.tier] ?? 0) + 1;

              set((s) => ({
                queue: s.queue.slice(batch.length),
                done: s.done + batch.length,
                tierCounts: counts,
                failedLeads: notScored.length > 0 ? [...s.failedLeads, ...notScored] : s.failedLeads,
                lastError: null,
              }));
              succeeded = true;
            } catch (e) {
              // Network-level failure (e.g. Safari "Load failed" from a
              // backgrounded/suspended tab, or a dropped connection).
              lastErrorMsg = e instanceof Error ? e.message : 'Network error';
            }
          }

          if (!succeeded && !get().cancelRequested) {
            set((s) => ({
              queue: s.queue.slice(batch.length),
              done: s.done + batch.length,
              failedLeads: [...s.failedLeads, ...batch],
              lastError: lastErrorMsg || 'Load failed',
            }));
          }
        }

        loopRunning = false;
        set({ scoring: false, paused: false, pausedReason: null });
      }

      return {
        scoring: false,
        paused: false,
        pausedReason: null,
        lastError: null,
        total: 0,
        done: 0,
        tierCounts: { HOT: 0, WARM: 0, COLD: 0 },
        queue: [],
        failedLeads: [],
        cancelRequested: false,

        start: (leads) => {
          if (leads.length === 0) return;
          set((s) => ({ queue: [...s.queue, ...leads], total: s.total + leads.length }));
          void runLoop();
        },

        resume: () => {
          if (get().queue.length === 0 || get().scoring) return;
          void runLoop();
        },

        retryFailed: () => {
          const failed = get().failedLeads;
          if (failed.length === 0) return;
          set((s) => ({ queue: [...s.queue, ...failed], failedLeads: [] }));
          void runLoop();
        },

        cancel: () => set({ cancelRequested: true }),

        dismiss: () => set({
          total: 0, done: 0, tierCounts: { HOT: 0, WARM: 0, COLD: 0 },
          queue: [], failedLeads: [], lastError: null,
        }),
      };
    },
    {
      name: 'autoscore-store',
      // Only persist enough to resume across a reload — never persist the
      // transient run flags (a fresh page load can't have a loop mid-flight).
      partialize: (state) => ({
        total: state.total,
        done: state.done,
        tierCounts: state.tierCounts,
        queue: state.queue,
        failedLeads: state.failedLeads,
      }),
    },
  ),
);
