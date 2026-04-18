import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts';
import { TrendingUp, Flame, Thermometer, Wind, Minus } from 'lucide-react';
import { supabase } from '@/lib/supabase';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { MarketPulse } from '@/types';

// ── Data hooks ────────────────────────────────────────────────────────────────

function useLatestPulse() {
  return useQuery<MarketPulse[]>({
    queryKey: ['market_pulse_latest'],
    queryFn: async () => {
      // Get latest fetched_at timestamp, then pull all rows for that batch
      const { data: latest } = await supabase
        .from('market_pulse')
        .select('fetched_at')
        .order('fetched_at', { ascending: false })
        .limit(1)
        .maybeSingle();

      if (!latest) return [];

      const { data, error } = await supabase
        .from('market_pulse')
        .select('*')
        .gte('fetched_at', latest.fetched_at)
        .order('zip_code');

      if (error) throw error;
      return (data ?? []) as MarketPulse[];
    },
    staleTime: 10 * 60 * 1000,
  });
}

function usePpsfTrend() {
  return useQuery<{ zip_code: string; median_ppsf: number; fetched_at: string }[]>({
    queryKey: ['market_pulse_ppsf_trend'],
    queryFn: async () => {
      // Last 12 records per zip (each row is ~1 week)
      const { data, error } = await supabase
        .from('market_pulse')
        .select('zip_code, median_ppsf, fetched_at')
        .order('fetched_at', { ascending: true })
        .limit(200);

      if (error) throw error;
      return data ?? [];
    },
    staleTime: 10 * 60 * 1000,
  });
}

function useWeeklyFocus() {
  return useQuery<string | null>({
    queryKey: ['weekly_market_focus'],
    queryFn: async () => {
      const { data } = await supabase
        .from('app_notifications')
        .select('content')
        .eq('type', 'weekly_market_focus')
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      return data?.content ?? null;
    },
    staleTime: 10 * 60 * 1000,
  });
}

// ── Market temp config ────────────────────────────────────────────────────────

type MarketTemp = 'hot' | 'warm' | 'neutral' | 'cool';

const TEMP_CONFIG: Record<MarketTemp, { label: string; bg: string; text: string; border: string; icon: React.ElementType }> = {
  hot:     { label: 'HOT',     bg: 'bg-red-50',    text: 'text-red-700',   border: 'border-red-200',   icon: Flame },
  warm:    { label: 'WARM',    bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-200', icon: Thermometer },
  neutral: { label: 'NEUTRAL', bg: 'bg-blue-50',   text: 'text-blue-700',  border: 'border-blue-200',  icon: Minus },
  cool:    { label: 'COOL',    bg: 'bg-gray-50',   text: 'text-gray-600',  border: 'border-gray-200',  icon: Wind },
};

const TEMP_BAR_COLOR: Record<MarketTemp, string> = {
  hot:     '#ef4444',
  warm:    '#f97316',
  neutral: '#3b82f6',
  cool:    '#9ca3af',
};

function TempCard({ row }: { row: MarketPulse }) {
  const temp  = (row.market_temp ?? 'neutral') as MarketTemp;
  const cfg   = TEMP_CONFIG[temp] ?? TEMP_CONFIG.neutral;
  const Icon  = cfg.icon;

  return (
    <div className={cn('rounded-xl border p-4 space-y-2', cfg.bg, cfg.border)}>
      <div className="flex items-center justify-between">
        <p className="text-lg font-bold text-gray-900">{row.zip_code}</p>
        <span className={cn('flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded', cfg.text)}>
          <Icon className="h-3 w-3" />
          {cfg.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
        <span>Median: <strong className="text-gray-900">{row.median_list_price ? `$${Math.round(row.median_list_price / 1000)}k` : '—'}</strong></span>
        <span>PPSF: <strong className="text-gray-900">{row.median_ppsf ? `$${Math.round(row.median_ppsf)}` : '—'}</strong></span>
        <span>Avg DOM: <strong className="text-gray-900">{row.avg_dom ?? '—'} days</strong></span>
        <span>Price cuts: <strong className="text-gray-900">{row.price_cut_pct != null ? `${row.price_cut_pct.toFixed(0)}%` : '—'}</strong></span>
      </div>
    </div>
  );
}

// ── PPSF trend chart ──────────────────────────────────────────────────────────

const LINE_COLORS = ['#1B3A5C', '#E8720C', '#22c55e', '#a855f7', '#3b82f6', '#f59e0b', '#14b8a6', '#ec4899'];

function PpsfTrendChart({ rows }: { rows: { zip_code: string; median_ppsf: number; fetched_at: string }[] }) {
  // Group by week, pivot by zip
  const weekMap = new Map<string, Record<string, number>>();
  rows.forEach(({ zip_code, median_ppsf, fetched_at }) => {
    const week = new Date(fetched_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (!weekMap.has(week)) weekMap.set(week, { week });
    weekMap.get(week)![zip_code] = median_ppsf;
  });

  const chartData = Array.from(weekMap.values());
  const zips = [...new Set(rows.map((r) => r.zip_code))].slice(0, 8);

  if (chartData.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">No trend data yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="week" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} width={50} />
        <Tooltip
          formatter={(v: number) => [`$${v}/sqft`]}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {zips.map((zip, i) => (
          <Line
            key={zip}
            type="monotone"
            dataKey={zip}
            stroke={LINE_COLORS[i % LINE_COLORS.length]}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── DOM bar chart ─────────────────────────────────────────────────────────────

function DomChart({ rows }: { rows: MarketPulse[] }) {
  const chartData = rows
    .filter((r) => r.avg_dom != null)
    .map((r) => ({
      zip:  r.zip_code,
      dom:  r.avg_dom!,
      temp: (r.market_temp ?? 'neutral') as MarketTemp,
    }));

  if (chartData.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">No DOM data yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="zip" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} unit=" days" width={56} />
        <Tooltip
          formatter={(v: number) => [`${v} days`, 'Avg DOM']}
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
        />
        <Bar dataKey="dom" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, i) => (
            <Cell key={i} fill={TEMP_BAR_COLOR[entry.temp]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Price cut alert list ──────────────────────────────────────────────────────

function PriceCutList({ rows }: { rows: MarketPulse[] }) {
  const sorted = [...rows]
    .filter((r) => r.price_cut_pct != null)
    .sort((a, b) => (b.price_cut_pct ?? 0) - (a.price_cut_pct ?? 0));

  if (sorted.length === 0) {
    return <p className="text-sm text-gray-400">No data yet.</p>;
  }

  return (
    <div className="space-y-2">
      {sorted.map((r) => {
        const pct  = r.price_cut_pct ?? 0;
        const temp = (r.market_temp ?? 'neutral') as MarketTemp;
        const cfg  = TEMP_CONFIG[temp];
        return (
          <div key={r.zip_code} className="flex items-center gap-3">
            <span className="text-sm font-semibold text-gray-900 w-14">{r.zip_code}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-2">
              <div
                className={cn('h-2 rounded-full', pct > 30 ? 'bg-gray-400' : pct > 20 ? 'bg-blue-400' : pct > 10 ? 'bg-orange-400' : 'bg-red-500')}
                style={{ width: `${Math.min(100, pct * 2)}%` }}
              />
            </div>
            <span className={cn('text-xs font-bold w-10 text-right', cfg.text)}>{pct.toFixed(0)}%</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MarketPulsePage() {
  const { data: pulse = [], isLoading: pulseLoading } = useLatestPulse();
  const { data: trendRows = [] }                       = usePpsfTrend();
  const { data: focusText }                            = useWeeklyFocus();

  const tempCounts = pulse.reduce<Record<string, number>>((acc, r) => {
    const t = r.market_temp ?? 'neutral';
    acc[t] = (acc[t] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <TrendingUp className="h-6 w-6 text-[#E8720C]" />
            DFW Market Pulse
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Weekly zip-level intelligence — updated every Sunday 6AM CST
          </p>
        </div>
        {pulse.length > 0 && (
          <div className="flex items-center gap-3 text-sm">
            {(['hot', 'warm', 'neutral', 'cool'] as MarketTemp[]).map((t) => {
              const cfg = TEMP_CONFIG[t];
              const cnt = tempCounts[t] ?? 0;
              if (!cnt) return null;
              return (
                <span key={t} className={cn('px-2 py-1 rounded border text-xs font-medium', cfg.bg, cfg.text, cfg.border)}>
                  {cnt} {cfg.label}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {/* Weekly Acquisition Focus */}
      {focusText && (
        <Card className="border-[#E8720C]/30 bg-orange-50/50">
          <CardHeader>
            <CardTitle className="text-[#E8720C] text-sm flex items-center gap-2">
              <Flame className="h-4 w-4" />
              Weekly Acquisition Focus — Claude AI Advisory
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">{focusText}</p>
          </CardContent>
        </Card>
      )}

      {/* Zip Heat Map */}
      <div>
        <h2 className="text-base font-semibold text-gray-800 mb-3">Zip Market Temperature</h2>
        {pulseLoading ? (
          <p className="text-sm text-gray-400">Loading market data…</p>
        ) : pulse.length === 0 ? (
          <Card>
            <CardContent>
              <p className="text-sm text-gray-400 py-4 text-center">
                No market data yet. The scan runs every Sunday at 6AM CST, or you can invoke the
                <code className="mx-1 px-1 bg-gray-100 rounded text-xs">market-pulse</code>
                edge function manually.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {pulse.map((row) => <TempCard key={row.id} row={row} />)}
          </div>
        )}
      </div>

      {/* Charts row */}
      {pulse.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* PPSF Trend */}
          <Card>
            <CardHeader>
              <CardTitle>PPSF Trend by Zip (12 weeks)</CardTitle>
            </CardHeader>
            <CardContent>
              <PpsfTrendChart rows={trendRows} />
            </CardContent>
          </Card>

          {/* DOM Tracker */}
          <Card>
            <CardHeader>
              <CardTitle>Avg Days on Market by Zip</CardTitle>
            </CardHeader>
            <CardContent>
              <DomChart rows={pulse} />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Price Cut Alert */}
      {pulse.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Price Cut Alert — Zips Ranked by % Listings with Price Cuts</CardTitle>
          </CardHeader>
          <CardContent>
            <PriceCutList rows={pulse} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
