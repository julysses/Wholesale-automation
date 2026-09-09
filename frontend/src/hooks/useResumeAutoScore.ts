/**
 * useResumeAutoScore
 *
 * On app load, resume any unscored lead backlog through the backend scorer.
 * Progress is based on Supabase counts, not a browser-owned lead queue.
 */

import { useEffect } from 'react';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';

export function useResumeAutoScore() {
  useEffect(() => {
    let active = true;

    (async () => {
      const store = useAutoScoreStore.getState();
      if (store.scoring) return;

      try {
        const status = await store.refreshStatus();
        if (active && !status.complete && status.unscored > 0) {
          store.start();
        }
      } catch {
        // The visible status bar will surface errors once the user retries.
      }
    })();
    return () => { active = false; useAutoScoreStore.getState().cancel(); };
  }, []);
}
