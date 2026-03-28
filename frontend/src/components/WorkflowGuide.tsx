/**
 * WorkflowGuide
 *
 * Full 11-step getting-started tracker shown on the Dashboard.
 * Each step auto-detects completion from real Supabase data.
 * Completed steps are checked off. The current active step is highlighted
 * with a prominent CTA. Future steps are shown as locked/dimmed.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle, Circle, Lock, ChevronDown, ChevronUp, ArrowRight, BookOpen, Zap } from 'lucide-react';
import { useWorkflowStep, WORKFLOW_STEPS } from '@/hooks/useWorkflowStep';

const STEP_DETAILS: Record<number, { what: string; system: string }> = {
  1:  { what: 'Register, run the 7 database migrations in Supabase SQL Editor, and save your API keys in the Setup Wizard.',
        system: 'Validates keys, creates your user profile, and initializes the full database schema.' },
  2:  { what: 'Scroll to the Strategy Comparison Panel and click Select on Mass Outreach, Precision Targeting, or Stack-First Hybrid.',
        system: 'Updates funnel targets, conversion benchmarks, and lead import recommendations to match your chosen strategy.' },
  3:  { what: 'Click Import CSV, upload your county tax delinquent list or XLeads export, and confirm the column mapping.',
        system: 'Removes DNC numbers, calculates distress scores with stacking bonuses, assigns Precision Tiers, and fills your Top 2,000 priority list.' },
  4:  { what: 'Check the Precision Targeting Panel — confirm Top 2,000 is ≥ 50% filled and you have 200+ Tier 1 leads before dialing.',
        system: 'Shows real-time tier breakdown and stack analytics so you know which lead sources are strongest.' },
  5:  { what: 'Filter leads to Precision Tier 1, select all, click Launch AI Dialing Campaign, and confirm the schedule.',
        system: 'Retell AI dials every lead, qualifies sellers with natural conversation, records calls, extracts intent signals, and scores every conversation.' },
  6:  { what: 'Check the funnel morning and evening. Watch for HOT lead notifications — they require action within 1 hour.',
        system: 'Updates funnel metrics every 2 minutes. Fires HOT lead automation instantly: pauses dialing, sends SMS, creates task.' },
  7:  { what: 'Open Acquisitions → HOT Leads, read the qualification summary and key quotes, then call the seller personally.',
        system: 'Already paused dialing, sent an SMS, and created your follow-up task before you even opened the page.' },
  8:  { what: 'Click Run Deal Analysis on a HOT lead, add any property details from your call, then review ARV, MAO, and exit strategy.',
        system: 'Estimates ARV with Claude AI, applies repair tiers ($15–$75+/sqft), calculates MAO, and generates your offer range.' },
  9:  { what: 'Open the Negotiation tab, read the personalized brief, use the opening script, and stay within the offer structure.',
        system: 'Generates opening/target/ceiling offers from your MAO, writes a seller-specific script from the call transcript, and provides 5 objection handlers.' },
  10: { what: 'Click Schedule Appointment after verbal agreement — enter date, time, and type (virtual / in-person / contract signing).',
        system: 'Sends the seller a confirmation SMS and a reminder SMS 24 hours before the meeting.' },
  11: { what: 'Sign the Purchase & Sale Agreement, upload it to the lead record, update status to Under Contract, then market to buyers.',
        system: 'Creates the deal in your Pipeline, updates KPI metrics, and logs the assignment fee into stack analytics to improve future targeting.' },
};

export function WorkflowGuide() {
  const { currentStep, completedSteps, pct, isLoading } = useWorkflowStep();
  const [expanded, setExpanded] = useState(true);
  const [openDetail, setOpenDetail] = useState<number | null>(currentStep);

  if (isLoading) return null;

  // Hide guide once all 11 steps done and user has contracts
  const allDone = completedSteps.size === 11;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
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
              {allDone ? 'You\'ve completed the full wholesale workflow.' : `${completedSteps.size} of 11 steps complete`}
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
                      {/* CTA */}
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
