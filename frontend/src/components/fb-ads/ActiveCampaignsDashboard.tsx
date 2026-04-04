import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, Pause, Plus, RefreshCw, Loader2 } from 'lucide-react';
import { cn, formatCurrency } from '@/lib/utils';
import { supabase } from '@/lib/supabase';

interface FbCampaign {
  id: string;
  name: string;
  status: 'draft' | 'active' | 'paused';
  daily_budget: number;
  battle_plan_score: number | null;
  wizard_step: number;
  created_at: string;
  updated_at: string;
}

interface Performance {
  campaign_id: string;
  total_spend: number;
  total_leads: number;
  avg_cpl: number;
  avg_contact_rate: number;
  avg_appt_rate: number;
}

interface Props {
  onNewCampaign: () => void;
  onEditCampaign: (id: string) => void;
}

export function ActiveCampaignsDashboard({ onNewCampaign, onEditCampaign }: Props) {
  const qc = useQueryClient();

  const { data: campaigns = [], isLoading } = useQuery<FbCampaign[]>({
    queryKey: ['fb_campaigns'],
    queryFn: async () => {
      const { data, error } = await supabase.from('fb_campaigns').select('*').order('created_at', { ascending: false });
      if (error) throw error;
      return data || [];
    },
    staleTime: 30000,
  });

  const { data: performances = [] } = useQuery<Performance[]>({
    queryKey: ['fb_campaign_performance_summary'],
    queryFn: async () => {
      const { data } = await supabase
        .from('fb_campaign_performance')
        .select('campaign_id, spend, leads, cpl, contact_rate, appt_rate');
      if (!data) return [];
      // Aggregate by campaign
      const map: Record<string, Performance> = {};
      for (const row of data) {
        if (!map[row.campaign_id]) {
          map[row.campaign_id] = { campaign_id: row.campaign_id, total_spend: 0, total_leads: 0, avg_cpl: 0, avg_contact_rate: 0, avg_appt_rate: 0 };
        }
        map[row.campaign_id].total_spend += row.spend || 0;
        map[row.campaign_id].total_leads += row.leads || 0;
      }
      return Object.values(map);
    },
    staleTime: 60000,
  });

  const toggleStatus = useMutation({
    mutationFn: async ({ id, current }: { id: string; current: string }) => {
      const newStatus = current === 'active' ? 'paused' : 'active';
      await supabase.from('fb_campaigns').update({ status: newStatus }).eq('id', id);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['fb_campaigns'] }),
  });

  const getPerf = (id: string) => performances.find(p => p.campaign_id === id);

  const STATUS_COLORS = {
    active: 'bg-green-100 text-green-700',
    paused: 'bg-yellow-100 text-yellow-700',
    draft: 'bg-gray-100 text-gray-600',
  };

  if (isLoading) {
    return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold text-gray-900">Active Campaigns</h2>
          <p className="text-xs text-gray-500">{campaigns.length} campaign{campaigns.length !== 1 ? 's' : ''} total</p>
        </div>
        <button
          onClick={onNewCampaign}
          className="flex items-center gap-1.5 px-3 py-2 bg-[#0A1628] text-white text-sm font-medium rounded-lg hover:bg-[#0a1628]/90 transition-colors"
        >
          <Plus className="h-4 w-4" /> New Campaign
        </button>
      </div>

      {campaigns.length === 0 ? (
        <div className="text-center py-12 text-gray-500 text-sm border border-dashed border-gray-200 rounded-xl">
          No campaigns yet. Click "New Campaign" to set up your first battle-plan campaign.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 border-b">
                <th className="text-left py-3 pr-4 font-medium">Campaign</th>
                <th className="text-left py-3 px-3 font-medium">Status</th>
                <th className="text-right py-3 px-3 font-medium">Budget/Day</th>
                <th className="text-right py-3 px-3 font-medium">Spend</th>
                <th className="text-right py-3 px-3 font-medium">Leads</th>
                <th className="text-right py-3 px-3 font-medium">CPL</th>
                <th className="text-right py-3 px-3 font-medium">Contact%</th>
                <th className="text-right py-3 px-3 font-medium">Appt%</th>
                <th className="text-right py-3 px-3 font-medium">BP Score</th>
                <th className="text-right py-3 pl-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map(campaign => {
                const perf = getPerf(campaign.id);
                const cpl = perf && perf.total_leads > 0
                  ? perf.total_spend / perf.total_leads
                  : null;

                return (
                  <tr key={campaign.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="py-3 pr-4">
                      <button
                        onClick={() => onEditCampaign(campaign.id)}
                        className="font-medium text-[#0A1628] hover:underline text-left max-w-[200px] truncate block"
                      >
                        {campaign.name}
                      </button>
                      <p className="text-xs text-gray-400">Step {campaign.wizard_step}/6 complete</p>
                    </td>
                    <td className="py-3 px-3">
                      <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', STATUS_COLORS[campaign.status])}>
                        {campaign.status}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-right text-gray-700">{formatCurrency(campaign.daily_budget, 0)}</td>
                    <td className="py-3 px-3 text-right text-gray-700">{perf ? formatCurrency(perf.total_spend, 0) : '—'}</td>
                    <td className="py-3 px-3 text-right text-gray-700">{perf?.total_leads || '—'}</td>
                    <td className={cn('py-3 px-3 text-right font-medium',
                      cpl == null ? 'text-gray-400' : cpl <= 30 ? 'text-green-600' : cpl <= 40 ? 'text-yellow-600' : 'text-red-600'
                    )}>
                      {cpl != null ? formatCurrency(cpl, 0) : '—'}
                    </td>
                    <td className={cn('py-3 px-3 text-right',
                      !perf?.avg_contact_rate ? 'text-gray-400' : perf.avg_contact_rate >= 40 ? 'text-green-600' : 'text-red-500'
                    )}>
                      {perf?.avg_contact_rate ? `${perf.avg_contact_rate.toFixed(0)}%` : '—'}
                    </td>
                    <td className="py-3 px-3 text-right text-gray-700">
                      {perf?.avg_appt_rate ? `${perf.avg_appt_rate.toFixed(0)}%` : '—'}
                    </td>
                    <td className="py-3 px-3 text-right">
                      {campaign.battle_plan_score != null ? (
                        <span className={cn('text-xs font-semibold',
                          campaign.battle_plan_score >= 80 ? 'text-green-600' :
                          campaign.battle_plan_score >= 60 ? 'text-yellow-600' : 'text-red-500'
                        )}>
                          {campaign.battle_plan_score.toFixed(0)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="py-3 pl-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => toggleStatus.mutate({ id: campaign.id, current: campaign.status })}
                          className={cn(
                            'p-1.5 rounded-lg transition-colors',
                            campaign.status === 'active'
                              ? 'text-yellow-600 hover:bg-yellow-50'
                              : 'text-green-600 hover:bg-green-50'
                          )}
                          title={campaign.status === 'active' ? 'Pause' : 'Activate'}
                        >
                          {campaign.status === 'active' ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                        </button>
                        <button
                          onClick={() => onEditCampaign(campaign.id)}
                          className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
                          title="Edit campaign"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
