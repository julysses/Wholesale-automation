/**
 * AutoScoreStatusBar
 *
 * Floating progress pill visible from any page while Claude is auto-scoring
 * freshly imported leads (frontend/src/stores/useAutoScoreStore.ts). Mounted
 * once in the app shell so the loop's progress stays visible no matter which
 * screen the user navigates to.
 *
 * Handles three states beyond plain "in progress":
 *   - paused: the tab is backgrounded; scoring resumes automatically when
 *     the tab is foregrounded again (no data lost, no retries wasted).
 *   - failed leads: a batch exhausted its retries — never silently dropped,
 *     shown with a one-click "Retry" action.
 *   - resumable: the page was reloaded mid-run — persisted progress lets the
 *     user pick up exactly where they left off.
 */

import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { Sparkles, X, Flame, RefreshCw, AlertTriangle } from 'lucide-react';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';

export function AutoScoreStatusBar() {
  const {
    scoring, paused, pausedReason, lastError, total, done, failedLeads, tierCounts, queue,
    cancel, dismiss, resume, retryFailed,
  } = useAutoScoreStore();
  const wasScoring = useRef(false);

  // Fire a one-time summary toast the moment an active run finishes
  useEffect(() => {
    if (wasScoring.current && !scoring && total > 0) {
      const parts = [
        tierCounts.HOT > 0 && `${tierCounts.HOT} HOT`,
        tierCounts.WARM > 0 && `${tierCounts.WARM} WARM`,
        tierCounts.COLD > 0 && `${tierCounts.COLD} COLD`,
      ].filter(Boolean).join(' · ');
      if (failedLeads.length > 0) {
        toast.warning(`Claude scored ${(done - failedLeads.length).toLocaleString()}/${total.toLocaleString()} leads (${failedLeads.length} failed)${parts ? ` — ${parts}` : ''}`);
      } else {
        toast.success(`Claude scored ${done.toLocaleString()} leads${parts ? ` — ${parts}` : ''}`);
      }
    }
    wasScoring.current = scoring;
  }, [scoring, total, done, failedLeads.length, tierCounts]);

  // Nothing to show: no run in progress, nothing scored yet, nothing to resume/retry
  const hasResumableWork = !scoring && queue.length > 0;
  if (!scoring && total === 0 && failedLeads.length === 0 && !hasResumableWork) return null;

  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="fixed bottom-4 right-4 z-40 bg-white rounded-xl shadow-lg border border-gray-200 p-3 w-80">
      <div className="flex items-center gap-2 mb-2">
        {paused ? (
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
        ) : scoring ? (
          <Sparkles className="h-4 w-4 text-[#E8720C] animate-pulse shrink-0" />
        ) : (
          <Flame className="h-4 w-4 text-green-600 shrink-0" />
        )}
        <p className="text-xs font-semibold text-gray-800 flex-1">
          {paused ? 'Claude scoring paused'
            : scoring ? 'Claude is scoring leads…'
            : hasResumableWork ? 'Scoring interrupted'
            : 'Scoring complete'}
        </p>
        <div className="flex items-center gap-1 shrink-0">
          {!scoring && (failedLeads.length > 0 || hasResumableWork) && (
            <button
              onClick={hasResumableWork ? resume : retryFailed}
              className="p-0.5 rounded hover:bg-gray-100 text-gray-400 hover:text-[#1B3A5C]"
              title={hasResumableWork ? 'Resume scoring' : 'Retry failed leads'}
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={scoring ? cancel : dismiss}
            className="p-0.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
            title={scoring ? 'Cancel scoring' : 'Dismiss'}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${paused ? 'bg-amber-400' : 'bg-[#E8720C]'}`}
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

      {paused && pausedReason && (
        <p className="text-[11px] text-amber-600 mt-1.5 leading-snug">{pausedReason}</p>
      )}
      {!paused && failedLeads.length > 0 && (
        <p className="text-[11px] text-red-500 mt-1.5 leading-snug">
          {failedLeads.length.toLocaleString()} lead{failedLeads.length === 1 ? '' : 's'} failed to score
          {lastError ? `: ${lastError}` : ''} — tap retry above.
        </p>
      )}
      {hasResumableWork && !paused && failedLeads.length === 0 && (
        <p className="text-[11px] text-gray-400 mt-1.5 leading-snug">
          Page was reloaded mid-run — tap resume to keep going.
        </p>
      )}
    </div>
  );
}
