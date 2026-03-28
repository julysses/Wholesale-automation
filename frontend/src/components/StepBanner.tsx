/**
 * StepBanner
 *
 * Compact contextual banner that appears at the top of every page inside
 * the Layout. It shows:
 *   - Which step the current page belongs to (if any)
 *   - A "Next step →" nudge pointing to the next action
 *
 * Disappears on pages that aren't part of the workflow, and disappears
 * entirely once all 11 steps are complete.
 */

import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle, ChevronRight } from 'lucide-react';
import { useWorkflowStep, WORKFLOW_STEPS } from '@/hooks/useWorkflowStep';

/** Which step number(s) each route belongs to */
const ROUTE_STEP_MAP: Record<string, number[]> = {
  '/setup':        [1],
  '/':             [2, 4, 6],
  '/leads':        [3, 5],
  '/acquisitions': [7, 8, 9, 10],
  '/pipeline':     [11],
  '/land':         [3],        // land imports also count as lead import
  '/analyzer':     [8],
  '/buyers':       [],
  '/ai-agents':    [],
  '/tasks':        [10],
  '/reports':      [],
  '/manual':       [],
};

function getStepsForPath(pathname: string): number[] {
  // Exact match first
  if (ROUTE_STEP_MAP[pathname]) return ROUTE_STEP_MAP[pathname];
  // Prefix match for nested routes
  for (const [route, steps] of Object.entries(ROUTE_STEP_MAP)) {
    if (route !== '/' && pathname.startsWith(route)) return steps;
  }
  return [];
}

export function StepBanner() {
  const location = useLocation();
  const { currentStep, completedSteps, nextStep, activeStep, isLoading } = useWorkflowStep();

  if (isLoading) return null;

  // All done — no banner needed
  if (completedSteps.size >= 11) return null;

  const stepsForPage = getStepsForPath(location.pathname);

  // Is the current active step on this page?
  const pageHasActiveStep = stepsForPage.includes(currentStep);

  // Is a completed step on this page?
  const pageHasDoneStep = stepsForPage.some(s => completedSteps.has(s));

  // Page is entirely unrelated to workflow
  if (stepsForPage.length === 0 && !pageHasActiveStep) return null;

  // ── Banner for: this page IS the current step ─────────────────────────────
  if (pageHasActiveStep) {
    return (
      <div className="bg-[#1B3A5C] text-white px-4 py-2.5 flex items-center gap-3 text-sm">
        {/* Step badge */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="h-5 w-5 rounded-full bg-[#E8720C] flex items-center justify-center text-[10px] font-black">
            {currentStep}
          </div>
          <span className="font-bold">Step {currentStep} of 11:</span>
          <span className="font-medium text-white/90">{activeStep.title}</span>
        </div>

        <ChevronRight className="h-4 w-4 text-white/40 shrink-0" />

        <span className="text-white/70 text-xs hidden sm:block truncate">
          {activeStep.description}
        </span>

        {/* Next step nudge */}
        {nextStep && (
          <div className="ml-auto flex items-center gap-2 shrink-0">
            <span className="text-white/50 text-xs hidden md:block">After this →</span>
            <Link
              to={nextStep.path}
              className="flex items-center gap-1 text-xs font-bold text-[#E8720C] hover:text-white bg-white/10 hover:bg-[#E8720C] px-3 py-1 rounded-full transition-colors"
            >
              Step {nextStep.number}: {nextStep.title}
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        )}
      </div>
    );
  }

  // ── Banner for: page has a DONE step, nudge to active step ───────────────
  if (pageHasDoneStep) {
    return (
      <div className="bg-green-600 text-white px-4 py-2 flex items-center gap-3 text-sm">
        <CheckCircle className="h-4 w-4 text-green-200 shrink-0" />
        <span className="text-green-100 text-xs">
          You've completed this step.
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-green-200 text-xs hidden sm:block">Your current step:</span>
          <Link
            to={activeStep.path}
            className="flex items-center gap-1 text-xs font-bold text-white bg-green-500 hover:bg-green-700 px-3 py-1 rounded-full transition-colors"
          >
            Step {currentStep}: {activeStep.title}
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      </div>
    );
  }

  // ── Banner for: page is workflow-adjacent but not the current step ────────
  return (
    <div className="bg-gray-700/80 text-white px-4 py-2 flex items-center gap-3 text-sm">
      <span className="text-white/60 text-xs">
        Your next action is on a different page.
      </span>
      <Link
        to={activeStep.path}
        className="ml-auto flex items-center gap-1 text-xs font-bold text-white bg-[#E8720C] hover:bg-[#d4660b] px-3 py-1 rounded-full transition-colors shrink-0"
      >
        Go to Step {currentStep}: {activeStep.title}
        <ArrowRight className="h-3 w-3" />
      </Link>
    </div>
  );
}
