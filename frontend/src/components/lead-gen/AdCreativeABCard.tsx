import { Trophy, Pause, Play } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AdCreative } from '@/types';

interface AdCreativeABCardProps {
  creatives: AdCreative[];
  onToggleStatus: (id: string, newStatus: string) => void;
  onSetWinner: (id: string) => void;
}

const ANGLE_LABELS: Record<string, string> = {
  foreclosure: 'Foreclosure',
  divorce: 'Divorce',
  inherited: 'Inherited',
  tired_landlord: 'Tired Landlord',
  relocation: 'Relocation',
  repairs: 'Repairs',
  generic: 'Generic',
};

const ANGLE_COLORS: Record<string, string> = {
  foreclosure: 'bg-red-100 text-red-700',
  divorce: 'bg-orange-100 text-orange-700',
  inherited: 'bg-purple-100 text-purple-700',
  tired_landlord: 'bg-yellow-100 text-yellow-700',
  relocation: 'bg-blue-100 text-blue-700',
  repairs: 'bg-gray-100 text-gray-700',
  generic: 'bg-green-100 text-green-700',
};

export function AdCreativeABCard({ creatives, onToggleStatus, onSetWinner }: AdCreativeABCardProps) {
  if (creatives.length === 0) {
    return (
      <div className="border border-dashed border-gray-200 rounded-xl p-6 text-center text-gray-500 text-sm">
        No creatives yet. Add your first A/B variant above.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {creatives.map((creative) => (
        <CreativeCard
          key={creative.id}
          creative={creative}
          onToggleStatus={onToggleStatus}
          onSetWinner={onSetWinner}
        />
      ))}
    </div>
  );
}

function CreativeCard({
  creative,
  onToggleStatus,
  onSetWinner,
}: {
  creative: AdCreative;
  onToggleStatus: (id: string, status: string) => void;
  onSetWinner: (id: string) => void;
}) {
  const cpl = creative.cpl ?? (
    creative.leads_count > 0 ? creative.total_spend / creative.leads_count : null
  );
  const cplColor = cpl == null ? 'text-gray-500' : cpl <= 50 ? 'text-green-600' : cpl <= 80 ? 'text-yellow-600' : 'text-red-600';

  return (
    <div className={cn(
      'border rounded-xl p-4 relative',
      creative.is_winner ? 'border-amber-400 bg-amber-50' : 'border-gray-200 bg-white',
      creative.status === 'paused' && 'opacity-60'
    )}>
      {/* Winner badge */}
      {creative.is_winner && (
        <div className="absolute top-3 right-3 flex items-center gap-1 text-amber-600 text-xs font-semibold">
          <Trophy className="h-3.5 w-3.5" />
          Winner
        </div>
      )}

      {/* Header */}
      <div className="mb-3">
        <div className="flex items-center gap-2 mb-1">
          {creative.pain_point_angle && (
            <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', ANGLE_COLORS[creative.pain_point_angle] || 'bg-gray-100 text-gray-600')}>
              {ANGLE_LABELS[creative.pain_point_angle] || creative.pain_point_angle}
            </span>
          )}
          <span className={cn('text-xs px-2 py-0.5 rounded-full', creative.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500')}>
            {creative.status}
          </span>
        </div>
        <p className="text-xs text-gray-500 truncate">{creative.name}</p>
      </div>

      {/* Copy preview */}
      {creative.headline && (
        <p className="font-semibold text-gray-900 text-sm leading-snug mb-1">
          {creative.headline}
        </p>
      )}
      {creative.primary_text && (
        <p className="text-xs text-gray-600 leading-relaxed line-clamp-3 mb-3">
          {creative.primary_text}
        </p>
      )}
      {creative.cta_text && (
        <div className="inline-block bg-[#E8720C] text-white text-xs px-3 py-1 rounded-lg font-medium mb-3">
          {creative.cta_text}
        </div>
      )}

      {/* KPI Strip */}
      <div className="grid grid-cols-3 gap-2 py-2 border-t border-gray-100 text-center">
        <div>
          <p className="text-xs text-gray-500">Leads</p>
          <p className="text-sm font-semibold text-gray-900">{creative.leads_count}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500">CPL</p>
          <p className={cn('text-sm font-semibold', cplColor)}>
            {cpl != null ? `$${cpl.toFixed(0)}` : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Quality</p>
          <p className={cn('text-sm font-semibold',
            creative.avg_lead_quality_score == null ? 'text-gray-500'
              : creative.avg_lead_quality_score >= 70 ? 'text-green-600'
              : creative.avg_lead_quality_score >= 50 ? 'text-yellow-600'
              : 'text-red-600'
          )}>
            {creative.avg_lead_quality_score != null ? creative.avg_lead_quality_score.toFixed(0) : '—'}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-3">
        <button
          onClick={() => onToggleStatus(creative.id, creative.status === 'active' ? 'paused' : 'active')}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 text-xs rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
        >
          {creative.status === 'active' ? (
            <><Pause className="h-3 w-3" /> Pause</>
          ) : (
            <><Play className="h-3 w-3" /> Activate</>
          )}
        </button>
        {!creative.is_winner && (
          <button
            onClick={() => onSetWinner(creative.id)}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 text-xs rounded-lg border border-amber-300 text-amber-700 hover:bg-amber-50 transition-colors"
          >
            <Trophy className="h-3 w-3" /> Set Winner
          </button>
        )}
      </div>
    </div>
  );
}
