/**
 * useResumeAutoScore
 *
 * Leads can end up sitting unscored — imported before Claude auto-scoring
 * existed, or stranded because the browser tab closed mid-run (the scoring
 * queue is in-memory only). This hook runs once per app load: it finds any
 * lead still missing score_motivation and feeds it into useAutoScoreStore,
 * so scoring resumes automatically without requiring a fresh re-upload.
 */

import { useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { useAutoScoreStore, type ScorableLead } from '@/stores/useAutoScoreStore';

const PAGE_SIZE = 500;
// Safety cap so a pathological backlog can't queue an unbounded number of
// Claude calls from a single page load — resume picks up the rest next load.
const MAX_LEADS_PER_RESUME = 20000;

const SELECT_COLUMNS = 'id, property_address, city, state, owner_first_name, owner_last_name, motivation_tag';

// Module-level guard: only ever kick off one resume per browser session,
// even if Layout remounts.
let hasResumed = false;

export function useResumeAutoScore() {
  useEffect(() => {
    if (hasResumed) return;
    hasResumed = true;

    (async () => {
      if (useAutoScoreStore.getState().scoring) return;

      const unscored: ScorableLead[] = [];
      let from = 0;

      while (unscored.length < MAX_LEADS_PER_RESUME) {
        const { data, error } = await supabase
          .from('leads')
          .select(SELECT_COLUMNS)
          .is('score_motivation', null)
          .range(from, from + PAGE_SIZE - 1);

        if (error || !data || data.length === 0) break;
        unscored.push(...(data as ScorableLead[]));
        if (data.length < PAGE_SIZE) break;
        from += PAGE_SIZE;
      }

      if (unscored.length > 0) {
        useAutoScoreStore.getState().start(unscored);
      }
    })();
  }, []);
}
