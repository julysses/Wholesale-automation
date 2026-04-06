import { useState, useEffect } from 'react';
import { ChevronRight, ChevronLeft, Save, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { supabase } from '@/lib/supabase';
import { CAMPAIGN_RULES, DFW_COUNTIES, TIER1_SIGNALS, AUDIENCE_TYPE_TO_SEGMENT, type DFWCounty } from '@/lib/fb-ads/battlePlanRules';
import { Step1CampaignSettings } from './steps/Step1CampaignSettings';
import { Step2AudienceBuilder } from './steps/Step2AudienceBuilder';
import { Step3AdSetConfigurator } from './steps/Step3AdSetConfigurator';
import { Step4CreativeStudio } from './steps/Step4CreativeStudio';
import { Step5LeadFormBuilder } from './steps/Step5LeadFormBuilder';
import { Step6PreFlightChecklist } from './steps/Step6PreFlightChecklist';
import type { Segment } from '@/lib/fb-ads/battlePlanRules';

const STEPS = [
  { num: 1, label: 'Campaign Settings' },
  { num: 2, label: 'Audience Builder' },
  { num: 3, label: 'Ad Set Configurator' },
  { num: 4, label: 'Creative Studio' },
  { num: 5, label: 'Lead Form Builder' },
  { num: 6, label: 'Pre-Flight Checklist' },
];

const today = new Date().toISOString().split('T')[0];
const defaultTier1: string[] = TIER1_SIGNALS.filter(s => s.defaultOn).map(s => s.id);

const INITIAL_STATE = {
  step1: {
    name: '',
    daily_budget: CAMPAIGN_RULES.DEFAULT_DAILY_BUDGET as number,
    ab_test_enabled: true,
    start_date: today,
  },
  step2: {
    custom_audiences: [] as any[],
    tier1_signals: defaultTier1,
    tier2_signals: [] as string[],
    tier3_signals: [] as string[],
    counties: ['Dallas', 'Tarrant'] as DFWCounty[],
    income_min: 40000,
    income_max: 100000,
  },
  step3: {
    ad_sets: [] as any[],
    total_budget: CAMPAIGN_RULES.DEFAULT_DAILY_BUDGET as number,
  },
  step4: {
    image_url: '',
    copy_a: '',
    copy_b: '',
    copy_c: '',
    active_segment: 'pre-foreclosure',
  },
  step5: {
    include_mortgage_balance: false,
    include_rented: false,
    include_best_time: false,
    confirmation_message: "Hi [name], thanks for reaching out. We received your info on [address]. Someone from our team will call you shortly — or reply here if you prefer to text.",
  },
};

interface Props {
  campaignId?: string;
  onComplete?: (id: string) => void;
  onCancel?: () => void;
}

export function CampaignWizard({ campaignId, onComplete, onCancel }: Props) {
  const [step, setStep] = useState(1);
  const [state, setState] = useState(INITIAL_STATE);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<string | undefined>(campaignId);
  const [blockReason, setBlockReason] = useState<string | undefined>();

  // Load existing campaign draft if editing
  useEffect(() => {
    if (!campaignId) return;
    supabase.from('fb_campaigns').select('*').eq('id', campaignId).single().then(({ data }) => {
      if (data?.wizard_state) {
        try { setState(data.wizard_state as typeof INITIAL_STATE); } catch {}
        setStep(data.wizard_step || 1);
      }
    });
  }, [campaignId]);

  const updateStep = <K extends keyof typeof state>(stepKey: K, updates: Partial<typeof state[K]>) => {
    setState(prev => ({
      ...prev,
      [stepKey]: { ...prev[stepKey], ...updates } as typeof state[K],
    }));
  };

  const validate = (stepNum: number): boolean => {
    const errs: Record<string, string> = {};

    if (stepNum === 1) {
      if (!state.step1.name.trim()) errs.name = 'Campaign name is required';
      if (!state.step1.start_date) errs.start_date = 'Start date is required';
      if (state.step1.daily_budget < CAMPAIGN_RULES.MIN_DAILY_BUDGET) errs.budget = `Minimum budget is $${CAMPAIGN_RULES.MIN_DAILY_BUDGET}`;
    }
    if (stepNum === 2) {
      const hasT1 = state.step2.tier1_signals.length > 0;
      const hasCustom = state.step2.custom_audiences.length > 0;
      if (!hasT1 && !hasCustom) {
        const reason = 'Your battle plan requires at least one Tier 1 distress signal or a Custom Audience upload. Cold reach without distress targeting produces low-quality leads.';
        setBlockReason(reason);
        errs.audience = reason;
      } else {
        setBlockReason(undefined);
      }
      if (state.step2.counties.length === 0) errs.counties = 'Select at least one DFW county';
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const saveDraft = async () => {
    setSaving(true);
    try {
      const payload = {
        name: state.step1.name || `Draft ${today}`,
        status: 'draft',
        daily_budget: state.step1.daily_budget,
        special_ad_category: true,
        ab_test_enabled: state.step1.ab_test_enabled,
        start_date: state.step1.start_date,
        wizard_step: step,
        wizard_state: state,
      };
      if (savedId) {
        await supabase.from('fb_campaigns').update(payload).eq('id', savedId);
      } else {
        const { data } = await supabase.from('fb_campaigns').insert(payload).select().single();
        if (data?.id) setSavedId(data.id);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleNext = () => {
    if (!validate(step)) return;
    if (step < 6) {
      setStep(s => s + 1);
    } else {
      saveDraft().then(() => { if (savedId) onComplete?.(savedId); });
    }
  };

  const handleBack = () => setStep(s => Math.max(1, s - 1));

  const detectedSegments: Segment[] = state.step2.custom_audiences
    .map((a: any) => AUDIENCE_TYPE_TO_SEGMENT[a.type] ?? 'pre-foreclosure')
    .filter(Boolean);

  return (
    <div className="max-w-3xl mx-auto">
      {/* Progress bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-600">Step {step} of {STEPS.length}</span>
          <button
            onClick={saveDraft}
            disabled={saving}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? 'Saving…' : 'Save Draft'}
          </button>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-2">
          <div
            className="bg-[#F5A623] h-2 rounded-full transition-all duration-500"
            style={{ width: `${(step / STEPS.length) * 100}%` }}
          />
        </div>
        <div className="flex justify-between mt-1">
          {STEPS.map(s => (
            <button
              key={s.num}
              onClick={() => s.num < step && setStep(s.num)}
              className={cn(
                'text-xs transition-colors',
                s.num === step ? 'text-[#F5A623] font-semibold' :
                s.num < step ? 'text-[#0A1628] cursor-pointer hover:text-[#0A1628]/70' : 'text-gray-300'
              )}
              disabled={s.num > step}
            >
              {s.num < step ? <CheckCircle className="h-3.5 w-3.5 inline text-green-500" /> : s.num}
              {' '}{!['lg', 'xl'].includes('') ? s.label : ''}
            </button>
          ))}
        </div>
      </div>

      {/* Step title */}
      <div className="mb-6">
        <h2 className="text-xl font-bold text-[#0A1628]">
          Step {step}: {STEPS.find(s => s.num === step)?.label}
        </h2>
      </div>

      {/* Step content */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm">
        {step === 1 && (
          <Step1CampaignSettings
            state={state.step1}
            onChange={(u) => updateStep('step1', u)}
            errors={errors}
          />
        )}
        {step === 2 && (
          <Step2AudienceBuilder
            state={state.step2}
            onChange={(u) => updateStep('step2', u)}
            errors={errors}
            blockReason={blockReason}
          />
        )}
        {step === 3 && (
          <Step3AdSetConfigurator
            state={state.step3}
            detectedSegments={detectedSegments}
            onChange={(u) => updateStep('step3', u)}
            errors={errors}
          />
        )}
        {step === 4 && (
          <Step4CreativeStudio
            state={state.step4}
            onChange={(u) => updateStep('step4', u)}
            errors={errors}
          />
        )}
        {step === 5 && (
          <Step5LeadFormBuilder
            state={state.step5}
            onChange={(u) => updateStep('step5', u)}
          />
        )}
        {step === 6 && (
          <Step6PreFlightChecklist wizardState={state as any} />
        )}
      </div>

      {/* Navigation */}
      <div className="flex justify-between mt-6">
        <div className="flex gap-2">
          {onCancel && (
            <button
              onClick={onCancel}
              className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
          )}
          {step > 1 && (
            <button
              onClick={handleBack}
              className="flex items-center gap-2 px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <ChevronLeft className="h-4 w-4" /> Back
            </button>
          )}
        </div>
        <button
          onClick={handleNext}
          className="flex items-center gap-2 px-6 py-2.5 bg-[#0A1628] text-white rounded-xl text-sm font-semibold hover:bg-[#0a1628]/90 transition-colors"
        >
          {step === 6 ? (
            <><CheckCircle className="h-4 w-4" /> Mark as Launch-Ready</>
          ) : (
            <>Next: {STEPS.find(s => s.num === step + 1)?.label} <ChevronRight className="h-4 w-4" /></>
          )}
        </button>
      </div>
    </div>
  );
}
