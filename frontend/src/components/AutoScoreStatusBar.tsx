/**
 * AutoScoreStatusBar
 *
 * Floating progress pill visible from any page while Claude is auto-scoring
 * freshly imported leads (frontend/src/stores/useAutoScoreStore.ts). Mounted
 * once in the app shell so the loop's progress stays visible no matter which
 * screen the user navigates to.
 */

import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { Sparkles, X, Flame, AlertTriangle, RotateCw } from 'lucide-react';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';

export function AutoScoreStatusBar() {
  const { scoring, total, done, failed, error, tierCounts, start, cancel, dismiss } = useAutoScoreStore();
  const wasScoring = useRef(false);

  // Fire a one-time summary toast the moment scoring finishes
  useEffect(() => {
    if (wasScoring.current && !scoring && total > 0) {
      const parts = [
        tierCounts.HOT > 0 && `${tierCounts.HOT} HOT`,
        tierCounts.WARM > 0 && `${tierCounts.WARM} WARM`,
        tierCounts.COLD > 0 && `${tierCounts.COLD} COLD`,
      ].filter(Boolean).join(' · ');
      if (failed > 0) {
        toast.warning(`Claude scored ${done - failed}/${total} leads (${failed} skipped)${parts ? ` — ${parts}` : ''}`);
      } else {
        toast.success(`Claude scored ${done.toLocaleString()} leads${parts ? ` — ${parts}` : ''}`);
      }
    }
    wasScoring.current = scoring;
  }, [scoring, total, done, failed, tierCounts]);

  if (!scoring && total === 0 && !error) return null;

  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const isPaused = !!error && !scoring;

  return (
    <div className="fixed bottom-4 right-4 z-40 bg-white rounded-xl shadow-lg border border-gray-200 p-3 w-72">
      <div className="flex items-center gap-2 mb-2">
        {isPaused ? (
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
        ) : scoring ? (
          <Sparkles className="h-4 w-4 text-[#E8720C] animate-pulse shrink-0" />
        ) : (
          <Flame className="h-4 w-4 text-green-600 shrink-0" />
        )}
        <p className="text-xs font-semibold text-gray-800 flex-1">
          {isPaused ? 'Claude scoring paused' : scoring ? 'Claude is scoring leads…' : 'Scoring complete'}
        </p>
        {isPaused && (
          <button
            onClick={() => start()}
            className="p-0.5 rounded hover:bg-gray-100 text-gray-500 hover:text-[#1B3A5C] shrink-0"
            title="Retry scoring"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          onClick={scoring ? cancel : dismiss}
          className="p-0.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 shrink-0"
          title={scoring ? 'Cancel scoring' : 'Dismiss'}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-[#E8720C] rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center justify-between mt-1.5 text-[11px] text-gray-500">
        <span>{done.toLocaleString()} / {total.toLocaleString()}</span>
        <span>
          {tierCounts.HOT > 0 && <span className="text-red-600 font-semibold mr-1.5">{tierCounts.HOT} HOT</span>}
          {tierCounts.WARM > 0 && <span className="text-amber-600 font-semibold">{tierCounts.WARM} WARM</span>}
        </span>
      </div>
      {isPaused && (
        <p className="mt-1.5 text-[11px] text-amber-700 line-clamp-2">{error}</p>
      )}
    </div>
  );
}
