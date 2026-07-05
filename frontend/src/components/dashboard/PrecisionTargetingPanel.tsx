/**
 * PrecisionTargetingPanel
 *
 * PRD Section 16 — Precision Targeting Dashboard
 *
 * Displays:
 *   • Imported vs suppressed vs prioritized lead counts
 *   • Top 2,000 leads breakdown by tier
 *   • Stack analytics (deals/conversion by list stack)
 *   • Average assignment fee by stack
 *
 * Precision tier conversion bands (PRD Section 7):
 *   Tier 1 — 1 deal / 200–700 records   (highest priority)
 *   Tier 2 — 1 deal / 500–1,200 records
 *   Tier 3 — 1 deal / 2,000–4,000 records
 */

import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/utils';
import {
  Target, Layers, TrendingUp, Award, AlertOctagon,
  ArrowRight, BarChart2, Zap, Download,
} from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface PrecisionSummary {
  total_imported:    number;
  total_suppressed:  number;
  total_prioritized: number;
  tier_1_count:      number;
  tier_2_count:      number;
  tier_3_count:      number;
  top_2000_count:    number;
  total_converted:   number;
  avg_assignment_fee: number | null;
}

interface StackRow {
  stack_name:          string;
  total_leads:         number;
  tier_1_leads:        number;
  converted_leads:     number;
  conversion_pct:      number;
  avg_assignment_fee:  number | null;
  avg_seller_score:    number | null;
}

// ── Hooks ─────────────────────────────────────────────────────────────────────

function usePrecisionSummary() {
  return useQuery<PrecisionSummary>({
    queryKey: ['precision_targeting_summary'],
    queryFn: async () => {
      const { data } = await supabase
        .from('precision_targeting_summary')
        .select('*')
        .single();
      return (data ?? {
        total_imported: 0, total_suppressed: 0, total_prioritized: 0,
        tier_1_count: 0, tier_2_count: 0, tier_3_count: 0,
        top_2000_count: 0, total_converted: 0, avg_assignment_fee: null,
      }) as PrecisionSummary;
    },
    staleTime: 60000,
  });
}

function useStackAnalytics() {
  return useQuery<StackRow[]>({
    queryKey: ['stack_analytics'],
    queryFn: async () => {
      const { data } = await supabase
        .from('stack_analytics')
        .select('*')
        .limit(10);
      return (data ?? []) as StackRow[];
    },
    staleTime: 60000,
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TierBadge({ tier }: { tier: 1 | 2 | 3 }) {
  const styles = {
    1: 'bg-red-100 text-red-800 border-red-200',
    2: 'bg-orange-100 text-orange-700 border-orange-200',
    3: 'bg-gray-100 text-gray-600 border-gray-200',
  };
  const labels = {
    1: 'Tier 1 — Highest',
    2: 'Tier 2 — High',
    3: 'Tier 3 — Supporting',
  };
  return (
    <span className={cn(
      'text-xs px-2 py-0.5 rounded-full border font-semibold',
      styles[tier],
    )}>
      {labels[tier]}
    </span>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  color: string;
  bg: string;
  border: string;
}

function StatCard({ label, value, sub, icon: Icon, color, bg, border }: StatCardProps) {
  // Vertical layout: icon + number on one row, label on its own full-width row
  // below so long labels wrap instead of truncating in a narrow column.
  return (
    <div className={cn('rounded-xl border p-3 min-w-0', bg, border)}>
      <div className="flex items-center gap-2 mb-1.5">
        <div className={cn('p-1.5 rounded-lg bg-white/70 shrink-0', color)}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <p className={cn('text-lg font-bold leading-none truncate', color)}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </p>
      </div>
      <p className="text-xs text-gray-600 font-medium leading-tight">{label}</p>
      {sub && <p className="text-[11px] text-gray-400 mt-0.5 leading-tight">{sub}</p>}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function PrecisionTargetingPanel() {
  const { data: summary, isLoading: summaryLoading } = usePrecisionSummary();
  const { data: stacks = [], isLoading: stacksLoading } = useStackAnalytics();

  const top2k = summary?.top_2000_count ?? 0;
  const pctFilled = Math.min(100, Math.round((top2k / 2000) * 100));

  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="h-5 w-5 text-blue-600" />
          <h2 className="font-semibold text-gray-900">Precision Targeting</h2>
        </div>
        <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
          PRD §7 — 2,000 precision leads
        </span>
      </div>

      {/* Lead pipeline stats — 2×2 so cards stay wide and readable in the sidebar */}
      {summaryLoading ? (
        <div className="grid grid-cols-2 gap-2.5">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-20 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2.5">
          <StatCard
            label="Imported Leads" value={summary?.total_imported ?? 0}
            icon={Layers} color="text-blue-700" bg="bg-blue-50" border="border-blue-100"
          />
          <StatCard
            label="Suppressed / DNC" value={summary?.total_suppressed ?? 0}
            sub="Removed from outreach"
            icon={AlertOctagon} color="text-gray-500" bg="bg-gray-50" border="border-gray-200"
          />
          <StatCard
            label="Prioritized" value={summary?.total_prioritized ?? 0}
            sub="Scored + ranked"
            icon={Zap} color="text-amber-600" bg="bg-amber-50" border="border-amber-100"
          />
          <StatCard
            label="Converted" value={summary?.total_converted ?? 0}
            sub={summary?.avg_assignment_fee
              ? `Avg fee: ${formatCurrency(summary.avg_assignment_fee)}`
              : undefined}
            icon={Award} color="text-green-700" bg="bg-green-50" border="border-green-100"
          />
        </div>
      )}

      {/* Top 2,000 progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-gray-700 flex items-center gap-1.5">
            <Target className="h-4 w-4 text-blue-500" />
            Top 2,000 Priority List
          </span>
          <span className="text-xs text-gray-500 font-medium">
            {top2k.toLocaleString()} / 2,000
            <span className="ml-1 text-blue-600 font-bold">({pctFilled}%)</span>
          </span>
        </div>
        <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-700',
              pctFilled >= 80 ? 'bg-green-500'
              : pctFilled >= 50 ? 'bg-blue-500'
              : 'bg-amber-400',
            )}
            style={{ width: `${pctFilled}%` }}
          />
        </div>

        {/* Tier breakdown */}
        {summary && (
          <div className="flex flex-wrap gap-2 mt-1">
            {[
              { tier: 1 as const, count: summary.tier_1_count, band: '1 deal / 200–700' },
              { tier: 2 as const, count: summary.tier_2_count, band: '1 deal / 500–1,200' },
              { tier: 3 as const, count: summary.tier_3_count, band: '1 deal / 2k–4k' },
            ].map(({ tier, count, band }) => (
              <div key={tier} className="flex items-center gap-1.5 text-xs text-gray-500">
                <TierBadge tier={tier} />
                <span className="font-medium text-gray-700">{count.toLocaleString()}</span>
                <span className="text-gray-400">({band})</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Stack analytics table */}
      <div>
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-gray-400" />
            <span className="text-sm font-medium text-gray-700">Deals by List Stack</span>
          </div>
          {stacks.length > 0 && (
            <button
              onClick={() => {
                const date = new Date().toISOString().slice(0, 10);
                const rows = stacks.map((s) => ({
                  stack_name: s.stack_name,
                  total_leads: s.total_leads,
                  tier_1_leads: s.tier_1_leads,
                  converted_leads: s.converted_leads,
                  conversion_pct: s.conversion_pct,
                  avg_assignment_fee: s.avg_assignment_fee ?? '',
                  avg_seller_score: s.avg_seller_score ?? '',
                }));
                const keys = Object.keys(rows[0]);
                const escape = (v: unknown) => { const s = v == null ? '' : String(v); return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s; };
                const csv = [keys.join(','), ...rows.map((r) => keys.map((k) => escape(r[k as keyof typeof r])).join(','))].join('\n');
                const a = document.createElement('a');
                a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
                a.download = `stack-analytics-${date}.csv`;
                a.click();
                URL.revokeObjectURL(a.href);
              }}
              className="flex items-center gap-1.5 px-2.5 py-1 border border-gray-200 rounded-lg text-xs text-gray-500 hover:bg-gray-50 transition-colors"
            >
              <Download className="h-3 w-3" />
              CSV
            </button>
          )}
        </div>

        {stacksLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 bg-gray-100 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : stacks.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">
            No stack data yet — import and score leads to see analytics.
          </p>
        ) : (
          <div className="space-y-1.5">
            {stacks.map((row) => {
              const convPct = row.conversion_pct ?? 0;
              return (
                <div
                  key={row.stack_name}
                  className="p-2.5 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  {/* Row 1: name + deal count */}
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-gray-800 truncate">
                      {row.stack_name}
                    </p>
                    <span className={cn(
                      'text-sm font-bold shrink-0',
                      row.converted_leads > 0 ? 'text-blue-700' : 'text-gray-400',
                    )}>
                      {row.converted_leads} {row.converted_leads === 1 ? 'deal' : 'deals'}
                    </span>
                  </div>

                  {/* Row 2: conversion bar spanning full width */}
                  <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden mt-1.5">
                    <div
                      className={cn(
                        'h-full rounded-full',
                        convPct > 1 ? 'bg-green-500'
                        : convPct > 0.5 ? 'bg-yellow-400'
                        : 'bg-gray-300',
                      )}
                      style={{ width: `${Math.min(100, convPct * 20)}%` }}
                    />
                  </div>

                  {/* Row 3: stats line — wraps cleanly instead of overflowing */}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1.5 text-xs text-gray-500">
                    <span>{row.total_leads.toLocaleString()} leads</span>
                    {row.tier_1_leads > 0 && (
                      <span className="text-red-600 font-semibold">{row.tier_1_leads} Tier 1</span>
                    )}
                    <span>{convPct.toFixed(1)}% conv.</span>
                    <span className="ml-auto">
                      {row.avg_assignment_fee ? (
                        <span className="text-green-700 font-semibold">{formatCurrency(row.avg_assignment_fee)} avg fee</span>
                      ) : (
                        <span className="text-gray-400">No deals yet</span>
                      )}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* PRD conversion benchmarks */}
      <div className="pt-3 border-t border-gray-100">
        <p className="text-xs font-semibold text-gray-500 mb-2">PRD Conversion Benchmarks</p>
        <div className="grid grid-cols-3 gap-2">
          {[
            { tier: '1', rate: '1 / 200–700',   color: 'text-red-600',    bg: 'bg-red-50',    border: 'border-red-100' },
            { tier: '2', rate: '1 / 500–1,200', color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-100' },
            { tier: '3', rate: '1 / 2k–4k',     color: 'text-gray-500',   bg: 'bg-gray-50',   border: 'border-gray-100' },
          ].map((b) => (
            <div key={b.tier} className={cn(
              'rounded-lg border p-2 text-center',
              b.bg, b.border,
            )}>
              <p className={cn('text-xs font-bold', b.color)}>Tier {b.tier}</p>
              <p className="text-xs text-gray-500 mt-0.5">{b.rate}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-2 flex items-center gap-1">
          <TrendingUp className="h-3 w-3" />
          Target: 2–6 contracts/mo from 2,000 prioritized leads · $10,000 avg fee
        </p>
      </div>
    </div>
  );
}
