/**
 * useWorkflowStep
 *
 * Detects the user's current step in the 11-step wholesale workflow by
 * querying real Supabase data. Returns the active step number (1–11),
 * completion status of every step, and the next step to act on.
 */

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';

// Same key StrategyComparisonPanel / FunnelPanel write to
const STRATEGY_STORAGE_KEY = 'acquisition_strategy';

export interface WorkflowStep {
  number: number;
  title: string;
  description: string;
  path: string;
  /** Short label for the StepBanner CTA */
  cta: string;
}

export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    number: 1,
    title: 'Complete Setup',
    description: 'Configure API keys and run database migrations.',
    path: '/setup',
    cta: 'Open Setup Wizard',
  },
  {
    number: 2,
    title: 'Choose Your Strategy',
    description: 'Pick Mass Outreach, Precision Targeting, or Stack-First Hybrid.',
    path: '/#strategy',
    cta: 'Open Strategy Selector',
  },
  {
    number: 3,
    title: 'Import Your First Leads',
    description: 'Upload a county tax delinquent list or XLeads CSV.',
    path: '/leads',
    cta: 'Import Leads',
  },
  {
    number: 4,
    title: 'Review Precision Targeting',
    description: 'Confirm your Top 2,000 priority list is ready before dialing.',
    path: '/#precision',
    cta: 'Open Precision Panel',
  },
  {
    number: 5,
    title: 'Launch AI Calling Campaign',
    description: 'Select Tier 1 leads and start the AI voice campaign.',
    path: '/leads',
    cta: 'Go to Leads',
  },
  {
    number: 6,
    title: 'Monitor Call Activity',
    description: 'Watch funnel progress and contact rates as calls go out.',
    path: '/#funnel',
    cta: 'View Funnel',
  },
  {
    number: 7,
    title: 'Review HOT Leads',
    description: 'Call back HOT leads within 1 hour of the alert.',
    path: '/acquisitions',
    cta: 'Open HOT Leads',
  },
  {
    number: 8,
    title: 'Run the AI Deal Analyzer',
    description: 'Get ARV, MAO, repair tier, and offer range for each HOT lead.',
    path: '/acquisitions',
    cta: 'Open Deal Analysis',
  },
  {
    number: 9,
    title: 'Use Negotiation Intelligence',
    description: 'Get your opening script, offer structure, and objection handlers.',
    path: '/acquisitions',
    cta: 'Open Negotiation',
  },
  {
    number: 10,
    title: 'Set the Appointment',
    description: 'Schedule the contract signing once the seller agrees.',
    path: '/acquisitions',
    cta: 'Open Appointments',
  },
  {
    number: 11,
    title: 'Close the Contract',
    description: 'Sign the PSA, upload docs, and log the assignment fee.',
    path: '/pipeline',
    cta: 'Open Pipeline',
  },
];

export interface WorkflowProgress {
  /** 1-based index of the current active step */
  currentStep: number;
  /** Which step numbers are fully complete */
  completedSteps: Set<number>;
  /** The step object for the current active step */
  activeStep: WorkflowStep;
  /** The next step object (null if all done) */
  nextStep: WorkflowStep | null;
  /** 0–100 overall completion percentage */
  pct: number;
  isLoading: boolean;
}

interface CheckData {
  hasLeads: boolean;
  hasTieredLeads: boolean;
  hasCalls: boolean;
  hasManyCalls: boolean;
  hasHotLeads: boolean;
  hasDealAnalyses: boolean;
  hasOfferRecs: boolean;
  hasAppointments: boolean;
  hasDeals: boolean;
  strategyChosen: boolean;
}

// Whether a step is complete based purely on live Supabase data.
function dataDone(step: number, d: CheckData): boolean {
  switch (step) {
    case 1:  return true; // setup — complete if they're logged in
    case 2:  return d.strategyChosen;
    case 3:  return d.hasLeads;
    case 4:  return d.hasTieredLeads;
    case 5:  return d.hasCalls;
    case 6:  return d.hasManyCalls;
    case 7:  return d.hasHotLeads;
    case 8:  return d.hasDealAnalyses;
    case 9:  return d.hasOfferRecs;
    case 10: return d.hasAppointments;
    case 11: return d.hasDeals;
    default: return false;
  }
}

// ── Manual step completion ────────────────────────────────────────────────────
// Some steps (e.g. reviewing the priority list) have no clean data signal, so
// users can tick them off by hand. Stored in localStorage, reactive via event.
const MANUAL_KEY = 'workflow_manual_complete';

export function getManualComplete(): Set<number> {
  try {
    const raw = localStorage.getItem(MANUAL_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(arr) ? arr.filter((n: unknown) => typeof n === 'number') : []);
  } catch {
    return new Set();
  }
}

export function toggleManualComplete(step: number): void {
  const s = getManualComplete();
  if (s.has(step)) s.delete(step);
  else s.add(step);
  try { localStorage.setItem(MANUAL_KEY, JSON.stringify([...s])); } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent('workflowManualChange'));
}

export function useWorkflowStep(): WorkflowProgress {
  const { data, isLoading } = useQuery({
    queryKey: ['workflow_progress'],
    staleTime: 30_000,
    refetchInterval: 60_000,
    queryFn: async (): Promise<CheckData> => {
      const [
        leadsRes,
        tieredLeadsRes,
        callsRes,
        manyCallsRes,
        hotLeadsRes,
        dealAnalysesRes,
        offerRecsRes,
        appointmentsRes,
        dealsRes,
      ] = await Promise.all([
        supabase.from('leads').select('id', { count: 'exact', head: true }),
        supabase.from('leads').select('id', { count: 'exact', head: true }).not('precision_tier', 'is', null),
        supabase.from('ai_call_records').select('id', { count: 'exact', head: true }),
        supabase.from('ai_call_records').select('id', { count: 'exact', head: true }).gt('id', '0').limit(1).maybeSingle(),
        supabase.from('leads').select('id', { count: 'exact', head: true }).eq('status', 'hot'),
        supabase.from('deal_analyses').select('id', { count: 'exact', head: true }),
        supabase.from('offer_recommendations').select('id', { count: 'exact', head: true }),
        supabase.from('tasks').select('id', { count: 'exact', head: true }).ilike('type', '%appointment%'),
        supabase.from('deals').select('id', { count: 'exact', head: true }),
      ]);

      return {
        hasLeads:        (leadsRes.count ?? 0) > 0,
        hasTieredLeads:  (tieredLeadsRes.count ?? 0) > 0,
        hasCalls:        (callsRes.count ?? 0) > 0,
        hasManyCalls:    (callsRes.count ?? 0) >= 50,
        hasHotLeads:     (hotLeadsRes.count ?? 0) > 0,
        hasDealAnalyses: (dealAnalysesRes.count ?? 0) > 0,
        hasOfferRecs:    (offerRecsRes.count ?? 0) > 0,
        hasAppointments: (appointmentsRes.count ?? 0) > 0,
        hasDeals:        (dealsRes.count ?? 0) > 0,
        strategyChosen: false, // overridden below from localStorage
      };
    },
  });

  // Strategy choice lives in localStorage (written by StrategyComparisonPanel /
  // FunnelPanel under 'acquisition_strategy'). Track it reactively so the
  // workflow advances the moment the user clicks a strategy — no refetch needed.
  const [strategyChosen, setStrategyChosen] = useState<boolean>(() => {
    try { return Boolean(localStorage.getItem(STRATEGY_STORAGE_KEY)); }
    catch { return false; }
  });
  useEffect(() => {
    const handler = () => setStrategyChosen(true);
    window.addEventListener('strategyChange', handler);
    return () => window.removeEventListener('strategyChange', handler);
  }, []);

  // Manually-ticked steps (reactive)
  const [manual, setManual] = useState<Set<number>>(() => getManualComplete());
  useEffect(() => {
    const handler = () => setManual(getManualComplete());
    window.addEventListener('workflowManualChange', handler);
    return () => window.removeEventListener('workflowManualChange', handler);
  }, []);

  const fallback: CheckData = {
    hasLeads: false, hasTieredLeads: false, hasCalls: false,
    hasManyCalls: false, hasHotLeads: false, hasDealAnalyses: false,
    hasOfferRecs: false, hasAppointments: false, hasDeals: false,
    strategyChosen: false,
  };

  const d = { ...(data ?? fallback), strategyChosen };

  // A step is complete if the data says so OR the user ticked it manually.
  const completedSteps = new Set<number>();
  for (let step = 1; step <= WORKFLOW_STEPS.length; step++) {
    if (dataDone(step, d) || manual.has(step)) completedSteps.add(step);
  }
  // Current step = the first one not yet complete (linear walk).
  let currentStep = WORKFLOW_STEPS.length;
  for (let step = 1; step <= WORKFLOW_STEPS.length; step++) {
    if (!completedSteps.has(step)) { currentStep = step; break; }
  }

  const pct = Math.round((completedSteps.size / WORKFLOW_STEPS.length) * 100);
  const activeStep = WORKFLOW_STEPS[currentStep - 1];
  const nextStep = currentStep < WORKFLOW_STEPS.length ? WORKFLOW_STEPS[currentStep] : null;

  return { currentStep, completedSteps, activeStep, nextStep, pct, isLoading };
}
