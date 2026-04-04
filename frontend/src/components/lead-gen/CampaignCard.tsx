import { useState } from 'react';
import { Play, Pause, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AdCampaign } from '@/types';

interface CampaignCardProps {
  campaign: AdCampaign;
  onToggleStatus: (id: string, newStatus: string) => void;
  onSyncFacebook?: (id: string) => void;
  onSelect?: (id: string) => void;
  selected?: boolean;
  syncing?: boolean;
}

const PLATFORM_LABELS: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  google: 'Google',
  tiktok: 'TikTok',
};

const PLATFORM_COLORS: Record<string, string> = {
  facebook: 'bg-blue-100 text-blue-700',
  instagram: 'bg-pink-100 text-pink-700',
  google: 'bg-green-100 text-green-700',
  tiktok: 'bg-gray-100 text-gray-700',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  paused: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-gray-100 text-gray-600',
  draft: 'bg-purple-100 text-purple-700',
};

export function CampaignCard({
  campaign,
  onToggleStatus,
  onSyncFacebook,
  onSelect,
  selected = false,
  syncing = false,
}: CampaignCardProps) {
  const cpl = campaign.cpl ?? (
    campaign.leads_count > 0 ? campaign.total_spend / campaign.leads_count : null
  );
  const ctr = campaign.impressions > 0 ? (campaign.clicks / campaign.impressions) * 100 : null;

  const cplColor = cpl == null ? 'text-gray-500' : cpl <= 50 ? 'text-green-600' : cpl <= 80 ? 'text-yellow-600' : 'text-red-600';

  return (
    <div
      className={cn(
        'bg-white border rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow cursor-pointer',
        selected && 'border-[#1B3A5C] ring-2 ring-[#1B3A5C]/20'
      )}
      onClick={() => onSelect?.(campaign.id)}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">{campaign.name}</h3>
          <div className="flex items-center gap-2 mt-1">
            <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', PLATFORM_COLORS[campaign.platform] || 'bg-gray-100 text-gray-600')}>
              {PLATFORM_LABELS[campaign.platform] || campaign.platform}
            </span>
            <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', STATUS_COLORS[campaign.status] || 'bg-gray-100 text-gray-600')}>
              {campaign.status}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 ml-2">
          {campaign.external_campaign_id && onSyncFacebook && (
            <button
              onClick={(e) => { e.stopPropagation(); onSyncFacebook(campaign.id); }}
              disabled={syncing}
              className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-[#1B3A5C] transition-colors"
              title="Sync from Facebook"
            >
              <RefreshCw className={cn('h-4 w-4', syncing && 'animate-spin')} />
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleStatus(campaign.id, campaign.status === 'active' ? 'paused' : 'active');
            }}
            className={cn(
              'p-1.5 rounded-lg transition-colors',
              campaign.status === 'active'
                ? 'text-yellow-600 hover:bg-yellow-50'
                : 'text-green-600 hover:bg-green-50'
            )}
            title={campaign.status === 'active' ? 'Pause campaign' : 'Activate campaign'}
          >
            {campaign.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Total Spend" value={`$${campaign.total_spend.toLocaleString('en-US', { minimumFractionDigits: 0 })}`} />
        <Stat label="Leads" value={campaign.leads_count.toString()} />
        <Stat
          label="CPL"
          value={cpl != null ? `$${cpl.toFixed(0)}` : '—'}
          valueClass={cplColor}
        />
        <Stat
          label="Avg Quality"
          value={campaign.avg_lead_quality_score != null ? `${campaign.avg_lead_quality_score.toFixed(0)}` : '—'}
          valueClass={
            campaign.avg_lead_quality_score == null ? 'text-gray-500'
              : campaign.avg_lead_quality_score >= 70 ? 'text-green-600'
              : campaign.avg_lead_quality_score >= 50 ? 'text-yellow-600'
              : 'text-red-600'
          }
        />
        <Stat
          label="Impressions"
          value={campaign.impressions > 0 ? campaign.impressions.toLocaleString() : '—'}
        />
        <Stat
          label="CTR"
          value={ctr != null ? `${ctr.toFixed(2)}%` : '—'}
        />
      </div>

      {/* Daily budget */}
      {campaign.daily_budget != null && (
        <div className="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
          Daily budget: <span className="font-medium text-gray-700">${campaign.daily_budget.toLocaleString()}/day</span>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, valueClass = 'text-gray-900' }: { label: string; value: string; valueClass?: string }) {
  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className={cn('text-sm font-semibold', valueClass)}>{value}</p>
    </div>
  );
}
