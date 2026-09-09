/**
 * useResumeAutoScore
 *
 * On app load, read durable scoring progress without starting paid AI work.
 * Imports and the explicit scoring action own the decision to start a run.
 */

import { useEffect } from 'react';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';

export function useResumeAutoScore() {
  useEffect(() => {
    const store = useAutoScoreStore.getState();
    if (!store.scoring) {
      void store.refreshStatus().catch(() => {
        // Status retrieval alone must never fall back to starting AI work.
      });
    }
    return () => { useAutoScoreStore.getState().cancel(); };
  }, []);
}
