import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatCurrency } from '@/lib/utils';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line
} from 'recharts';
import { cn } from '@/lib/utils';

const COLORS = ['#1B3A5C', '#E8720C', '#2E6DA4', '#22c55e', '#f59e0b', '#a855f7', '#ec4899', '#14b8a6'];

const DATE_RANGES = [
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: 'mtd', label: 'This month' },
  { value: 'ytd', label: 'This year' },
];

function getDateRange(range: string): [string, string] {
  const now = new Date();
  const end = now.toISOString();
  if (range === '30') {
    return [new Date(Date.now() - 30 * 86400000).toISOString(), end];
  }
  if (range === '90') {
    return [new Date(Date.now() - 90 * 86400000).toISOString(), end];
  }
  if (range === 'mtd') {
    return [new Date(now.getFullYear(), now.getMonth(), 1).toISOString(), end];
  }
  if (range === 'ytd') {
    return [new Date(now.getFullYear(), 0, 1).toISOString(), end];
  }
  return [new Date(Date.now() - 30 * 86400000).toISOString(), end];
}

export function Reports() {
  const [range, setRange] = useState('mtd');
  const [dateFrom, dateTo] = getDateRange(range);

  // Deals data
  const { data: dealsData } = useQuery({
    queryKey: ['reports', 'deals', range],
    queryFn: async () => {
      const { data } = await supabase
        .from('deals')
        .select('*')
        .gte('created_at', dateFrom)
        .lte('created_at', dateTo);
      return data || [];
    },
    staleTime: 60000,
  });

  // Leads data
  const { data: leadsData } = useQuery({
    queryKey: ['reports', 'leads', range],
    queryFn: async () => {
      const { data } = await supabase
        .from('leads')
        .select('*')
        .gte('created_at', dateFrom)
        .lte('created_at', dateTo);
      return data || [];
    },
    staleTime: 60000,
  });

  // Buyers data
  const { data: buyersData } = useQuery({
    queryKey: ['reports', 'buyers'],
    queryFn: async () => {
      const { data } = await supabase.from('buyers').select('*');
      return data || [];
    },
    staleTime: 60000,
  });

  const deals = dealsData || [];
  const leads = leadsData || [];
  const buyers = buyersData || [];

  // Deal performance
  const closedDeals = deals.filter((d: any) => d.stage === 'closed');
  const totalFees = closedDeals.reduce((s: number, d: any) => s + (d.assignment_fee || 0), 0);
  const avgFee = closedDeals.length > 0 ? totalFees / closedDeals.length : 0;
  const avgDaysToClose = closedDeals.length > 0
    ? closedDeals.reduce((s: number, d: any) => {
        if (!d.contract_date || !d.actual_close_date) return s;
        return s + Math.max(0, (new Date(d.actual_close_date).getTime() - new Date(d.contract_date).getTime()) / 86400000);
      }, 0) / closedDeals.length
    : 0;

  // Monthly deals chart (last 6 months)
  const monthlyDeals = Array.from({ length: 6 }, (_, i) => {
    const d = new Date();
    d.setMonth(d.getMonth() - (5 - i));
    const month = d.toLocaleString('en-US', { month: 'short' });
    const year = d.getFullYear();
    const monthStart = new Date(year, d.getMonth(), 1).toISOString();
    const monthEnd = new Date(year, d.getMonth() + 1, 0).toISOString();
    const count = closedDeals.filter((deal: any) =>
      deal.actual_close_date >= monthStart && deal.actual_close_date <= monthEnd
    ).length;
    const fees = closedDeals
      .filter((deal: any) => deal.actual_close_date >= monthStart && deal.actual_close_date <= monthEnd)
      .reduce((s: number, d: any) => s + (d.assignment_fee || 0), 0);
    return { month, count, fees };
  });

  // Lead sources donut
  const sourceCount: Record<string, number> = {};
  leads.forEach((l: any) => {
    const src = l.source || 'unknown';
    sourceCount[src] = (sourceCount[src] || 0) + 1;
  });
  const sourceData = Object.entries(sourceCount).map(([name, value]) => ({
    name: name.replace(/_/g, ' '),
    value,
  })).sort((a, b) => b.value - a.value);

  // Funnel conversion
  const funnelStages = [
    { label: 'Total Leads', count: leads.length },
    { label: 'Qualified', count: leads.filter((l: any) => ['qualified_hot', 'qualified_warm', 'qualified_cold'].includes(l.status)).length },
    { label: 'Offer Made', count: leads.filter((l: any) => l.status === 'offer_made').length + deals.filter((d: any) => d.stage === 'offer_made').length },
    { label: 'Under Contract', count: deals.filter((d: any) => !['cancelled'].includes(d.stage)).length },
    { label: 'Closed', count: closedDeals.length },
  ];

  // Pipeline health
  const stageDeals: Record<string, number> = {};
  deals.forEach((d: any) => {
    if (!['closed', 'cancelled'].includes(d.stage)) {
      stageDeals[d.stage] = (stageDeals[d.stage] || 0) + 1;
    }
  });
  const pipelineStageData = Object.entries(stageDeals).map(([stage, count]) => ({
    stage: stage.replace(/_/g, ' '),
    count,
  }));
  const atRisk = deals.filter((d: any) => {
    if (!d.closing_date || ['closed', 'cancelled', 'buyer_found', 'assigned'].includes(d.stage)) return false;
    const days = Math.ceil((new Date(d.closing_date).getTime() - Date.now()) / 86400000);
    return days <= 7;
  }).length;

  // Buyers
  const tierCount = { A: 0, B: 0, C: 0 };
  buyers.forEach((b: any) => { if (tierCount[b.tier as keyof typeof tierCount] !== undefined) tierCount[b.tier as keyof typeof tierCount]++; });
  const tierData = [
    { name: 'Tier A', value: tierCount.A },
    { name: 'Tier B', value: tierCount.B },
    { name: 'Tier C', value: tierCount.C },
  ];
  const topBuyers = [...buyers]
    .sort((a: any, b: any) => b.deals_closed - a.deals_closed)
    .slice(0, 5);
  const strategyCount: Record<string, number> = {};
  buyers.forEach((b: any) => {
    (b.strategy || []).forEach((s: string) => {
      strategyCount[s] = (strategyCount[s] || 0) + 1;
    });
  });
  const topStrategy = Object.entries(strategyCount).sort((a, b) => b[1] - a[1])[0];

  const StatCard = ({ title, value, sub }: { title: string; value: string | number; sub?: string }) => (
    <div className="bg-gray-50 rounded-lg p-4 text-center">
      <p className="text-2xl font-bold text-[#1B3A5C]">{value}</p>
      <p className="text-xs text-gray-500 font-medium mt-0.5">{title}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
          <p className="text-sm text-gray-500 mt-0.5">Performance analytics and insights</p>
        </div>
        <div className="flex gap-1 bg-white border border-gray-200 rounded-lg p-1">
          {DATE_RANGES.map((r) => (
            <button
              key={r.value}
              onClick={() => setRange(r.value)}
              className={cn(
                'px-3 py-1.5 text-xs rounded-md font-medium transition-colors',
                range === r.value
                  ? 'bg-[#1B3A5C] text-white'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Deal Performance */}
        <Card>
          <CardHeader><CardTitle>Deal Performance</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <StatCard title="Deals Closed" value={closedDeals.length} />
              <StatCard title="Total Fees" value={formatCurrency(totalFees)} />
              <StatCard title="Avg Fee" value={formatCurrency(avgFee)} />
              <StatCard title="Avg Days to Close" value={avgDaysToClose > 0 ? `${Math.round(avgDaysToClose)}d` : '—'} />
            </div>
            <div className="h-44">
              <p className="text-xs font-medium text-gray-500 mb-2">Deals Closed by Month</p>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyDeals}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#1B3A5C" radius={[4, 4, 0, 0]} name="Deals" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Lead Funnel */}
        <Card>
          <CardHeader><CardTitle>Lead Funnel</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="h-52">
              <p className="text-xs font-medium text-gray-500 mb-2">Leads by Source</p>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sourceData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {sourceData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-500">Conversion Funnel</p>
              {funnelStages.map((stage, i) => (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-xs text-gray-600 w-32 shrink-0">{stage.label}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-2">
                    <div
                      className="h-2 rounded-full bg-[#1B3A5C]"
                      style={{ width: funnelStages[0].count > 0 ? `${(stage.count / funnelStages[0].count) * 100}%` : '0%' }}
                    />
                  </div>
                  <span className="text-xs font-semibold text-gray-900 w-8 text-right">{stage.count}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Pipeline Health */}
        <Card>
          <CardHeader><CardTitle>Pipeline Health</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <StatCard title="Active Deals" value={Object.values(stageDeals).reduce((s, c) => s + c, 0)} />
              <StatCard title="Pipeline Value"
                value={formatCurrency(deals.filter((d: any) => !['closed', 'cancelled'].includes(d.stage))
                  .reduce((s: number, d: any) => s + (d.assignment_fee || 0), 0))} />
              <StatCard title="At Risk" value={atRisk} sub="Closing in < 7d, no buyer" />
            </div>
            {pipelineStageData.length > 0 && (
              <div className="h-44">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={pipelineStageData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="stage" tick={{ fontSize: 11 }} width={110} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#E8720C" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Buyer Activity */}
        <Card>
          <CardHeader><CardTitle>Buyer Activity</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <StatCard title="Total Buyers" value={buyers.length} />
              <StatCard title="Tier A" value={tierCount.A} sub="Closed with us" />
              <StatCard title="Top Strategy"
                value={topStrategy?.[0]?.replace(/_/g, '/').toUpperCase() || '—'} />
            </div>

            {/* Tier chart */}
            <div className="flex justify-center" style={{ height: 120 }}>
              <ResponsiveContainer width="50%" height="100%">
                <PieChart>
                  <Pie data={tierData} cx="50%" cy="50%" outerRadius={50} dataKey="value" label={({ name }) => name}>
                    {tierData.map((_, i) => (
                      <Cell key={i} fill={['#f59e0b', '#2E6DA4', '#94a3b8'][i]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Top buyers */}
            {topBuyers.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-2">Top Buyers by Deals Closed</p>
                <div className="space-y-1.5">
                  {topBuyers.map((b: any, i: number) => (
                    <div key={b.id} className="flex items-center gap-3">
                      <span className="text-xs font-bold text-gray-400 w-4">#{i + 1}</span>
                      <span className="text-sm text-gray-800 flex-1">{b.first_name} {b.last_name}</span>
                      <span className="text-xs font-semibold text-green-600">{b.deals_closed} deals</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
