import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { AlertTriangle, Info, Loader2, RefreshCw } from 'lucide-react';
import { supabase } from '@/lib/supabase';
import { cn, formatCurrency } from '@/lib/utils';
import { claudeAdvisor, type PerformanceAlert } from '@/lib/fb-ads/claudeAdvisor';
import { KPI_THRESHOLDS } from '@/lib/fb-ads/battlePlanRules';

const SEGMENT_COLORS = ['#0A1628', '#F5A623', '#2E6DA4', '#22C55E', '#A855F7', '#F43F5E', '#0EA5E9'];

export function PerformanceTracker() {
  const [alerts, setAlerts] = useState<PerformanceAlert[]>([]);
  const [loadingAlerts, setLoadingAlerts] = useState(false);

  const { data: perfData = [] } = useQuery({
    queryKey: ['fb_perf_all'],
    queryFn: async () => {
      const { data } = await supabase
        .from('fb_campaign_performance')
        .select('*, fb_campaigns(name), fb_ad_sets(segment)')
        .order('date', { ascending: true });
      return data || [];
    },
    staleTime: 60000,
  });

  const { data: fbLeads = [] } = useQuery({
    queryKey: ['fb_leads_all'],
    queryFn: async () => {
      const { data } = await supabase.from('fb_leads').select('situations, segment_tag, received_at');
      return data || [];
    },
    staleTime: 60000,
  });

  // KPI aggregates
  const totalSpend = perfData.reduce((s: number, r: any) => s + (r.spend || 0), 0);
  const totalLeads = perfData.reduce((s: number, r: any) => s + (r.leads || 0), 0);
  const blendedCpl = totalLeads > 0 ? totalSpend / totalLeads : 0;
  const avgContactRate = perfData.length > 0
    ? perfData.reduce((s: number, r: any) => s + (r.contact_rate || 0), 0) / perfData.length
    : 0;
  const avgApptRate = perfData.length > 0
    ? perfData.reduce((s: number, r: any) => s + (r.appt_rate || 0), 0) / perfData.length
    : 0;

  // CPL by segment (bar chart)
  const cplBySegment = (() => {
    const map: Record<string, { spend: number; leads: number }> = {};
    perfData.forEach((r: any) => {
      const seg = r.fb_ad_sets?.segment || 'unknown';
      if (!map[seg]) map[seg] = { spend: 0, leads: 0 };
      map[seg].spend += r.spend || 0;
      map[seg].leads += r.leads || 0;
    });
    return Object.entries(map).map(([seg, { spend, leads }]) => ({
      segment: seg.replace('-', '\n'),
      cpl: leads > 0 ? Math.round(spend / leads) : 0,
    }));
  })();

  // Lead volume by day (line chart)
  const leadsByDay = (() => {
    const map: Record<string, { date: string; leads: number; spend: number }> = {};
    perfData.forEach((r: any) => {
      const d = r.date;
      if (!map[d]) map[d] = { date: d, leads: 0, spend: 0 };
      map[d].leads += r.leads || 0;
      map[d].spend += r.spend || 0;
    });
    return Object.values(map).slice(-30);
  })();

  // Situation tag distribution (pie chart)
  const situationDist = (() => {
    const map: Record<string, number> = {};
    fbLeads.forEach((l: any) => {
      (l.situations || []).forEach((s: string) => {
        map[s] = (map[s] || 0) + 1;
      });
    });
    return Object.entries(map).map(([name, value]) => ({ name, value }));
  })();

  const runAlerts = async () => {
    setLoadingAlerts(true);
    try {
      const result = await claudeAdvisor.analyzePerformance(perfData);
      setAlerts(result);
    } catch {
      setAlerts([]);
    } finally {
      setLoadingAlerts(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPIStat label="Total Spend" value={formatCurrency(totalSpend, 0)} />
        <KPIStat label="Total Leads" value={totalLeads.toString()} />
        <KPIStat
          label="Blended CPL"
          value={blendedCpl > 0 ? formatCurrency(blendedCpl, 0) : '—'}
          alert={blendedCpl > KPI_THRESHOLDS.CPL_WARNING}
        />
        <KPIStat
          label="Contact Rate"
          value={avgContactRate > 0 ? `${avgContactRate.toFixed(0)}%` : '—'}
          alert={avgContactRate > 0 && avgContactRate < KPI_THRESHOLDS.CONTACT_RATE_MIN}
        />
        <KPIStat label="Appt Rate" value={avgApptRate > 0 ? `${avgApptRate.toFixed(0)}%` : '—'} />
      </div>

      {perfData.length === 0 ? (
        <div className="text-center py-12 text-gray-500 text-sm border border-dashed border-gray-200 rounded-xl">
          No performance data yet. Add daily snapshots to fb_campaign_performance to see analytics.
        </div>
      ) : (
        <>
          {/* Chart grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* CPL by Segment */}
            <ChartCard title="CPL by Segment">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={cplBySegment}>
                  <XAxis dataKey="segment" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => `$${v}`} />
                  <Bar dataKey="cpl" fill="#0A1628" radius={[4, 4, 0, 0]}>
                    {cplBySegment.map((_, i) => (
                      <Cell key={i} fill={SEGMENT_COLORS[i % SEGMENT_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Lead Volume by Day */}
            <ChartCard title="Lead Volume by Day">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={leadsByDay}>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="leads" stroke="#0A1628" strokeWidth={2} dot={false} name="Leads" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Situation Tag Distribution */}
            <ChartCard title="Situation Tag Distribution">
              {situationDist.length === 0 ? (
                <p className="text-sm text-gray-400 py-8 text-center">No situation data yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={situationDist} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                      {situationDist.map((_, i) => <Cell key={i} fill={SEGMENT_COLORS[i % SEGMENT_COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            {/* Budget vs Lead Volume */}
            <ChartCard title="Budget vs Lead Volume">
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={leadsByDay}>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line yAxisId="left" type="monotone" dataKey="leads" stroke="#0A1628" strokeWidth={2} dot={false} name="Leads" />
                  <Line yAxisId="right" type="monotone" dataKey="spend" stroke="#F5A623" strokeWidth={2} dot={false} name="Spend ($)" />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </>
      )}

      {/* Claude Alert Panel */}
      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="bg-[#0A1628] px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-semibold text-white">✦ Claude Optimization Alerts</span>
          <button
            onClick={runAlerts}
            disabled={loadingAlerts}
            className="flex items-center gap-1.5 text-xs text-white/80 hover:text-white transition-colors"
          >
            {loadingAlerts ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            {loadingAlerts ? 'Analyzing…' : 'Analyze Now'}
          </button>
        </div>
        <div className="p-4 space-y-3">
          {alerts.length === 0 && !loadingAlerts && (
            <p className="text-sm text-gray-500">
              Click "Analyze Now" to get Claude's optimization recommendations based on the last 7 days of performance data.
            </p>
          )}
          {alerts.map((alert, i) => (
            <AlertBanner key={i} alert={alert} />
          ))}
        </div>
      </div>
    </div>
  );
}

function KPIStat({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div className={cn('border rounded-xl p-4', alert ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white')}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={cn('text-xl font-bold mt-1', alert ? 'text-red-600' : 'text-gray-900')}>{value}</p>
      {alert && <p className="text-xs text-red-500 mt-0.5">⚠ Below target</p>}
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-800 mb-3">{title}</h3>
      {children}
    </div>
  );
}

function AlertBanner({ alert }: { alert: PerformanceAlert }) {
  const styles = {
    urgent: 'bg-red-50 border-red-200 text-red-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
    info: 'bg-blue-50 border-blue-200 text-blue-800',
  };
  const Icon = alert.type === 'urgent' ? AlertTriangle : alert.type === 'warning' ? AlertTriangle : Info;
  return (
    <div className={cn('border rounded-lg p-3', styles[alert.type])}>
      <div className="flex items-start gap-2">
        <Icon className="h-4 w-4 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium">{alert.ad_set} — {alert.message}</p>
          <p className="text-xs mt-1 opacity-80">{alert.recommendation}</p>
        </div>
      </div>
    </div>
  );
}
