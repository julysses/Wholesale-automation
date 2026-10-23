/**
 * WorkflowGuide
 *
 * Full 11-step getting-started tracker shown on the Dashboard.
 * Each step auto-detects completion from real Supabase data.
 * Completed steps are checked off. The current active step is highlighted
 * with a prominent CTA. Future steps are shown as locked/dimmed.
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, Circle, Lock, ChevronDown, ChevronUp, ArrowRight, BookOpen, Zap } from 'lucide-react';
import { useWorkflowStep, WORKFLOW_STEPS, getManualComplete, toggleManualComplete } from '@/hooks/useWorkflowStep';
import { PropStreamPullGuide } from '@/components/dashboard/PropStreamPullGuide';

const STEP_DETAILS: Record<number, { what: string; system: string }> = {
  1:  { what: 'Review connection status with your administrator. Database changes require a reviewed migration plan for the selected environment; do not rerun historical migrations from this guide.',
        system: 'The setup screen reports configuration status. A connected account does not confirm database readiness, delivery, or launch approval.' },
  2:  { what: 'Choose a planning strategy and review its assumptions against your budget and verified results.',
        system: 'Updates planning targets. Targets and conversion assumptions are not measured performance or permission to contact sellers.' },
  3:  { what: 'Import a reviewed file and confirm the column mapping, source, property identity, and duplicates.',
        system: 'Imported records remain subject to evidence and contact-permission checks. Importing or scoring a record does not establish consent.' },
  4:  { what: 'Review priority records and supporting evidence before deciding which leads need follow-up.',
        system: 'Displays tier and stack information to support review. A score is not outreach authorization.' },
  5:  { what: 'After calling launch approval, select individual eligible leads and review the controlled call batch. Confirm saved consent and the approved calling configuration.',
        system: 'Calling requires provider configuration, live enablement, and contact checks. Verify each attempt and provider receipt; selection alone does not place a call.' },
  6:  { what: 'Review recorded call results, provider receipts, assigned tasks, and owner alerts.',
        system: 'Displays recorded activity. Confirm delivery and task ownership separately before relying on a follow-up.' },
  7:  { what: 'Open Acquisitions, review the qualification evidence, and assign a permitted personal follow-up.',
        system: 'Shows recorded lead status. Verify whether any message or follow-up task was actually created; a HOT label does not prove delivery.' },
  8:  { what: 'Review property evidence, comparable sales, repair assumptions, and valuation limitations. Establish any offer price yourself.',
        system: 'Analysis supports review and does not approve an offer. Save exact human-entered terms in AI Agents → Human Offer Review.' },
  9:  { what: 'Review discussion notes and prepare your negotiation approach. Any changed price or terms require a new saved revision and human review.',
        system: 'Draft guidance is not an approved offer. Human Offer Review records exact terms and a saved property/message preview; it does not send them.' },
  10: { what: 'Record the agreed appointment date, time, and type, then confirm ownership of the follow-up.',
        system: 'Verify the saved appointment and any separate reminder delivery. Scheduling alone does not prove an SMS was sent.' },
  11: { what: 'Complete the required agreement and title review, record the contract status, and verify the buyer and closing outcome.',
        system: 'Pipeline and reporting reflect recorded data. Verify documents and actual closing proceeds before recording a closed deal or earned fee.' },
};

export function WorkflowGuide() {
  const { currentStep, completedSteps, pct, isLoading, error } = useWorkflowStep();
  const [expanded, setExpanded] = useState(true);
  const [openDetail, setOpenDetail] = useState<number | null>(currentStep);

  // Track manually-ticked steps so the checkbox reflects state immediately
  const [manualComplete, setManualComplete] = useState<Set<number>>(() => getManualComplete());
  useEffect(() => {
    const handler = () => setManualComplete(getManualComplete());
    window.addEventListener('workflowManualChange', handler);
    return () => window.removeEventListener('workflowManualChange', handler);
  }, []);

  if (isLoading) return null;

  // Hide guide once all 11 steps done and user has contracts
  const allDone = completedSteps.size === 11;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <p className="px-5 pt-3 text-xs text-gray-500">Internal QA is excluded. Manual checkmarks are operator acknowledgements; this guide does not certify launch readiness.</p>
      {error && <p role="alert" className="px-5 text-sm text-red-700">Workflow evidence could not be loaded. Refresh before relying on completion status.</p>}
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded-lg bg-[#1B3A5C]">
            <Zap className="h-4 w-4 text-[#E8720C]" />
          </div>
          <div className="text-left">
            <p className="text-sm font-bold text-[#1B3A5C]">
              {allDone ? 'Workflow Complete 🎉' : `Getting Started — Step ${currentStep} of 11`}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              {allDone ? 'Recorded workflow milestones complete; launch approval remains separate.' : `${completedSteps.size} of 11 steps complete`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Progress bar */}
          <div className="hidden sm:flex items-center gap-2">
            <div className="w-32 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-[#E8720C] rounded-full transition-all duration-700"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-gray-500">{pct}%</span>
          </div>
          <Link
            to="/manual"
            onClick={e => e.stopPropagation()}
            className="hidden sm:flex items-center gap-1 text-xs text-gray-400 hover:text-[#1B3A5C] transition-colors"
          >
            <BookOpen className="h-3.5 w-3.5" /> Full manual
          </Link>
          {expanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
        </div>
      </button>

      {/* Steps list */}
      {expanded && (
        <div className="border-t border-gray-100 divide-y divide-gray-50">
          {WORKFLOW_STEPS.map((step) => {
            const isDone    = completedSteps.has(step.number);
            const isActive  = step.number === currentStep;
            const isLocked  = !isDone && !isActive;
            const isOpen    = openDetail === step.number;
            const detail    = STEP_DETAILS[step.number];

            return (
              <div
                key={step.number}
                className={`transition-colors ${isActive ? 'bg-[#1B3A5C]/[0.03]' : ''}`}
              >
                {/* Step row */}
                <button
                  onClick={() => setOpenDetail(isOpen ? null : step.number)}
                  className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-gray-50/80 transition-colors"
                >
                  {/* Status icon */}
                  <div className="shrink-0">
                    {isDone ? (
                      <CheckCircle className="h-5 w-5 text-green-500" />
                    ) : isActive ? (
                      <div className="h-5 w-5 rounded-full border-2 border-[#E8720C] bg-[#E8720C] flex items-center justify-center">
                        <span className="text-white text-[10px] font-black">{step.number}</span>
                      </div>
                    ) : (
                      <div className="h-5 w-5 rounded-full border-2 border-gray-200 flex items-center justify-center">
                        <span className="text-gray-300 text-[10px] font-bold">{step.number}</span>
                      </div>
                    )}
                  </div>

                  {/* Title */}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-semibold truncate ${
                      isDone ? 'text-gray-400 line-through' : isActive ? 'text-[#1B3A5C]' : 'text-gray-400'
                    }`}>
                      {step.title}
                    </p>
                    {isActive && !isOpen && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate">{step.description}</p>
                    )}
                  </div>

                  {/* Active CTA badge */}
                  {isActive && (
                    <span className="shrink-0 text-xs font-bold text-[#E8720C] bg-[#E8720C]/10 px-2 py-0.5 rounded-full">
                      Current
                    </span>
                  )}

                  {isLocked && (
                    <Lock className="h-3.5 w-3.5 text-gray-200 shrink-0" />
                  )}

                  {!isLocked && (
                    isOpen
                      ? <ChevronUp className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                      : <ChevronDown className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                  )}
                </button>

                {/* Expanded detail */}
                {isOpen && !isLocked && (
                  <div className={`px-5 pb-4 ${isActive ? 'bg-[#1B3A5C]/[0.03]' : 'bg-gray-50/50'}`}>
                    <div className="ml-8 space-y-3">
                      {/* What you do */}
                      <div>
                        <p className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">What you do</p>
                        <p className="text-sm text-gray-700 leading-relaxed">{detail.what}</p>
                      </div>
                      {/* What system does */}
                      <div>
                        <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-1">System does automatically</p>
                        <p className="text-sm text-gray-500 leading-relaxed">{detail.system}</p>
                      </div>
                      {/* Step 3: strategy-specific PropStream pull instructions */}
                      {step.number === 3 && <PropStreamPullGuide />}
                      {/* CTA row */}
                      <div className="flex flex-wrap items-center gap-3">
                        {(isActive || isDone) && (
                          <Link
                            to={step.path}
                            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold transition-colors ${
                              isActive
                                ? 'bg-[#E8720C] text-white hover:bg-[#d4660b]'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                          >
                            {step.cta} <ArrowRight className="h-4 w-4" />
                          </Link>
                        )}
                        {/* Manual completion — lets users tick off steps that have no
                            clean data signal (e.g. reviewing the priority list) */}
                        {step.number !== 1 && (
                          <label className="inline-flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={manualComplete.has(step.number)}
                              onChange={() => toggleManualComplete(step.number)}
                              className="h-4 w-4 rounded border-gray-300 text-[#1B3A5C] focus:ring-[#1B3A5C]"
                            />
                            Mark this step complete
                          </label>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* All done state */}
      {allDone && expanded && (
        <div className="border-t border-gray-100 px-5 py-4 bg-green-50 flex items-center justify-between">
          <div>
            <p className="text-sm font-bold text-green-700">All 11 steps complete!</p>
            <p className="text-xs text-green-600 mt-0.5">Review your Stack Analytics to target the best lead sources next cycle.</p>
          </div>
          <Link to="/reports" className="text-xs font-bold text-green-700 hover:underline flex items-center gap-1">
            View Reports <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}
    </div>
  );
}
