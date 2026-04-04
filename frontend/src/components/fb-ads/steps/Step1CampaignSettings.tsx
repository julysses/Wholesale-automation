import { AlertTriangle, Lock, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CAMPAIGN_RULES } from '@/lib/fb-ads/battlePlanRules';

interface Step1State {
  name: string;
  daily_budget: number;
  ab_test_enabled: boolean;
  start_date: string;
}

interface Props {
  state: Step1State;
  onChange: (updates: Partial<Step1State>) => void;
  errors: Record<string, string>;
}

export function Step1CampaignSettings({ state, onChange, errors }: Props) {
  const today = new Date().toISOString().split('T')[0];

  const handleBudget = (val: number) => {
    onChange({ daily_budget: val });
  };

  const budgetTooLow = state.daily_budget < CAMPAIGN_RULES.MIN_DAILY_BUDGET;
  const budgetTooHigh = state.daily_budget > CAMPAIGN_RULES.MAX_DAILY_BUDGET;

  return (
    <div className="space-y-6">
      <BattlePlanCallout>
        Campaign objective is locked to <strong>Leads</strong> and Housing Special Ad Category is <strong>legally required</strong> for all real estate ads. Daily budget range of $20–$100 is optimized for Meta's algorithm learning phase.
      </BattlePlanCallout>

      {/* Campaign Name */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1.5">
          Campaign Name <span className="text-red-500">*</span>
        </label>
        <input
          type="text"
          value={state.name}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder={`DFW-[Segment]-${today}`}
          className={cn(
            'w-full border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2',
            errors.name ? 'border-red-400 focus:ring-red-200' : 'border-gray-200 focus:ring-[#0A1628]/20'
          )}
        />
        {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
        <p className="text-xs text-gray-400 mt-1">Suggested: DFW-[Segment]-{today}</p>
      </div>

      {/* Locked fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <LockedField label="Objective" value="Leads" reason="Battle plan: Lead generation only" />
        <LockedField label="Buying Type" value="Auction" reason="Battle plan: Auction buying type" />
        <LockedField
          label="Special Ad Category"
          value="Housing — ON"
          reason="Legally required for all real estate ads"
          critical
        />
        <LockedField label="Device" value="All Devices" reason="Battle plan: All devices" />
      </div>

      {/* Daily Budget */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1.5">
          Daily Budget
        </label>
        <div className="flex items-center gap-3">
          <span className="text-gray-500 font-medium">$</span>
          <input
            type="number"
            min={CAMPAIGN_RULES.MIN_DAILY_BUDGET}
            max={CAMPAIGN_RULES.MAX_DAILY_BUDGET}
            step={5}
            value={state.daily_budget}
            onChange={(e) => handleBudget(Number(e.target.value))}
            className={cn(
              'w-32 border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2',
              (budgetTooLow || budgetTooHigh) ? 'border-amber-400 focus:ring-amber-200' : 'border-gray-200 focus:ring-[#0A1628]/20'
            )}
          />
          <span className="text-xs text-gray-500">per day (battle plan: $20–$100)</span>
        </div>

        {/* Budget slider */}
        <input
          type="range"
          min={CAMPAIGN_RULES.MIN_DAILY_BUDGET}
          max={CAMPAIGN_RULES.MAX_DAILY_BUDGET}
          step={5}
          value={state.daily_budget}
          onChange={(e) => handleBudget(Number(e.target.value))}
          className="w-full mt-2 accent-[#0A1628]"
        />
        <div className="flex justify-between text-xs text-gray-400">
          <span>$20 min</span>
          <span>$100 max</span>
        </div>

        {budgetTooLow && (
          <div className="flex items-start gap-2 mt-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-sm text-amber-800">
              Battle plan minimum is <strong>$20/day</strong>. Below this, Meta's algorithm won't optimize effectively.
            </p>
          </div>
        )}
      </div>

      {/* A/B Test toggle */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-2">A/B Testing</label>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => onChange({ ab_test_enabled: !state.ab_test_enabled })}
            className={cn(
              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
              state.ab_test_enabled ? 'bg-[#0A1628]' : 'bg-gray-300'
            )}
          >
            <span className={cn(
              'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
              state.ab_test_enabled ? 'translate-x-6' : 'translate-x-1'
            )} />
          </button>
          <span className="text-sm text-gray-700">
            {state.ab_test_enabled ? 'Enabled (recommended)' : 'Disabled'}
          </span>
        </div>
        {!state.ab_test_enabled && (
          <div className="flex items-start gap-2 mt-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-sm text-amber-800">
              Battle plan recommends A/B testing ON to identify top-performing creatives.
            </p>
          </div>
        )}
      </div>

      {/* Start Date */}
      <div>
        <label className="block text-sm font-semibold text-gray-700 mb-1.5">
          Start Date <span className="text-red-500">*</span>
        </label>
        <input
          type="date"
          value={state.start_date}
          min={today}
          onChange={(e) => onChange({ start_date: e.target.value })}
          className={cn(
            'border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2',
            errors.start_date ? 'border-red-400 focus:ring-red-200' : 'border-gray-200 focus:ring-[#0A1628]/20'
          )}
        />
        {errors.start_date && <p className="text-xs text-red-500 mt-1">{errors.start_date}</p>}
      </div>
    </div>
  );
}

function LockedField({ label, value, reason, critical }: {
  label: string; value: string; reason: string; critical?: boolean;
}) {
  return (
    <div className="border border-gray-100 rounded-lg p-3 bg-gray-50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
        <Lock className="h-3.5 w-3.5 text-gray-400" />
      </div>
      <p className={cn('text-sm font-semibold', critical ? 'text-red-600' : 'text-gray-800')}>{value}</p>
      <p className="text-xs text-gray-400 mt-1">{reason}</p>
    </div>
  );
}

export function BattlePlanCallout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 p-4 bg-[#0A1628]/5 border border-[#0A1628]/20 rounded-xl">
      <Info className="h-4 w-4 text-[#0A1628] shrink-0 mt-0.5" />
      <p className="text-sm text-[#0A1628]/80 leading-relaxed">{children}</p>
    </div>
  );
}
