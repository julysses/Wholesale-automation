import { useDeals } from '@/hooks/useDeals';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const STAGES = [
  'new', 'contacted', 'responding', 'offer_made',
  'under_contract', 'marketing_to_buyers', 'buyer_found', 'assigned', 'closed'
];

const COLORS = [
  '#94a3b8', '#60a5fa', '#818cf8', '#f59e0b',
  '#f97316', '#a855f7', '#eab308', '#14b8a6', '#22c55e'
];

const LABELS: Record<string, string> = {
  new: 'New',
  contacted: 'Contacted',
  responding: 'Responding',
  offer_made: 'Offer Made',
  under_contract: 'Under Contract',
  marketing_to_buyers: 'Marketing',
  buyer_found: 'Buyer Found',
  assigned: 'Assigned',
  closed: 'Closed',
};

export function PipelineChart() {
  const { data: leadCounts, error } = useQuery({
    queryKey: ['lead-stage-counts'],
    queryFn: async () => Object.fromEntries(await Promise.all(STAGES.map(async stage => {
      const { count, error } = await supabase.from('leads').select('id', { count: 'exact', head: true }).eq('status', stage);
      if (error) throw error;
      return [stage, count ?? 0];
    }))),
    staleTime: 60000,
  });
  const { data: deals, error: dealsError } = useDeals();
  const counts: Record<string, number> = Object.fromEntries(STAGES.map(stage => [stage, leadCounts?.[stage] ?? 0]));

  // Count deals by stage
  const dealStages = ['offer_made', 'under_contract', 'marketing_to_buyers', 'buyer_found', 'assigned', 'closed'];
  dealStages.forEach((s) => {
    const dealCount = (deals ?? []).filter((d) => d.stage === s).length;
    if (dealCount > 0) counts[s] = Math.max(counts[s], dealCount);
  });

  const chartData = STAGES.map((stage, i) => ({
    stage,
    name: LABELS[stage] || stage,
    count: counts[stage] || 0,
    color: COLORS[i],
  })).filter((d) => d.count > 0 || ['new', 'offer_made', 'closed'].includes(d.stage));

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h3 className="text-base font-semibold text-gray-900 mb-4">Pipeline by Stage</h3>
      {error || dealsError ? <p role="alert" className="text-sm text-red-700">Pipeline counts could not be loaded.</p> : <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 20, top: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 12 }} />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 12 }}
            width={110}
          />
          <Tooltip
            formatter={(value) => [value, 'Count']}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>}
    </div>
  );
}
