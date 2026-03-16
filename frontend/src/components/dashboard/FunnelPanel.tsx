/**
 * FunnelPanel — Precision Acquisition Funnel visualization.
 *
 * PRD model: precision targeting — 2,000 high-probability leads
 * instead of mass outreach.
 *
 * Precision funnel (PRD Section 3 vs 4):
 *   Traditional:  30,000 leads → 20,000 calls → 2,000 convos → 2-4 deals
 *   Precision:    2,000 leads  → 1,500 calls  → 500 convos   → 2-6 deals
 *
 * Shows actual vs. target for each funnel stage pulled from Supabase
 * via the funnel_metrics view (migration 004 + 005).
 */

import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { Phone, MessageSquare, Flame, CalendarCheck, FileText, TrendingUp } from 'lucide-react';

interface FunnelMetrics {
  total_calls: number;
  conversations: number;
  interested: number;
  hot_leads: number;
  appointments: number;
  appointments_completed: number;
}

// PRD precision targeting model: 2,000 leads → 2-6 contracts/month
// (replaces mass-call model per PRD Section 1 + Section 3)
const TARGETS: FunnelMetrics = {
  total_calls: 1500,          // ~75% of 2,000 precision leads get called
  conversations: 500,         // 33% conversation rate from precision list
  interested: 150,            // 30% of conversations show interest
  hot_leads: 40,              // 27% of interested are HOT
  appointments: 12,           // 30% of HOT leads book
  appointments_completed: 6,  // 50% of appointments → contract
};

interface StageProps {
  icon: React.ReactNode;
  label: string;
  actual: number;
  target: number;
  color: string;
  bgColor: string;
  borderColor: string;
}

function FunnelStage({ icon, label, actual, target, color, bgColor, borderColor }: StageProps) {
  const pct = Math.min(100, Math.round((actual / target) * 100));
  const isOnTrack = pct >= 80;

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg border ${borderColor} ${bgColor}`}>
      <div className={`p-2 rounded-lg bg-white/70 ${color} shrink-0`}>
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className={`text-xs font-medium ${color}`}>{label}</span>
          <span className="text-xs text-gray-500">
            <span className={`font-bold ${isOnTrack ? 'text-green-600' : 'text-gray-700'}`}>
              {actual.toLocaleString()}
            </span>
            <span className="text-gray-400"> / {target.toLocaleString()}</span>
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
      <div className={`text-xs font-semibold shrink-0 ${
        isOnTrack ? 'text-green-600' : pct >= 50 ? 'text-yellow-600' : 'text-red-500'
      }`}>
        {pct}%
      </div>
    </div>
  );
}

export function FunnelPanel() {
  const { data: metrics, isLoading } = useQuery<FunnelMetrics>({
    queryKey: ['funnel_metrics'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('funnel_metrics')
        .select('*')
        .single();
      if (error || !data) {
        // Fallback: compute from individual tables
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
      return data as FunnelMetrics;
    },
    staleTime: 120000,
  });

  const actual = metrics ?? {
    total_calls: 0,
    conversations: 0,
    interested: 0,
    hot_leads: 0,
    appointments: 0,
    appointments_completed: 0,
  };

  // Projected monthly revenue (contracts × $10k avg fee)
  const projectedContracts = actual.appointments_completed;
  const projectedRevenue = projectedContracts * 10000;

  const stages: StageProps[] = [
    {
      icon: <Phone className="h-3.5 w-3.5" />,
      label: 'AI Calls Made',
      actual: actual.total_calls,
      target: TARGETS.total_calls,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-100',
    },
    {
      icon: <MessageSquare className="h-3.5 w-3.5" />,
      label: 'Conversations',
      actual: actual.conversations,
      target: TARGETS.conversations,
      color: 'text-indigo-600',
      bgColor: 'bg-indigo-50',
      borderColor: 'border-indigo-100',
    },
    {
      icon: <TrendingUp className="h-3.5 w-3.5" />,
      label: 'Interested',
      actual: actual.interested,
      target: TARGETS.interested,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
      borderColor: 'border-purple-100',
    },
    {
      icon: <Flame className="h-3.5 w-3.5" />,
      label: 'Warm / Hot Leads',
      actual: actual.hot_leads,
      target: TARGETS.hot_leads,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-100',
    },
    {
      icon: <CalendarCheck className="h-3.5 w-3.5" />,
      label: 'Appointments Set',
      actual: actual.appointments,
      target: TARGETS.appointments,
      color: 'text-amber-700',
      bgColor: 'bg-amber-50',
      borderColor: 'border-amber-100',
    },
    {
      icon: <FileText className="h-3.5 w-3.5" />,
      label: 'Contracts Closed',
      actual: actual.appointments_completed,
      target: TARGETS.appointments_completed,
      color: 'text-green-700',
      bgColor: 'bg-green-50',
      borderColor: 'border-green-200',
    },
  ];

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-base font-semibold text-gray-900">Acquisition Funnel</h3>
        <span className="text-xs text-gray-400">Monthly target</span>
      </div>
      <p className="text-xs text-gray-500 mb-4">
        Precision model: 2,000 targeted leads → 500 convos → 6 contracts/mo
      </p>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-12 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {stages.map((s) => (
            <FunnelStage key={s.label} {...s} />
          ))}
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
            {projectedContracts} contract{projectedContracts !== 1 ? 's' : ''} × $10,000+ avg fee · target: 2–6/mo
          </div>
        </div>
      )}

      {projectedContracts === 0 && !isLoading && (
        <div className="mt-4 pt-4 border-t border-gray-100 text-center">
          <p className="text-xs text-gray-400">
            Precision target: 2–6 contracts/month · $10,000+ avg fee
          </p>
          <p className="text-xs font-medium text-gray-600 mt-0.5">= $20,000–$60,000/month</p>
        </div>
      )}
    </div>
  );
}
