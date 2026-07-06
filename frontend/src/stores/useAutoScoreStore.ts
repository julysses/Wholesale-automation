/**
 * useAutoScoreStore — drives the "Claude automatically scores newly imported
 * leads" background loop.
 *
 * Runs as a plain async function kicked off from a zustand action (not a
 * React effect), so — like useMasterListStore — it keeps running across SPA
 * navigation. It stops only if the user explicitly cancels or the tab closes.
 *
 * Scores in batches (BATCH_SIZE leads per Claude call) via
 * POST /api/ai/qualify-leads-batch, then writes results back to Supabase.
 * A batch's failure doesn't stop the loop — one bad chunk shouldn't strand
 * the rest of an import.
 */

import { create } from 'zustand';
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

const BATCH_SIZE = 20;

interface AutoScoreStore {
  scoring: boolean;
  total: number;
  done: number;
  failed: number;
  tierCounts: { HOT: number; WARM: number; COLD: number };
  cancelRequested: boolean;
  start: (leads: ScorableLead[]) => Promise<void>;
  cancel: () => void;
  dismiss: () => void;
}

// Shared mutable queue outside React state — start() appends to it, and only
// one processing loop ever runs at a time (a second start() call while scoring
// just adds its leads to the same queue instead of racing a parallel loop).
let pendingQueue: ScorableLead[] = [];

export const useAutoScoreStore = create<AutoScoreStore>((set, get) => ({
  scoring: false,
  total: 0,
  done: 0,
  failed: 0,
  tierCounts: { HOT: 0, WARM: 0, COLD: 0 },
  cancelRequested: false,

  cancel: () => { pendingQueue = []; set({ cancelRequested: true }); },
  dismiss: () => set({ total: 0, done: 0, failed: 0, tierCounts: { HOT: 0, WARM: 0, COLD: 0 } }),

  start: async (leads) => {
    if (leads.length === 0) return;
    pendingQueue.push(...leads);

    if (get().scoring) {
      // Already running — just grew the shared queue; the loop below will pick it up.
      set((s) => ({ total: s.total + leads.length }));
      return;
    }

    set({
      scoring: true, total: leads.length, done: 0, failed: 0,
      tierCounts: { HOT: 0, WARM: 0, COLD: 0 }, cancelRequested: false,
    });

    while (pendingQueue.length > 0) {
      if (get().cancelRequested) break;
      const batch = pendingQueue.splice(0, BATCH_SIZE);

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
          set((s) => ({ done: s.done + batch.length, failed: s.failed + batch.length }));
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
          // Upsert-by-id only touches the columns provided here — property_address,
          // city, etc. on the existing row are left untouched.
          await supabase.from('leads').upsert(rows, { onConflict: 'id' });
        }

        const scoredIds = new Set(results.map((r) => r.lead_id));
        const missed = batch.length - scoredIds.size;

        set((s) => {
          const counts = { ...s.tierCounts };
          for (const r of results) counts[r.tier] = (counts[r.tier] ?? 0) + 1;
          return { done: s.done + batch.length, failed: s.failed + missed, tierCounts: counts };
        });
      } catch {
        set((s) => ({ done: s.done + batch.length, failed: s.failed + batch.length }));
      }
    }

    set({ scoring: false });
  },
}));
