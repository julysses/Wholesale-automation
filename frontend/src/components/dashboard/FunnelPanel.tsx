/**
 * FunnelPanel — Multi-strategy acquisition funnel with 3-way strategy toggle.
 *
 * Strategies (toggled via localStorage so selection persists):
 *
 *  A. Mass Outreach  (Old Blueprint)
 *     30,000 leads → 20,000 calls → 2,000 convos → 2–4 contracts
 *     Conv. rate: 0.007–0.013% | Cost index: $$$$
 *
 *  B. Precision Targeting  (PRD v2)
 *     2,000 leads → 1,500 calls → 500 convos → 2–6 contracts
 *     Conv. rate: 0.10–0.30% | Cost index: $
 *
 *  C. Stack-First Hybrid  (AI Recommended / Proprietary)
 *     5,000 leads (Tier 1 + 2 only) → 3,500 calls → 1,000 convos → 4–8 contracts
 *     Conv. rate: 0.08–0.16% | Cost index: $$
 *
 * Shows actual vs. target for each funnel stage pulled from Supabase
 * via the funnel_metrics view (migration 004 + 005).
 */

import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { cn } from '@/lib/utils';
import {
  Phone, MessageSquare, Flame, CalendarCheck,
  FileText, TrendingUp, Zap, ChevronRight,
} from 'lucide-react';

// ── Strategy definitions ──────────────────────────────────────────────────────

export type StrategyKey = 'mass' | 'precision' | 'hybrid';

export interface FunnelStrategy {
  key: StrategyKey;
  label: string;
  badge: string;
  description: string;
  costIndex: string;
  bestFor: string;
  conversionRange: string;   // e.g. "0.10–0.30%"
  contractsRange: string;    // e.g. "2–6 / mo"
  revenueRange: string;      // e.g. "$20k–$60k / mo"
  color: string;             // Tailwind text color
  activeBg: string;          // active tab bg
  activeBorder: string;
  targets: FunnelMetrics;
  stageRatios: string[];     // conversion ratio label per stage (5 stages)
}

export interface FunnelMetrics {
  total_calls: number;
  conversations: number;
  interested: number;
  hot_leads: number;
  appointments: number;
  appointments_completed: number;
}

export const STRATEGIES: Record<StrategyKey, FunnelStrategy> = {
  mass: {
    key: 'mass',
    label: 'Mass Outreach',
    badge: 'Old Blueprint',
    description: '30k raw leads, high volume AI dialing, lower per-lead cost. Best for maximum market coverage.',
    costIndex: '$$$$',
    bestFor: 'Maximum coverage · scaling teams · high-volume markets',
    conversionRange: '0.007–0.013%',
    contractsRange: '2–4 / mo',
    revenueRange: '$20k–$40k / mo',
    color: 'text-gray-700',
    activeBg: 'bg-gray-800',
    activeBorder: 'border-gray-700',
    targets: {
      total_calls: 20000,
      conversations: 2000,
      interested: 200,
      hot_leads: 60,
      appointments: 15,
      appointments_completed: 3,
    },
    stageRatios: ['67% contact rate', '10% conv. rate', '10% interest', '30% qualify', '20% close'],
  },
  precision: {
    key: 'precision',
    label: 'Precision Targeting',
    badge: 'PRD v2',
    description: '2,000 stacked-distress leads only. Highest quality, lowest cost, ideal for lean teams.',
    costIndex: '$',
    bestFor: 'Lean teams · quality over volume · maximum ROI',
    conversionRange: '0.10–0.30%',
    contractsRange: '2–6 / mo',
    revenueRange: '$20k–$60k / mo',
    color: 'text-blue-700',
    activeBg: 'bg-blue-600',
    activeBorder: 'border-blue-500',
    targets: {
      total_calls: 1500,
      conversations: 500,
      interested: 150,
      hot_leads: 40,
      appointments: 12,
      appointments_completed: 5,
    },
    stageRatios: ['75% contact rate', '33% conv. rate', '30% interest', '27% qualify', '42% close'],
  },
  hybrid: {
    key: 'hybrid',
    label: 'Stack-First Hybrid',
    badge: '⚡ AI Recommended',
    description: '5,000 Tier 1 + Tier 2 stacked leads. Balances volume and quality — most contracts per dollar spent.',
    costIndex: '$$',
    bestFor: 'Growing teams · max deal flow · balanced cost-per-contract',
    conversionRange: '0.08–0.16%',
    contractsRange: '4–8 / mo',
    revenueRange: '$40k–$80k / mo',
    color: 'text-emerald-700',
    activeBg: 'bg-emerald-600',
    activeBorder: 'border-emerald-500',
    targets: {
      total_calls: 3500,
      conversations: 1000,
      interested: 280,
      hot_leads: 80,
      appointments: 25,
      appointments_completed: 6,
    },
    stageRatios: ['70% contact rate', '29% conv. rate', '28% interest', '29% qualify', '24% close'],
  },
};

const STORAGE_KEY = 'acquisition_strategy';

// ── Hooks ─────────────────────────────────────────────────────────────────────

function useStrategySelection() {
  const [strategy, setStrategyState] = useState<StrategyKey>(() => {
    try {
      return (localStorage.getItem(STORAGE_KEY) as StrategyKey) ?? 'precision';
    } catch {
      return 'precision';
    }
  });

  const setStrategy = (key: StrategyKey) => {
    setStrategyState(key);
    try { localStorage.setItem(STORAGE_KEY, key); } catch { /* ignore */ }
    window.dispatchEvent(new CustomEvent('strategyChange', { detail: key }));
  };

  // Sync across panels on same page
  useEffect(() => {
    const handler = (e: Event) => {
      setStrategyState((e as CustomEvent<StrategyKey>).detail);
    };
    window.addEventListener('strategyChange', handler);
    return () => window.removeEventListener('strategyChange', handler);
  }, []);

  return { strategy, setStrategy };
}

// ── FunnelStage ───────────────────────────────────────────────────────────────

interface StageProps {
  icon: React.ReactNode;
  label: string;
  actual: number;
  target: number;
  ratio: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

function FunnelStage({ icon, label, actual, target, ratio, color, bgColor, borderColor }: StageProps) {
  const pct = Math.min(100, Math.round((actual / target) * 100));
  const isOnTrack = pct >= 80;
  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border ${borderColor} ${bgColor}`}>
      <div className={`p-2 rounded-lg bg-white/70 ${color} shrink-0`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-1.5">
            <span className={`text-xs font-medium ${color}`}>{label}</span>
            <span className="text-xs text-gray-400 hidden sm:inline">({ratio})</span>
          </div>
          <span className="text-xs text-gray-500">
            <span className={`font-bold ${isOnTrack ? 'text-green-600' : 'text-gray-700'}`}>
              {(actual ?? 0).toLocaleString()}
            </span>
            <span className="text-gray-400"> / {(target ?? 0).toLocaleString()}</span>
          </span>
        </div>
        <div className="h-1.5 bg-white/50 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isOnTrack ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-400' : 'bg-red-400'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <div className={`text-xs font-semibold shrink-0 w-8 text-right ${
        isOnTrack ? 'text-green-600' : pct >= 50 ? 'text-yellow-600' : 'text-red-500'
      }`}>
        {pct}%
      </div>
    </div>
  );
}

// ── Strategy toggle pill ──────────────────────────────────────────────────────

function StrategyToggle({
  current,
  onChange,
}: {
  current: StrategyKey;
  onChange: (k: StrategyKey) => void;
}) {
  return (
    <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
      {(Object.values(STRATEGIES) as FunnelStrategy[]).map((s) => (
        <button
          key={s.key}
          onClick={() => onChange(s.key)}
          className={cn(
            'flex-1 text-xs font-medium rounded-md px-2 py-1.5 transition-all',
            current === s.key
              ? `${s.activeBg} text-white shadow-sm`
              : 'text-gray-500 hover:text-gray-700',
          )}
        >
          {s.key === 'hybrid' ? '⚡ Hybrid' : s.label.split(' ')[0]}
        </button>
      ))}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function FunnelPanel() {
  const { strategy, setStrategy } = useStrategySelection();
  const selected = STRATEGIES[strategy];

  const { data: metrics, isLoading } = useQuery<FunnelMetrics>({
    queryKey: ['funnel_metrics'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('funnel_metrics')
        .select('*')
        .single();
      if (error || !data) {
        const [callsRes, apptRes] = await Promise.all([
          supabase.from('ai_call_records').select('id, disposition'),
          supabase.from('appointments').select('id, status'),
        ]);
        const calls = callsRes.data ?? [];
        const appts = apptRes.data ?? [];
        return {
          total_calls: calls.length,
          conversations: calls.filter((c: any) =>
            !['no_answer', 'voicemail', 'unknown'].includes(c.disposition ?? '')
          ).length,
          interested: calls.filter((c: any) =>
            ['warm', 'hot', 'appointment_set', 'callback'].includes(c.disposition ?? '')
          ).length,
          hot_leads: calls.filter((c: any) =>
            ['hot', 'appointment_set'].includes(c.disposition ?? '')
          ).length,
          appointments: appts.length,
          appointments_completed: appts.filter((a: any) => a.status === 'completed').length,
        };
      }
      const d = data as any;
      return {
        total_calls:            d.total_calls            ?? 0,
        conversations:          d.conversations          ?? 0,
        interested:             d.interested             ?? 0,
        hot_leads:              d.hot_leads              ?? 0,
        appointments:           d.appointments           ?? 0,
        appointments_completed: d.appointments_completed ?? d.contracts_closed ?? 0,
      } as FunnelMetrics;
    },
    staleTime: 120000,
  });

  const actual: FunnelMetrics = metrics ?? {
    total_calls: 0, conversations: 0, interested: 0,
    hot_leads: 0, appointments: 0, appointments_completed: 0,
  };

  const targets = selected.targets;
  const ratios  = selected.stageRatios;

  const projectedContracts = actual.appointments_completed;
  const projectedRevenue   = projectedContracts * 10_000;

  const stages: StageProps[] = [
    { icon: <Phone className="h-3.5 w-3.5" />,       label: 'AI Calls Made',     actual: actual.total_calls,            target: targets.total_calls,            ratio: ratios[0], color: 'text-blue-600',   bgColor: 'bg-blue-50',   borderColor: 'border-blue-100' },
    { icon: <MessageSquare className="h-3.5 w-3.5" />,label: 'Conversations',     actual: actual.conversations,          target: targets.conversations,          ratio: ratios[1], color: 'text-indigo-600', bgColor: 'bg-indigo-50', borderColor: 'border-indigo-100' },
    { icon: <TrendingUp className="h-3.5 w-3.5" />,   label: 'Interested',        actual: actual.interested,             target: targets.interested,             ratio: ratios[2], color: 'text-purple-600', bgColor: 'bg-purple-50', borderColor: 'border-purple-100' },
    { icon: <Flame className="h-3.5 w-3.5" />,        label: 'Warm / Hot Leads',  actual: actual.hot_leads,              target: targets.hot_leads,              ratio: ratios[3], color: 'text-orange-600', bgColor: 'bg-orange-50', borderColor: 'border-orange-100' },
    { icon: <CalendarCheck className="h-3.5 w-3.5" />,label: 'Appointments Set',  actual: actual.appointments,           target: targets.appointments,           ratio: ratios[4], color: 'text-amber-700',  bgColor: 'bg-amber-50',  borderColor: 'border-amber-100' },
    { icon: <FileText className="h-3.5 w-3.5" />,     label: 'Contracts Closed',  actual: actual.appointments_completed, target: targets.appointments_completed, ratio: '',        color: 'text-green-700',  bgColor: 'bg-green-50',  borderColor: 'border-green-200' },
  ];

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      {/* Header + toggle */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-gray-900">Acquisition Funnel</h3>
        <span className="text-xs text-gray-400">Monthly target</span>
      </div>

      <StrategyToggle current={strategy} onChange={setStrategy} />

      {/* Selected strategy summary */}
      <div className={cn(
        'mt-3 mb-4 px-3 py-2 rounded-lg border text-xs',
        strategy === 'mass'      ? 'bg-gray-50 border-gray-200' :
        strategy === 'precision' ? 'bg-blue-50 border-blue-100' :
                                   'bg-emerald-50 border-emerald-100',
      )}>
        <div className="flex items-center gap-1.5 flex-wrap">
          {strategy === 'hybrid' && <Zap className="h-3.5 w-3.5 text-emerald-600 shrink-0" />}
          <span className={cn('font-semibold', selected.color)}>{selected.label}</span>
          <span className={cn(
            'px-1.5 py-0.5 rounded-full font-bold text-white text-[10px]',
            selected.activeBg,
          )}>
            {selected.badge}
          </span>
          <span className="text-gray-500 hidden sm:inline">·</span>
          <span className="text-gray-500 hidden sm:inline">{selected.contractsRange}</span>
          <span className="text-gray-500 hidden sm:inline">·</span>
          <span className={cn('font-semibold hidden sm:inline', selected.color)}>{selected.revenueRange}</span>
          <span className="ml-auto text-gray-400">Conv. {selected.conversionRange}</span>
        </div>
        <p className="text-gray-500 mt-1 leading-relaxed">{selected.description}</p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {stages.map((s) => <FunnelStage key={s.label} {...s} />)}
        </div>
      )}

      {/* Revenue projection */}
      {projectedContracts > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Projected Revenue</span>
            <span className="text-sm font-bold text-green-700">
              ${projectedRevenue.toLocaleString()}
            </span>
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {projectedContracts} contract{projectedContracts !== 1 ? 's' : ''} ×
            $10,000+ avg fee · target: {selected.contractsRange}
          </div>
        </div>
      )}

      {projectedContracts === 0 && !isLoading && (
        <div className="mt-4 pt-4 border-t border-gray-100 text-center">
          <p className="text-xs text-gray-400">
            Target: {selected.contractsRange} · $10,000+ avg fee
          </p>
          <p className={cn('text-xs font-medium mt-0.5', selected.color)}>
            {selected.revenueRange}
          </p>
        </div>
      )}
    </div>
  );
}
