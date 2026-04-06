import { useState } from 'react';
import { AlertTriangle, CheckCircle, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  SEGMENT_HEADLINES, SEGMENT_LABELS, SEGMENT_COPY_A, SEGMENT_COPY_B, SEGMENT_COPY_C,
  validateHeadline, type Segment,
} from '@/lib/fb-ads/battlePlanRules';
import { BattlePlanCallout } from './Step1CampaignSettings';

interface AdSetConfig {
  segment: Segment;
  headline: string;
  copy_version_a: string;
  copy_version_b: string;
  copy_version_c: string;
  active_copy_version: 'A' | 'B' | 'C';
  placement_feed: boolean;
  placement_marketplace: boolean;
  placement_instagram: boolean;
  budget_allocation: number;
}

interface Step3State {
  ad_sets: AdSetConfig[];
  total_budget: number;
}

interface Props {
  state: Step3State;
  detectedSegments: Segment[];  // segments from Step 2 audiences
  onChange: (updates: Partial<Step3State>) => void;
  errors: Record<string, string>;
}

const DEFAULT_SEGMENTS: Segment[] = ['pre-foreclosure', 'probate', 'divorce'];

export function Step3AdSetConfigurator({ state, detectedSegments, onChange, errors }: Props) {
  const segments = detectedSegments.length > 0 ? detectedSegments : DEFAULT_SEGMENTS;
  const [headlineWarnings, setHeadlineWarnings] = useState<Record<string, string[]>>({});

  // Initialize ad sets for any segment not yet present
  const ensureAdSets = () => {
    const existing = new Set(state.ad_sets.map(a => a.segment));
    const toAdd = segments.filter(s => !existing.has(s));
    if (toAdd.length === 0) return state.ad_sets;
    const budget = Math.floor((state.total_budget || 25) / segments.length);
    const newSets = toAdd.map(segment => ({
      segment,
      headline: SEGMENT_HEADLINES[segment],
      copy_version_a: SEGMENT_COPY_A[segment],
      copy_version_b: SEGMENT_COPY_B[segment],
      copy_version_c: SEGMENT_COPY_C[segment],
      active_copy_version: 'A' as const,
      placement_feed: true,
      placement_marketplace: true,
      placement_instagram: true,
      budget_allocation: budget,
    }));
    return [...state.ad_sets, ...newSets];
  };

  const adSets = ensureAdSets();

  const updateAdSet = (segmentKey: Segment, updates: Partial<AdSetConfig>) => {
    const updated = adSets.map(a => a.segment === segmentKey ? { ...a, ...updates } : a);
    onChange({ ad_sets: updated });
  };

  const handleHeadlineChange = (segment: Segment, headline: string) => {
    updateAdSet(segment, { headline });
    const { warnings } = validateHeadline(headline, segment);
    setHeadlineWarnings(prev => ({ ...prev, [segment]: warnings }));
  };

  return (
    <div className="space-y-6">
      <BattlePlanCallout>
        One audience = one ad set = one segment-matched creative. Headlines are pre-populated from the battle plan but can be edited — Claude will flag any deviation from approved copy standards.
      </BattlePlanCallout>

      <div className="space-y-5">
        {segments.map(segment => {
          const adSet = adSets.find(a => a.segment === segment) || {
            segment,
            headline: SEGMENT_HEADLINES[segment],
            copy_version_a: SEGMENT_COPY_A[segment],
            copy_version_b: SEGMENT_COPY_B[segment],
            copy_version_c: SEGMENT_COPY_C[segment],
            active_copy_version: 'A' as const,
            placement_feed: true,
            placement_marketplace: true,
            placement_instagram: true,
            budget_allocation: Math.floor((state.total_budget || 25) / segments.length),
          };
          const warnings = headlineWarnings[segment] || [];

          return (
            <div key={segment} className="border border-gray-200 rounded-xl p-5 space-y-4">
              {/* Segment header */}
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">{SEGMENT_LABELS[segment]}</h3>
                <span className="text-xs bg-[#0A1628]/10 text-[#0A1628] px-2 py-0.5 rounded-full font-medium">
                  Ad Set
                </span>
              </div>

              {/* Headline */}
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">
                  Headline (segment-matched)
                </label>
                <input
                  value={adSet.headline}
                  onChange={(e) => handleHeadlineChange(segment, e.target.value)}
                  className={cn(
                    'w-full border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2',
                    warnings.length > 0 ? 'border-amber-400 focus:ring-amber-200' : 'border-gray-200 focus:ring-[#0A1628]/20'
                  )}
                />
                {warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-1.5 mt-1">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-700">{w}</p>
                  </div>
                ))}
              </div>

              {/* Copy Versions */}
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                  Copy Version
                </label>
                <div className="flex gap-2 mb-2">
                  {(['A', 'B', 'C'] as const).map(v => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => updateAdSet(segment, { active_copy_version: v })}
                      className={cn(
                        'px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors',
                        adSet.active_copy_version === v
                          ? 'bg-[#0A1628] text-white border-[#0A1628]'
                          : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                      )}
                    >
                      {v === 'A' ? 'Version A (Problem/Solution)' : v === 'B' ? 'Version B (Direct/Punchy)' : 'Version C (Situation-Specific)'}
                    </button>
                  ))}
                </div>
                <textarea
                  rows={3}
                  value={
                    adSet.active_copy_version === 'A' ? adSet.copy_version_a
                    : adSet.active_copy_version === 'B' ? adSet.copy_version_b
                    : adSet.copy_version_c
                  }
                  onChange={(e) => {
                    const key = `copy_version_${adSet.active_copy_version.toLowerCase()}` as keyof AdSetConfig;
                    updateAdSet(segment, { [key]: e.target.value });
                  }}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#0A1628]/20"
                />
              </div>

              {/* Placements */}
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                  Placements
                </label>
                <div className="flex gap-3 flex-wrap">
                  {([
                    { key: 'placement_feed', label: 'Feed', locked: false, lockedOff: false },
                    { key: 'placement_marketplace', label: 'Marketplace', locked: false, lockedOff: false },
                    { key: 'placement_instagram', label: 'Instagram Feed', locked: false, lockedOff: false },
                    { key: 'placement_audience_network', label: 'Audience Network', locked: true, lockedOff: true },
                  ] as const).map(({ key, label, locked, lockedOff }) => (
                    <div key={key} className="flex items-center gap-1.5">
                      {locked ? (
                        <div className="flex items-center gap-1.5 opacity-50">
                          <Lock className="h-3 w-3 text-gray-400" />
                          <input type="checkbox" checked={false} disabled className="h-4 w-4 rounded" />
                          <span className="text-sm text-gray-400 line-through">{label}</span>
                          <span className="text-xs text-red-400">Locked OFF</span>
                        </div>
                      ) : (
                        <label className="flex items-center gap-1.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={!!(adSet as any)[key]}
                            onChange={(e) => updateAdSet(segment, { [key]: e.target.checked } as any)}
                            className="h-4 w-4 rounded accent-[#0A1628]"
                          />
                          <span className="text-sm text-gray-700">{label}</span>
                          {!!(adSet as any)[key] && <CheckCircle className="h-3.5 w-3.5 text-green-500" />}
                        </label>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Budget Allocation */}
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1.5">
                  Budget Allocation
                </label>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-500">$</span>
                  <input
                    type="number"
                    min={5}
                    value={adSet.budget_allocation}
                    onChange={(e) => updateAdSet(segment, { budget_allocation: Number(e.target.value) })}
                    className="w-20 border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
                  />
                  <span className="text-xs text-gray-400">/day for this ad set</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
