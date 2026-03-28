/**
 * useWorkflowStep
 *
 * Detects the user's current step in the 11-step wholesale workflow by
 * querying real Supabase data. Returns the active step number (1–11),
 * completion status of every step, and the next step to act on.
 */

import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';

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
    path: '/',
    cta: 'Choose on Dashboard',
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
    path: '/',
    cta: 'Review on Dashboard',
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
    path: '/',
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

function resolveCurrentStep(d: CheckData): number {
  // Walk forward — the first step NOT complete is the current one
  if (!d.strategyChosen)    return 2;   // setup (step 1) always passes if logged in
  if (!d.hasLeads)          return 3;
  if (!d.hasTieredLeads)    return 4;
  if (!d.hasCalls)          return 5;
  if (!d.hasManyCalls)      return 6;
  if (!d.hasHotLeads)       return 7;
  if (!d.hasDealAnalyses)   return 8;
  if (!d.hasOfferRecs)      return 9;
  if (!d.hasAppointments)   return 10;
  if (!d.hasDeals)          return 11;
  return 11; // all done — stay on step 11
}

function buildCompletedSet(d: CheckData, current: number): Set<number> {
  const done = new Set<number>();
  done.add(1); // step 1 = setup = always complete if they're logged in
  if (current > 2)  done.add(2);
  if (current > 3)  done.add(3);
  if (current > 4)  done.add(4);
  if (current > 5)  done.add(5);
  if (current > 6)  done.add(6);
  if (current > 7)  done.add(7);
  if (current > 8)  done.add(8);
  if (current > 9)  done.add(9);
  if (current > 10) done.add(10);
  if (d.hasDeals)   done.add(11);
  return done;
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

      const strategyChosen = Boolean(
        typeof window !== 'undefined' && localStorage.getItem('wholesaleStrategy')
      );

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
        strategyChosen,
      };
    },
  });

  const fallback: CheckData = {
    hasLeads: false, hasTieredLeads: false, hasCalls: false,
    hasManyCalls: false, hasHotLeads: false, hasDealAnalyses: false,
    hasOfferRecs: false, hasAppointments: false, hasDeals: false,
    strategyChosen: false,
  };

  const d = data ?? fallback;
  const currentStep = resolveCurrentStep(d);
  const completedSteps = buildCompletedSet(d, currentStep);
  const pct = Math.round((completedSteps.size / WORKFLOW_STEPS.length) * 100);
  const activeStep = WORKFLOW_STEPS[currentStep - 1];
  const nextStep = currentStep < WORKFLOW_STEPS.length ? WORKFLOW_STEPS[currentStep] : null;

  return { currentStep, completedSteps, activeStep, nextStep, pct, isLoading };
}
