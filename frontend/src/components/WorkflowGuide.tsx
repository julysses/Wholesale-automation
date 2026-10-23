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
  1: { what: 'Open Setup Wizard to review agency identity, PropStream, Retell and Twilio configuration. Database changes are managed during deployment.',
       system: 'Checks configured connections. Successful checks do not prove lead intake, scheduled collection, call completion or SMS delivery.' },
  2: { what: 'Choose your acquisition strategy in the Strategy Comparison Panel.',
       system: 'Updates funnel targets and planning benchmarks. A strategy selection does not start outreach.' },
  3: { what: 'Import a supported CSV in Leads, or review county evidence and existing PropStream results in Daily Lists. Confirm the saved lead, owner and follow-up task.',
       system: 'Reconciles supported imports with existing CRM identities. DNC and other contact restrictions are preserved; a discovered phone number is not outreach clearance.' },
  4: { what: 'Review priority scores, property evidence, contact identity and channel eligibility before selecting a calling batch.',
       system: 'Shows tier and stack analytics. Scores prioritize review; they do not establish consent or permission to contact a seller.' },
  5: { what: 'Review the selected leads, Retell agent, number and schedule. Start a campaign only after calling eligibility and provider acceptance are verified.',
       system: 'Checks each lead before dispatch and records the provider outcome. A submitted call is not a completed conversation.' },
  6: { what: 'Review call outcomes, stalled-work alerts and assigned follow-up tasks each day. Respond promptly to interested sellers.',
       system: 'Records provider events and follow-up work. Check actual CRM history for task creation and message delivery.' },
  7: { what: 'Open Acquisitions, review the seller conversation and assigned task, then follow up through an eligible channel.',
       system: 'Shows recorded qualification and outreach history. A HOT score does not mean an SMS was delivered.' },
  8: { what: 'Run Deal Analysis and review property details, comparable sales and repairs. Enter the offer price yourself after reviewing the evidence.',
       system: 'Provides underwriting context. Estimates do not populate an approved offer or contract price.' },
  9: { what: 'Review the Negotiation brief, enter your proposed terms and approve the exact saved offer content.',
       system: 'Saves a versioned draft and approval history. Approval does not send an offer or authorize outreach.' },
  10: { what: 'Record the agreed appointment date, time and type, then check any requested confirmation in the message history.',
        system: 'Saves the appointment. Confirmation and reminder messages depend on eligibility, enabled delivery and provider receipts.' },
  11: { what: 'Record the signed agreement and actual deal progress in Pipeline. Log the closing and assignment fee when confirmed.',
        system: 'Uses recorded deal data for pipeline reporting. Completing this guide does not certify a closing or launch readiness.' },
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
                        <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-1">What to verify</p>
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
