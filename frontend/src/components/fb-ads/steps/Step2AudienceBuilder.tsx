import { useState, useCallback } from 'react';
import { Upload, ChevronDown, ChevronRight, AlertTriangle, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  TIER1_SIGNALS, TIER2_SIGNALS, TIER3_SIGNALS,
  AUDIENCE_TYPES, AUDIENCE_PRIORITY, DFW_COUNTIES,
  MIN_AUDIENCE_RECORDS, LOOKALIKE_THRESHOLD,
  type DFWCounty,
} from '@/lib/fb-ads/battlePlanRules';
import { BattlePlanCallout } from './Step1CampaignSettings';

interface CustomAudienceUpload {
  name: string;
  type: string;
  county: string;
  recordCount: number;
  priority: 'red' | 'orange' | 'yellow';
  file?: File;
}

interface Step2State {
  custom_audiences: CustomAudienceUpload[];
  tier1_signals: string[];
  tier2_signals: string[];
  tier3_signals: string[];
  counties: DFWCounty[];
  income_min: number;
  income_max: number;
}

interface Props {
  state: Step2State;
  onChange: (updates: Partial<Step2State>) => void;
  errors: Record<string, string>;
  blockReason?: string;
}

export function Step2AudienceBuilder({ state, onChange, errors, blockReason }: Props) {
  const [openTiers, setOpenTiers] = useState<Set<number>>(new Set([1]));
  const [dragOver, setDragOver] = useState(false);
  const [uploadAudienceType, setUploadAudienceType] = useState('Pre-Foreclosure');
  const [uploadCounty, setUploadCounty] = useState('Dallas');
  const [lookalikeCounts] = useState({
    'Pre-Foreclosure List': 0,
    'Lead Form Completions': 0,
    'Website Pixel Visitors': 0,
    'Closed Deal Contacts': 0,
  });

  const toggleTier = (tier: number) => {
    setOpenTiers(prev => {
      const next = new Set(prev);
      next.has(tier) ? next.delete(tier) : next.add(tier);
      return next;
    });
  };

  const toggleSignal = (tier: 1 | 2 | 3, id: string) => {
    const key = `tier${tier}_signals` as keyof Step2State;
    const current = state[key] as string[];
    const updated = current.includes(id)
      ? current.filter(s => s !== id)
      : [...current, id];
    onChange({ [key]: updated });
  };

  const handleFileDrop = useCallback((e: React.DragEvent | React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    setDragOver(false);
    const file = 'dataTransfer' in e
      ? e.dataTransfer.files[0]
      : (e.target as HTMLInputElement).files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const lines = text.trim().split('\n');
      const recordCount = Math.max(0, lines.length - 1); // minus header

      const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const audienceName = `${uploadAudienceType.replace(/\s+/g, '')}-${uploadCounty}-${today}`;
      const newAudience: CustomAudienceUpload = {
        name: audienceName,
        type: uploadAudienceType,
        county: uploadCounty,
        recordCount,
        priority: AUDIENCE_PRIORITY[uploadAudienceType] || 'yellow',
        file,
      };
      onChange({ custom_audiences: [...state.custom_audiences, newAudience] });
    };
    reader.readAsText(file);
  }, [uploadAudienceType, uploadCounty, state.custom_audiences, onChange]);

  const removeAudience = (idx: number) => {
    onChange({ custom_audiences: state.custom_audiences.filter((_, i) => i !== idx) });
  };

  const toggleCounty = (county: DFWCounty) => {
    const updated = state.counties.includes(county)
      ? state.counties.filter(c => c !== county)
      : [...state.counties, county];
    onChange({ counties: updated });
  };

  const hasCustomAudience = state.custom_audiences.length > 0;
  const hasTier1Signal = state.tier1_signals.length > 0;

  return (
    <div className="space-y-6">
      <BattlePlanCallout>
        Custom Audience uploads (PropStream/BatchLeads CSVs) are your highest-ROI targeting layer.
        Pair with at least one Tier 1 distress signal. Target homeowners only in DFW counties.
      </BattlePlanCallout>

      {blockReason && (
        <div className="flex items-start gap-2 p-4 bg-red-50 border border-red-300 rounded-xl">
          <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
          <p className="text-sm text-red-800">{blockReason}</p>
        </div>
      )}

      {/* A — Custom Audience Upload */}
      <Section title="A. Custom Audience Upload" subtitle="Upload CSV from PropStream or BatchLeads">
        <div className="flex gap-3 mb-3 flex-wrap">
          <select
            value={uploadAudienceType}
            onChange={(e) => setUploadAudienceType(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm"
          >
            {AUDIENCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select
            value={uploadCounty}
            onChange={(e) => setUploadCounty(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm"
          >
            {DFW_COUNTIES.map(c => <option key={c} value={c}>{c} County</option>)}
          </select>
        </div>

        <label
          className={cn(
            'flex flex-col items-center justify-center h-28 border-2 border-dashed rounded-xl cursor-pointer transition-colors',
            dragOver ? 'border-[#0A1628] bg-[#0A1628]/5' : 'border-gray-200 hover:border-gray-300 bg-gray-50'
          )}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleFileDrop}
        >
          <Upload className="h-6 w-6 text-gray-400 mb-2" />
          <span className="text-sm text-gray-600">Drop CSV here or <span className="text-[#0A1628] font-medium">browse</span></span>
          <span className="text-xs text-gray-400 mt-1">Min {MIN_AUDIENCE_RECORDS} records</span>
          <input type="file" accept=".csv" className="hidden" onChange={handleFileDrop} />
        </label>

        {state.custom_audiences.length > 0 && (
          <div className="mt-3 space-y-2">
            {state.custom_audiences.map((aud, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-white border rounded-lg">
                <div className="flex items-center gap-2">
                  <PriorityBadge priority={aud.priority} />
                  <div>
                    <p className="text-sm font-medium text-gray-900">{aud.name}</p>
                    <p className="text-xs text-gray-500">{aud.recordCount.toLocaleString()} records</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {aud.recordCount < MIN_AUDIENCE_RECORDS && (
                    <span className="text-xs text-red-500">Too small</span>
                  )}
                  {aud.recordCount < 500 && aud.recordCount >= MIN_AUDIENCE_RECORDS && (
                    <span className="text-xs text-amber-500">Below lookalike threshold</span>
                  )}
                  {aud.recordCount >= 500 && (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  )}
                  <button onClick={() => removeAudience(i)} className="text-xs text-red-400 hover:text-red-600">Remove</button>
                </div>
              </div>
            ))}
          </div>
        )}
        {errors.custom_audiences && <p className="text-xs text-red-500 mt-1">{errors.custom_audiences}</p>}
      </Section>

      {/* B — Signal Selector */}
      <Section title="B. In-Platform Signal Selector" subtitle="Pre-checked signals align with battle plan">
        {([
          { tier: 1 as const, signals: TIER1_SIGNALS, label: 'Tier 1 — Distress Signals (Required)', color: 'red' },
          { tier: 2 as const, signals: TIER2_SIGNALS, label: 'Tier 2 — Transition Signals', color: 'orange' },
          { tier: 3 as const, signals: TIER3_SIGNALS, label: 'Tier 3 — Landlord Burnout Signals', color: 'yellow' },
        ] as const).map(({ tier, signals, label, color }) => (
          <div key={tier} className="border border-gray-200 rounded-lg overflow-hidden mb-2">
            <button
              type="button"
              onClick={() => toggleTier(tier)}
              className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-2">
                <span className={cn(
                  'h-2 w-2 rounded-full',
                  color === 'red' ? 'bg-red-500' : color === 'orange' ? 'bg-orange-500' : 'bg-yellow-500'
                )} />
                <span className="text-sm font-semibold text-gray-800">{label}</span>
                <span className="text-xs text-gray-400">
                  ({(state[`tier${tier}_signals` as keyof Step2State] as string[]).length} selected)
                </span>
              </div>
              {openTiers.has(tier) ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
            </button>
            {openTiers.has(tier) && (
              <div className="p-3 space-y-2">
                {signals.map(sig => {
                  const selected = (state[`tier${tier}_signals` as keyof Step2State] as string[]).includes(sig.id);
                  return (
                    <label key={sig.id} className="flex items-center gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleSignal(tier, sig.id)}
                        className="h-4 w-4 rounded accent-[#0A1628]"
                      />
                      <span className="text-sm text-gray-700">{sig.label}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        ))}

        {!hasTier1Signal && !hasCustomAudience && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg mt-2">
            <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
            <p className="text-sm text-red-800">
              Your battle plan requires at least one Tier 1 distress signal or a Custom Audience upload.
              Cold reach without distress targeting produces low-quality leads.
            </p>
          </div>
        )}
      </Section>

      {/* C — Demographics */}
      <Section title="C. Demographic Overlay" subtitle="Homeowners only — locked per battle plan">
        <div className="grid grid-cols-2 gap-4">
          <LockedOverlay label="Homeowners Only" value="ON" />
          <LockedOverlay label="Device" value="All Devices" />
        </div>

        <div className="mt-4">
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Household Income Range
          </label>
          <div className="flex items-center gap-3 text-sm text-gray-700">
            <span>$</span>
            <input
              type="number"
              step={5000}
              value={state.income_min}
              onChange={(e) => onChange({ income_min: Number(e.target.value) })}
              className="w-24 border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
            />
            <span>–</span>
            <span>$</span>
            <input
              type="number"
              step={5000}
              value={state.income_max}
              onChange={(e) => onChange({ income_max: Number(e.target.value) })}
              className="w-24 border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
            />
            {(state.income_min !== 40000 || state.income_max !== 100000) && (
              <span className="text-xs text-amber-600">⚠ Battle plan default: $40K–$100K</span>
            )}
          </div>
        </div>

        <div className="mt-4">
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            DFW Counties <span className="text-red-500">*</span> (min 1)
          </label>
          <div className="flex gap-2 flex-wrap">
            {DFW_COUNTIES.map(county => (
              <button
                key={county}
                type="button"
                onClick={() => toggleCounty(county)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors',
                  state.counties.includes(county)
                    ? 'bg-[#0A1628] text-white border-[#0A1628]'
                    : 'bg-white text-gray-700 border-gray-200 hover:border-gray-300'
                )}
              >
                {county}
              </button>
            ))}
          </div>
          {errors.counties && <p className="text-xs text-red-500 mt-1">{errors.counties}</p>}
        </div>
      </Section>

      {/* D — Lookalike */}
      <Section title="D. Lookalike Audience Status" subtitle="Readiness tracker for seed audiences">
        <div className="space-y-2">
          {Object.entries(lookalikeCounts).map(([name, count]) => {
            const ready = count >= LOOKALIKE_THRESHOLD;
            return (
              <div key={name} className="flex items-center justify-between p-3 bg-white border rounded-lg">
                <span className="text-sm text-gray-700">{name}</span>
                <div className="flex items-center gap-2">
                  {ready ? (
                    <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                      <CheckCircle className="h-3.5 w-3.5" /> READY
                    </span>
                  ) : (
                    <span className="text-xs text-gray-500">
                      {count}/{LOOKALIKE_THRESHOLD} leads
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Section>
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-bold text-gray-800">{title}</h3>
        {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function LockedOverlay({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 border border-gray-200 rounded-lg">
      <span className="text-sm text-gray-600">{label}</span>
      <div className="flex items-center gap-1.5">
        <span className="text-sm font-semibold text-gray-900">{value}</span>
        <span className="text-xs bg-gray-200 text-gray-500 px-1.5 py-0.5 rounded">Locked</span>
      </div>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: 'red' | 'orange' | 'yellow' }) {
  const map = {
    red: { emoji: '🔴', class: 'bg-red-100 text-red-700' },
    orange: { emoji: '🟠', class: 'bg-orange-100 text-orange-700' },
    yellow: { emoji: '🟡', class: 'bg-yellow-100 text-yellow-700' },
  };
  return (
    <span className={cn('text-xs px-1.5 py-0.5 rounded font-medium', map[priority].class)}>
      {map[priority].emoji} {priority.charAt(0).toUpperCase() + priority.slice(1)}
    </span>
  );
}
