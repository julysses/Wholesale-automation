import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { LandLead, LandVetting, LandZoning, LandWaterSource, LandSewage } from '@/types';
import { CheckCircle, XCircle, AlertCircle, ChevronRight, ChevronLeft } from 'lucide-react';

interface Props {
  lead: LandLead;
  existing?: LandVetting;
  onComplete?: (passed: boolean) => void;
}

const STEPS = [
  { num: 1, title: 'Lot Size',     icon: '📐' },
  { num: 2, title: 'Zoning',       icon: '🏗️' },
  { num: 3, title: 'Motivation',   icon: '💬' },
  { num: 4, title: 'Water',        icon: '💧' },
  { num: 5, title: 'Sewage',       icon: '🔧' },
  { num: 6, title: 'Power',        icon: '⚡' },
  { num: 7, title: 'Buildability', icon: '🏠' },
];

const MOTIVATION_TAGS = ['divorce', 'probate', 'financial', 'tired_landlord', 'inherited', 'relocation', 'other'];
const BUILDABILITY_ISSUES = ['sinkholes', 'flood_zone', 'endangered_species', 'wetlands', 'easement', 'hoa_restrictions', 'environmental', 'other'];

type FormData = Omit<LandVetting, 'id' | 'created_at' | 'land_lead_id' | 'vetted_by'>;

function RadioGroup({ label, value, onChange, options }: {
  label: string;
  value: string | boolean | undefined;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <p className="text-sm font-medium text-gray-700 mb-2">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
              String(value) === opt.value
                ? 'bg-[#1B3A5C] text-white border-[#1B3A5C]'
                : 'bg-white text-gray-700 border-gray-300 hover:border-[#1B3A5C]'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SevenMustsForm({ lead, existing, onComplete }: Props) {
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Partial<FormData>>(existing ?? {});

  const patch = (updates: Partial<FormData>) => setForm(f => ({ ...f, ...updates }));

  const computeResult = (data: Partial<FormData>) => {
    const fails: string[] = [];
    if (data.lot_size_confirmed === false)  fails.push('Lot size mismatch — could not confirm');
    if (data.zoning_confirmed === false)    fails.push('Zoning not confirmed');
    if ((data.motivation_score ?? 0) < 2)  fails.push('Seller motivation too low');
    if (data.water_source === 'none')       fails.push('No water source available');
    if (data.sewage_type === 'none')        fails.push('No sewage available');
    if (data.power_type === 'none')         fails.push('No power available');
    if (data.can_build === false)           fails.push('Property has buildability issues');
    return { passed: fails.length === 0, fail_reasons: fails };
  };

  const saveMutation = useMutation({
    mutationFn: async (data: Partial<FormData>) => {
      const { passed, fail_reasons } = computeResult(data);
      const payload = { ...data, land_lead_id: lead.id, passed, fail_reasons, completed_at: new Date().toISOString() };

      if (existing?.id) {
        const { error } = await supabase.from('land_vetting').update(payload).eq('id', existing.id);
        if (error) throw error;
      } else {
        const { error } = await supabase.from('land_vetting').insert(payload);
        if (error) throw error;
      }

      await supabase.from('land_leads').update({
        status: 'vetted',
        vetting_passed: passed,
      }).eq('id', lead.id);

      return passed;
    },
    onSuccess: (passed) => {
      qc.invalidateQueries({ queryKey: ['land_leads'] });
      onComplete?.(passed);
    },
  });

  const stepContent = () => {
    switch (step) {
      case 0: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Confirm the lot size matches the county record. Discrepancies affect offer calculation.</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">County Record (acres)</label>
              <input type="number" step="0.01" value={lead.lot_size_acres ?? ''} disabled
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-500" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Seller Confirmed (acres)</label>
              <input type="number" step="0.01"
                value={form.lot_size_actual ?? ''}
                onChange={e => patch({ lot_size_actual: parseFloat(e.target.value) || undefined })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <RadioGroup label="Does size match the record?" value={String(form.lot_size_confirmed)}
            onChange={v => patch({ lot_size_confirmed: v === 'true' })}
            options={[{ value: 'true', label: 'Yes — matches' }, { value: 'false', label: 'No — discrepancy' }]} />
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Notes</label>
            <textarea rows={2} value={form.lot_size_notes ?? ''}
              onChange={e => patch({ lot_size_notes: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        </div>
      );
      case 1: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Confirm the current zoning classification.</p>
          <RadioGroup label="Confirmed zoning type" value={form.zoning_type}
            onChange={v => patch({ zoning_type: v as LandZoning, zoning_confirmed: true })}
            options={[
              { value: 'single_family', label: 'Single Family' },
              { value: 'multifamily',   label: 'Multifamily' },
              { value: 'commercial',    label: 'Commercial' },
              { value: 'agricultural', label: 'Agricultural' },
              { value: 'mixed',         label: 'Mixed Use' },
            ]} />
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Zoning notes / variance potential</label>
            <textarea rows={2} value={form.zoning_notes ?? ''}
              onChange={e => patch({ zoning_notes: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        </div>
      );
      case 2: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Why is the seller looking to sell? This is your most important qualifying question.</p>
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Seller's stated reason (their words)</label>
            <textarea rows={3} placeholder="e.g. 'I inherited this from my parents and don't know what to do with it…'"
              value={form.seller_motivation ?? ''}
              onChange={e => patch({ seller_motivation: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Motivation tag</p>
            <div className="flex flex-wrap gap-2">
              {MOTIVATION_TAGS.map(tag => (
                <button key={tag} type="button"
                  onClick={() => patch({ motivation_tag: tag })}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium border capitalize transition-colors ${
                    form.motivation_tag === tag ? 'bg-[#E8720C] text-white border-[#E8720C]' : 'bg-white text-gray-700 border-gray-300 hover:border-[#E8720C]'
                  }`}>
                  {tag.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Motivation level (1 = not motivated, 5 = must sell now)</p>
            <div className="flex gap-2">
              {[1,2,3,4,5].map(n => (
                <button key={n} type="button"
                  onClick={() => patch({ motivation_score: n })}
                  className={`w-10 h-10 rounded-lg font-bold text-sm border transition-colors ${
                    form.motivation_score === n
                      ? n >= 4 ? 'bg-green-600 text-white border-green-600' : n === 3 ? 'bg-yellow-500 text-white border-yellow-500' : 'bg-red-500 text-white border-red-500'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-gray-500'
                  }`}>
                  {n}
                </button>
              ))}
            </div>
          </div>
        </div>
      );
      case 3: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Water availability significantly affects land value and buildability.</p>
          <RadioGroup label="Water source" value={form.water_source}
            onChange={v => patch({ water_source: v as LandWaterSource, water_confirmed: true })}
            options={[
              { value: 'city',    label: 'City Water (best)' },
              { value: 'well',    label: 'Well' },
              { value: 'none',    label: 'No Water' },
              { value: 'unknown', label: 'Unknown' },
            ]} />
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Notes</label>
            <textarea rows={2} value={form.water_notes ?? ''}
              onChange={e => patch({ water_notes: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        </div>
      );
      case 4: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Septic systems require logging the last pump date — critical for buyer due diligence.</p>
          <RadioGroup label="Sewage type" value={form.sewage_type}
            onChange={v => patch({ sewage_type: v as LandSewage, sewage_confirmed: true })}
            options={[
              { value: 'city_sewer', label: 'City Sewer (best)' },
              { value: 'septic',     label: 'Septic Tank' },
              { value: 'none',       label: 'No Sewage' },
              { value: 'unknown',    label: 'Unknown' },
            ]} />
          {form.sewage_type === 'septic' && (
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Last Septic Pump Date</label>
              <input type="date" value={form.septic_pump_date ?? ''}
                onChange={e => patch({ septic_pump_date: e.target.value })}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Notes</label>
            <textarea rows={2} value={form.sewage_notes ?? ''}
              onChange={e => patch({ sewage_notes: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        </div>
      );
      case 5: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Power availability or ability to hook up to existing lines.</p>
          <RadioGroup label="Power status" value={form.power_type}
            onChange={v => patch({ power_type: v, power_confirmed: true })}
            options={[
              { value: 'connected',        label: 'Already Connected' },
              { value: 'hookup_available', label: 'Hookup Available' },
              { value: 'none',             label: 'No Power / Can\'t Hook Up' },
              { value: 'unknown',          label: 'Unknown' },
            ]} />
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Notes (distance to nearest line, etc.)</label>
            <textarea rows={2} value={form.power_notes ?? ''}
              onChange={e => patch({ power_notes: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        </div>
      );
      case 6: return (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">Is there any reason this property cannot be built on? This is a deal-killer check.</p>
          <RadioGroup label="Can the property be built on?" value={String(form.can_build)}
            onChange={v => patch({ can_build: v === 'true', buildability_confirmed: true })}
            options={[
              { value: 'true',  label: 'Yes — buildable' },
              { value: 'false', label: 'No — has issues' },
            ]} />
          {form.can_build === false && (
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Select all buildability issues</p>
              <div className="flex flex-wrap gap-2">
                {BUILDABILITY_ISSUES.map(issue => {
                  const active = (form.buildability_issues ?? []).includes(issue);
                  return (
                    <button key={issue} type="button"
                      onClick={() => {
                        const current = form.buildability_issues ?? [];
                        patch({ buildability_issues: active ? current.filter(i => i !== issue) : [...current, issue] });
                      }}
                      className={`px-3 py-1.5 rounded-lg text-sm border capitalize transition-colors ${
                        active ? 'bg-red-600 text-white border-red-600' : 'bg-white text-gray-700 border-gray-300 hover:border-red-400'
                      }`}>
                      {issue.replace(/_/g, ' ')}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-gray-500 block mb-1">Buildability notes</label>
            <textarea rows={2} value={form.buildability_notes ?? ''}
              onChange={e => patch({ buildability_notes: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>
        </div>
      );
      default: return null;
    }
  };

  const { passed, fail_reasons } = computeResult(form);
  const isLast = step === STEPS.length - 1;

  return (
    <div className="space-y-6">
      {/* Step progress bar */}
      <div className="flex items-center gap-1">
        {STEPS.map((s, i) => (
          <div key={s.num} className="flex items-center gap-1 flex-1">
            <button onClick={() => setStep(i)}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors flex-1 ${
                i === step ? 'bg-[#1B3A5C] text-white' : i < step ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}>
              <span>{s.icon}</span>
              <span className="hidden sm:inline">{s.title}</span>
              <span className="sm:hidden">{s.num}</span>
            </button>
            {i < STEPS.length - 1 && <ChevronRight className="h-3 w-3 text-gray-300 shrink-0" />}
          </div>
        ))}
      </div>

      {/* Step header */}
      <div>
        <h3 className="text-base font-bold text-[#1B3A5C]">
          Must #{step + 1}: {STEPS[step].title}
        </h3>
        <p className="text-xs text-gray-400">{lead.property_address} · {lead.owner_name}</p>
      </div>

      {/* Step content */}
      <div className="min-h-[200px]">
        {stepContent()}
      </div>

      {/* Result preview on last step */}
      {isLast && (
        <div className={`rounded-xl p-4 border ${passed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center gap-2 mb-2">
            {passed
              ? <CheckCircle className="h-5 w-5 text-green-600" />
              : <XCircle className="h-5 w-5 text-red-600" />}
            <span className={`font-semibold text-sm ${passed ? 'text-green-700' : 'text-red-700'}`}>
              {passed ? 'Passes all 7 Musts — move to comp stage' : `Failed ${fail_reasons.length} must(s)`}
            </span>
          </div>
          {!passed && (
            <ul className="space-y-1">
              {fail_reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs text-red-600">
                  <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
                  {r}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="flex justify-between pt-2 border-t border-gray-100">
        <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}
          className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">
          <ChevronLeft className="h-4 w-4" /> Back
        </button>
        {isLast ? (
          <button onClick={() => saveMutation.mutate(form)}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1 px-5 py-2 text-sm font-bold bg-[#1B3A5C] text-white rounded-lg hover:bg-[#152d47] disabled:opacity-60">
            {saveMutation.isPending ? 'Saving…' : 'Save Vetting Results'}
          </button>
        ) : (
          <button onClick={() => setStep(s => Math.min(STEPS.length - 1, s + 1))}
            className="flex items-center gap-1 px-4 py-2 text-sm font-medium bg-[#1B3A5C] text-white rounded-lg hover:bg-[#152d47]">
            Next <ChevronRight className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
