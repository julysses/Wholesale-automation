/**
 * StrategyComparisonPanel
 *
 * Side-by-side comparison of all three acquisition strategies with
 * conversion ratios and ROI metrics for easy decision-making.
 *
 * Reads / writes the same localStorage key as FunnelPanel so both
 * components stay in sync without a prop-drilling context.
 *
 * Strategies:
 *
 *  A. Mass Outreach        — 30k leads, old blueprint, max coverage
 *  B. Precision Targeting  — 2k leads, PRD v2, highest ROI
 *  C. Stack-First Hybrid   — 5k Tier1+2 leads, AI Recommended, best deal flow
 */

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import {
  CheckCircle2, AlertCircle, Zap, TrendingUp,
  DollarSign, Users, Phone, Target, BarChart2,
  ChevronRight, Info,
} from 'lucide-react';
import { STRATEGIES, type StrategyKey, type FunnelStrategy } from './FunnelPanel';

const STORAGE_KEY = 'acquisition_strategy';

// ── Detailed per-strategy data ────────────────────────────────────────────────
// Enriches STRATEGIES with comparison-specific fields.

interface StrategyDetail {
  leadVolume: string;
  leadSources: string[];
  costPerLead: string;
  costPerContract: string;
  convRatioStages: { from: string; to: string; rate: string }[];
  pros: string[];
  cons: string[];
  idealFor: string[];
  timeToFirstDeal: string;
}

const DETAILS: Record<StrategyKey, StrategyDetail> = {
  mass: {
    leadVolume: '30,000 raw leads',
    leadSources: ['PropStream aged lists', 'Single-signal absentee', 'Driving for dollars'],
    costPerLead: '~$0.05–$0.15',
    costPerContract: '$3,000–$6,000',
    convRatioStages: [
      { from: '30,000 leads',   to: '20,000 calls',     rate: '67% contact' },
      { from: '20,000 calls',   to: '2,000 convos',     rate: '10% answer' },
      { from: '2,000 convos',   to: '200 interested',   rate: '10% interest' },
      { from: '200 interested', to: '15 appointments',  rate: '7.5% book' },
      { from: '15 appointments','to': '2–4 contracts',  rate: '13–27% close' },
    ],
    pros: [
      'Maximum market coverage',
      'Finds deals competitors miss',
      'Low per-lead data cost',
      'Good for high-population markets',
    ],
    cons: [
      'High call volume = high cost',
      'Low conversion wastes team time',
      'High DNC/opt-out rate over time',
      'Requires large calling infrastructure',
    ],
    idealFor: ['Large teams (5+ people)', 'High-density metro markets', 'Max brand awareness'],
    timeToFirstDeal: '30–60 days',
  },

  precision: {
    leadVolume: '~2,000 precision leads',
    leadSources: [
      'PropStream + all 5 government signals',
      'Tier 1 stacked distress only',
      'Absentee + vacant + tax delinquent',
    ],
    costPerLead: '~$0.50–$1.50',
    costPerContract: '$800–$2,000',
    convRatioStages: [
      { from: '2,000 leads',    to: '1,500 calls',      rate: '75% contact' },
      { from: '1,500 calls',    to: '500 convos',        rate: '33% answer' },
      { from: '500 convos',     to: '150 interested',    rate: '30% interest' },
      { from: '150 interested', to: '12 appointments',  rate: '8% book' },
      { from: '12 appointments','to': '2–6 contracts',  rate: '17–50% close' },
    ],
    pros: [
      'Highest conversion rate (0.10–0.30%)',
      'Lowest cost-per-contract ($800–$2k)',
      'Less calling = less burnout',
      'Sellers are pre-qualified by data',
      'Preserves DNC goodwill',
    ],
    cons: [
      'Smaller pipeline volume',
      'Requires 5 government data sources',
      'More setup for data stacking',
      'Limited to highest-distress areas',
    ],
    idealFor: ['Solo operators', '1–3 person teams', 'Low-overhead operations'],
    timeToFirstDeal: '14–30 days',
  },

  hybrid: {
    leadVolume: '~5,000 stacked leads',
    leadSources: [
      'PropStream Tier 1 + Tier 2 stacks',
      'All 5 government distress signals',
      'Excludes Tier 3 (single-signal) lists',
    ],
    costPerLead: '~$0.30–$0.80',
    costPerContract: '$1,500–$3,500',
    convRatioStages: [
      { from: '5,000 leads',    to: '3,500 calls',      rate: '70% contact' },
      { from: '3,500 calls',    to: '1,000 convos',     rate: '29% answer' },
      { from: '1,000 convos',   to: '280 interested',   rate: '28% interest' },
      { from: '280 interested', to: '25 appointments',  rate: '9% book' },
      { from: '25 appointments','to': '4–8 contracts',  rate: '16–32% close' },
    ],
    pros: [
      'Best contracts-per-dollar (most efficient)',
      '2× more deals than Precision alone',
      'Still 10× better conv. than Mass',
      'Covers Tier 1 + 2 stack combos',
      'Scales without exploding call volume',
    ],
    cons: [
      'Requires Tier 1 + Tier 2 data sourcing',
      'More complex list stacking workflow',
      'Mid-range per-lead cost',
    ],
    idealFor: ['Growing teams (2–4 people)', 'Maximum monthly deal flow', 'Reinvesting profits'],
    timeToFirstDeal: '14–21 days',
  },
};

// ── Helper components ─────────────────────────────────────────────────────────

function CostDots({ index }: { index: string }) {
  const filled = index.length;
  const max = 4;
  return (
    <div className="flex gap-0.5">
      {Array.from({ length: max }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'h-2 w-2 rounded-full',
            i < filled ? 'bg-current' : 'bg-gray-200',
          )}
        />
      ))}
    </div>
  );
}

function ConversionFunnel({ stages }: { stages: StrategyDetail['convRatioStages'] }) {
  return (
    <div className="space-y-1">
      {stages.map((s, i) => (
        <div key={i} className="flex items-center gap-1.5 text-xs">
          <span className="text-gray-500 shrink-0 w-32 truncate">{s.from}</span>
          <ChevronRight className="h-3 w-3 text-gray-300 shrink-0" />
          <span className="text-gray-700 font-medium shrink-0 w-28 truncate">{s.to}</span>
          <span className="ml-auto text-right shrink-0 font-semibold text-blue-600 w-16">{s.rate}</span>
        </div>
      ))}
    </div>
  );
}

// ── Strategy card ─────────────────────────────────────────────────────────────

function StrategyCard({
  strategy,
  detail,
  isActive,
  onSelect,
}: {
  strategy: FunnelStrategy;
  detail: StrategyDetail;
  isActive: boolean;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={cn(
        'rounded-2xl border-2 transition-all duration-200 overflow-hidden',
        isActive
          ? `border-current shadow-md ${strategy.color}`
          : 'border-gray-200 hover:border-gray-300',
      )}
    >
      {/* Card header */}
      <div
        className={cn(
          'p-4',
          isActive
            ? strategy.key === 'mass'      ? 'bg-gray-800 text-white'
              : strategy.key === 'precision' ? 'bg-blue-600 text-white'
              : 'bg-emerald-600 text-white'
            : 'bg-white',
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              {strategy.key === 'hybrid' && (
                <Zap className={cn('h-4 w-4', isActive ? 'text-yellow-300' : 'text-emerald-600')} />
              )}
              <span className={cn(
                'text-sm font-bold',
                isActive ? 'text-white' : strategy.color,
              )}>
                {strategy.label}
              </span>
              <span className={cn(
                'text-[10px] font-bold px-1.5 py-0.5 rounded-full',
                isActive
                  ? 'bg-white/20 text-white'
                  : strategy.key === 'hybrid'
                  ? 'bg-emerald-100 text-emerald-700'
                  : strategy.key === 'precision'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-600',
              )}>
                {strategy.badge}
              </span>
            </div>
            <p className={cn(
              'text-xs mt-1',
              isActive ? 'text-white/80' : 'text-gray-500',
            )}>
              {detail.leadVolume}
            </p>
          </div>

          {isActive && (
            <CheckCircle2 className="h-5 w-5 text-white shrink-0" />
          )}
        </div>

        {/* Key metrics row */}
        <div className="grid grid-cols-3 gap-2 mt-3">
          {[
            { icon: TrendingUp, label: 'Conv. rate',  value: strategy.conversionRange },
            { icon: Target,     label: 'Contracts',   value: strategy.contractsRange },
            { icon: DollarSign, label: 'Revenue/mo',  value: strategy.revenueRange.replace('/ mo', '').trim() },
          ].map((m) => (
            <div
              key={m.label}
              className={cn(
                'rounded-lg p-2 text-center',
                isActive ? 'bg-white/15' : 'bg-gray-50 border border-gray-100',
              )}
            >
              <p className={cn('text-[10px]', isActive ? 'text-white/70' : 'text-gray-400')}>
                {m.label}
              </p>
              <p className={cn(
                'text-xs font-bold mt-0.5',
                isActive ? 'text-white' : strategy.color,
              )}>
                {m.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Card body */}
      <div className="bg-white p-4 space-y-4">
        {/* Cost row */}
        <div className="flex items-center justify-between text-xs">
          <div>
            <span className="text-gray-400">Cost / lead: </span>
            <span className={cn('font-semibold', strategy.color)}>{detail.costPerLead}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-gray-400">Cost index:</span>
            <span className={cn(strategy.color)}>
              <CostDots index={strategy.costIndex} />
            </span>
          </div>
          <div>
            <span className="text-gray-400">/ contract: </span>
            <span className={cn('font-semibold', strategy.color)}>{detail.costPerContract}</span>
          </div>
        </div>

        {/* Conversion funnel (collapsible) */}
        <div>
          <button
            className="flex items-center gap-1 text-xs text-gray-500 font-medium hover:text-gray-700 mb-2"
            onClick={() => setExpanded(!expanded)}
          >
            <BarChart2 className="h-3.5 w-3.5" />
            Conversion funnel
            <span className="ml-1 text-gray-400">{expanded ? '▲' : '▼'}</span>
          </button>
          {expanded && <ConversionFunnel stages={detail.convRatioStages} />}
          {!expanded && (
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <Phone className="h-3 w-3" />
              {detail.convRatioStages[0].from}
              <ChevronRight className="h-3 w-3" />
              <span className="font-medium text-gray-600">
                {detail.convRatioStages[detail.convRatioStages.length - 1].to}
              </span>
              <span className="ml-auto font-semibold" style={{ color: 'inherit' }}>
                Conv. {strategy.conversionRange}
              </span>
            </div>
          )}
        </div>

        {/* Pros */}
        <div>
          <p className="text-xs font-semibold text-gray-500 mb-1.5">Strengths</p>
          <div className="space-y-1">
            {detail.pros.map((p) => (
              <div key={p} className="flex items-start gap-1.5 text-xs text-gray-600">
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0 mt-0.5" />
                {p}
              </div>
            ))}
          </div>
        </div>

        {/* Cons */}
        <div>
          <p className="text-xs font-semibold text-gray-500 mb-1.5">Trade-offs</p>
          <div className="space-y-1">
            {detail.cons.map((c) => (
              <div key={c} className="flex items-start gap-1.5 text-xs text-gray-500">
                <AlertCircle className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                {c}
              </div>
            ))}
          </div>
        </div>

        {/* Ideal for */}
        <div className="flex flex-wrap gap-1.5">
          {detail.idealFor.map((tag) => (
            <span
              key={tag}
              className={cn(
                'text-xs px-2 py-0.5 rounded-full border font-medium',
                isActive
                  ? strategy.key === 'mass'      ? 'bg-gray-100 text-gray-700 border-gray-200'
                    : strategy.key === 'precision' ? 'bg-blue-50 text-blue-700 border-blue-100'
                    : 'bg-emerald-50 text-emerald-700 border-emerald-100'
                  : 'bg-gray-50 text-gray-500 border-gray-100',
              )}
            >
              {tag}
            </span>
          ))}
        </div>

        {/* Time to first deal */}
        <div className="flex items-center gap-1.5 text-xs text-gray-500 border-t border-gray-100 pt-3">
          <Info className="h-3.5 w-3.5 text-gray-400" />
          <span>First deal est.</span>
          <span className={cn('font-semibold ml-auto', strategy.color)}>
            {detail.timeToFirstDeal}
          </span>
        </div>

        {/* Select button */}
        <button
          onClick={onSelect}
          className={cn(
            'w-full rounded-xl py-2.5 text-sm font-semibold transition-all',
            isActive
              ? strategy.key === 'mass'      ? 'bg-gray-800 text-white cursor-default'
                : strategy.key === 'precision' ? 'bg-blue-600 text-white cursor-default'
                : 'bg-emerald-600 text-white cursor-default'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
          )}
          disabled={isActive}
        >
          {isActive ? '✓ Active Strategy' : `Use ${strategy.label}`}
        </button>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function StrategyComparisonPanel() {
  const [current, setCurrent] = useState<StrategyKey>(() => {
    try { return (localStorage.getItem(STORAGE_KEY) as StrategyKey) ?? 'precision'; }
    catch { return 'precision'; }
  });

  const handleSelect = (key: StrategyKey) => {
    setCurrent(key);
    try { localStorage.setItem(STORAGE_KEY, key); } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('strategyChange', { detail: key }));
  };

  // Sync with FunnelPanel selections
  useEffect(() => {
    const handler = (e: Event) => setCurrent((e as CustomEvent<StrategyKey>).detail);
    window.addEventListener('strategyChange', handler);
    return () => window.removeEventListener('strategyChange', handler);
  }, []);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-5">
        <div>
          <h2 className="font-semibold text-gray-900 flex items-center gap-2">
            <Target className="h-5 w-5 text-blue-600" />
            Acquisition Strategy Selector
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Compare targeting approaches by conversion rate, cost-per-contract, and monthly deal flow.
            Your selection updates the Acquisition Funnel targets.
          </p>
        </div>
        <span className={cn(
          'shrink-0 text-xs font-bold px-2 py-1 rounded-full text-white',
          current === 'mass'      ? 'bg-gray-700'
          : current === 'precision' ? 'bg-blue-600'
          : 'bg-emerald-600',
        )}>
          {STRATEGIES[current].label}
        </span>
      </div>

      {/* Quick ROI comparison bar */}
      <div className="grid grid-cols-3 gap-2 mb-5">
        {(Object.values(STRATEGIES) as FunnelStrategy[]).map((s) => {
          const detail = DETAILS[s.key];
          return (
            <button
              key={s.key}
              onClick={() => handleSelect(s.key)}
              className={cn(
                'rounded-xl border-2 p-3 text-left transition-all',
                current === s.key
                  ? `${s.activeBorder} shadow-sm`
                  : 'border-gray-200 hover:border-gray-300',
              )}
            >
              <div className="flex items-center gap-1.5 mb-1">
                {s.key === 'hybrid' && <Zap className="h-3.5 w-3.5 text-emerald-600" />}
                <span className={cn('text-xs font-bold', s.color)}>{s.label.split(' ')[0]}</span>
                {current === s.key && <CheckCircle2 className={cn('h-3.5 w-3.5 ml-auto', s.color)} />}
              </div>
              <p className={cn('text-sm font-bold', s.color)}>{s.contractsRange}</p>
              <p className="text-xs text-gray-400">{detail.costPerContract}/deal</p>
            </button>
          );
        })}
      </div>

      {/* Full strategy cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {(Object.values(STRATEGIES) as FunnelStrategy[]).map((s) => (
          <StrategyCard
            key={s.key}
            strategy={s}
            detail={DETAILS[s.key]}
            isActive={current === s.key}
            onSelect={() => handleSelect(s.key)}
          />
        ))}
      </div>

      {/* Bottom insight */}
      <div className="mt-5 p-3 bg-amber-50 border border-amber-100 rounded-xl">
        <div className="flex items-start gap-2 text-xs text-amber-800">
          <Zap className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">AI Recommendation: </span>
            Stack-First Hybrid delivers the best contracts-per-dollar spent — roughly
            <span className="font-semibold"> 4× better conversion</span> than mass outreach with
            <span className="font-semibold"> 2× more monthly deals</span> than pure precision targeting.
            Ideal for teams ready to scale beyond a 2k lead list without mass-calling infrastructure.
          </div>
        </div>
      </div>
    </div>
  );
}
