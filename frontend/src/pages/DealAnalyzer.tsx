import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { calculateMAO, formatCurrency } from '@/lib/utils';
import { supabase } from '@/lib/supabase';
import { toast } from 'sonner';
import { Plus, Trash2, Calculator, TrendingUp, Save } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useLeads } from '@/hooks/useLeads';

interface Comp {
  address: string;
  sqft: number;
  sale_price: number;
  sale_date: string;
  distance: number;
}

interface LineItem {
  label: string;
  amount: number;
}

const CONDITION_ESTIMATES: Record<string, [number, number]> = {
  cosmetic: [5000, 15000],
  moderate: [25000, 50000],
  full_renovation: [60000, 120000],
};

const DEFAULT_LINE_ITEMS: LineItem[] = [
  { label: 'Foundation', amount: 0 },
  { label: 'Roof', amount: 0 },
  { label: 'HVAC', amount: 0 },
  { label: 'Plumbing', amount: 0 },
  { label: 'Electrical', amount: 0 },
  { label: 'Cosmetic / Paint / Flooring', amount: 0 },
];

export function DealAnalyzer() {
  const [address, setAddress] = useState('');
  const [sqft, setSqft] = useState<number>(0);
  const [beds, setBeds] = useState<number>(3);
  const [baths, setBaths] = useState<number>(2);
  const [condition, setCondition] = useState('moderate');
  const [comps, setComps] = useState<Comp[]>([
    { address: '', sqft: 0, sale_price: 0, sale_date: '', distance: 0 }
  ]);
  const [arv, setArv] = useState<number>(0);
  const [repairOverride, setRepairOverride] = useState<number | null>(null);
  const [lineItems, setLineItems] = useState<LineItem[]>(DEFAULT_LINE_ITEMS);
  const [assignmentFee, setAssignmentFee] = useState<number>(15000);
  const [aiRec, setAiRec] = useState<string>('');
  const [loadingAi, setLoadingAi] = useState(false);
  const [saveLeadId, setSaveLeadId] = useState('');
  const [savingToLead, setSavingToLead] = useState(false);
  const { data: leadsData } = useLeads({ pageSize: 200 });
  const queryClient = useQueryClient();
  const allLeads = leadsData?.data ?? [];

  const handleSaveToLead = async () => {
    if (!saveLeadId) return toast.error('Select a lead to save to');
    if (arv === 0) return toast.error('Calculate ARV first');
    setSavingToLead(true);
    try {
      // One durable analysis write also updates the lead through the existing
      // deal_analysis_sync trigger, so Acquisitions sees the same analysis.
      const { error } = await supabase.from('deal_analyses').insert({
        lead_id: saveLeadId,
        arv_low: arv, arv_mid: arv, arv_high: arv,
        arv_confidence: 'low',
        arv_comp_count: comps.filter(c => c.sale_price > 0 && c.sqft > 0).length,
        arv_notes: 'Operator-entered comparable analysis; values are estimates.',
        repair_tier: condition === 'cosmetic' ? 'light' : condition === 'full_renovation' ? 'heavy' : 'moderate',
        repair_cost_low: estimatedRepairs, repair_cost_mid: estimatedRepairs, repair_cost_high: estimatedRepairs,
        assignment_fee: assignmentFee,
        mao,
        offer_range_low: Math.max(0, mao * 0.9), offer_range_high: Math.max(0, mao),
        is_viable: mao > 0,
        summary: aiRec || 'Manual comparable and repair analysis.',
      }).select('id').single();
      if (error) throw error;
      const { error: repairError } = await supabase.from('leads')
        .update({ estimated_repairs: estimatedRepairs }).eq('id', saveLeadId).select('id').single();
      if (repairError) throw new Error('Analysis saved, but the lead repair estimate could not be updated. Please retry.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['leads'] }),
        queryClient.invalidateQueries({ queryKey: ['deal_analyses'] }),
      ]);
      toast.success('Analysis saved to lead and Acquisitions');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save analysis. Please retry.');
    } finally {
      setSavingToLead(false);
    }
  };

  // Calculate ARV from comps
  const calculateARV = () => {
    const validComps = comps.filter((c) => c.sale_price > 0 && c.sqft > 0);
    if (validComps.length === 0) {
      toast.error('Add at least one comp with price and sqft');
      return;
    }
    // Distance-weighted average price per sqft
    const weights = validComps.map((c) => 1 / Math.max(c.distance, 0.1));
    const totalWeight = weights.reduce((s, w) => s + w, 0);
    const weightedPPSF = validComps.reduce((s, c, i) => {
      return s + (c.sale_price / c.sqft) * (weights[i] / totalWeight);
    }, 0);
    const calculatedArv = sqft > 0 ? Math.round(weightedPPSF * sqft) : Math.round(
      validComps.reduce((s, c) => s + c.sale_price, 0) / validComps.length
    );
    setArv(calculatedArv);
    toast.success(`ARV calculated: ${formatCurrency(calculatedArv)}`);
  };

  const estimatedRepairs = repairOverride !== null
    ? repairOverride
    : lineItems.reduce((s, l) => s + l.amount, 0) ||
      Math.round((CONDITION_ESTIMATES[condition]?.[0] + CONDITION_ESTIMATES[condition]?.[1]) / 2);

  const mao = arv > 0 ? calculateMAO(arv, estimatedRepairs, assignmentFee) : 0;
  const atMao = arv * 0.7 - estimatedRepairs;
  const fiveBelow = mao * 0.95 > 0 ? arv * 0.7 - estimatedRepairs - (mao * 0.05) : 0;
  const tenBelow = mao * 0.9 > 0 ? arv * 0.7 - estimatedRepairs - (mao * 0.10) : 0;

  const handleGetAiRecommendation = async () => {
    if (arv === 0) {
      toast.error('Calculate ARV first');
      return;
    }
    setLoadingAi(true);
    try {
      const response = await apiFetch('/api/ai/generate-offer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ property_address: address || 'Subject Property', arv, repair_estimate: estimatedRepairs, mao }),
      });
      const data = await response.json();
      const rec = data?.recommendation || data?.options?.[0]?.pitch;
      if (typeof rec !== 'string' || !rec.trim()) throw new Error('No recommendation was returned.');
      setAiRec(rec);
    } catch (error) {
      setAiRec('');
      toast.error(error instanceof Error ? error.message : 'Unable to generate an AI recommendation. Please retry.');
    } finally {
      setLoadingAi(false);
    }
  };

  const addComp = () => {
    if (comps.length >= 6) {
      toast.error('Maximum 6 comps');
      return;
    }
    setComps([...comps, { address: '', sqft: 0, sale_price: 0, sale_date: '', distance: 0 }]);
  };

  const removeComp = (i: number) => {
    setComps(comps.filter((_, idx) => idx !== i));
  };

  const updateComp = (i: number, field: keyof Comp, value: string | number) => {
    const updated = [...comps];
    updated[i] = { ...updated[i], [field]: value };
    setComps(updated);
  };

  const updateLineItem = (i: number, amount: number) => {
    const updated = [...lineItems];
    updated[i].amount = amount;
    setLineItems(updated);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Deal Analyzer</h1>
        <p className="text-sm text-gray-500 mt-0.5">Calculate your MAO and analyze deal profitability</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* LEFT: Input panel */}
        <div className="space-y-5">
          {/* Property Info */}
          <Card>
            <CardHeader><CardTitle>Property Information</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <Input label="Property Address" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="123 Main St" />
              <div className="grid grid-cols-3 gap-3">
                <Input label="Sqft" type="number" value={sqft || ''} onChange={(e) => setSqft(Number(e.target.value))} />
                <Input label="Beds" type="number" value={beds || ''} onChange={(e) => setBeds(Number(e.target.value))} />
                <Input label="Baths" type="number" value={baths || ''} onChange={(e) => setBaths(Number(e.target.value))} step="0.5" />
              </div>
              <Select label="Condition"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                options={[
                  { value: 'cosmetic', label: 'Cosmetic ($5K–$15K)' },
                  { value: 'moderate', label: 'Moderate ($25K–$50K)' },
                  { value: 'full_renovation', label: 'Full Renovation ($60K–$120K)' },
                ]}
              />
            </CardContent>
          </Card>

          {/* Comps */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Comparable Sales</CardTitle>
                <Button size="sm" variant="outline" icon={<Plus className="h-4 w-4" />} onClick={addComp}>
                  Add Comp
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {comps.map((comp, i) => (
                <div key={i} className="border border-gray-200 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-gray-500">Comp #{i + 1}</span>
                    {comps.length > 1 && (
                      <button onClick={() => removeComp(i)} className="text-red-400 hover:text-red-600">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  <Input placeholder="Address" value={comp.address} onChange={(e) => updateComp(i, 'address', e.target.value)} />
                  <div className="grid grid-cols-2 gap-2">
                    <Input placeholder="Sale Price" type="number" value={comp.sale_price || ''} onChange={(e) => updateComp(i, 'sale_price', Number(e.target.value))} />
                    <Input placeholder="Sqft" type="number" value={comp.sqft || ''} onChange={(e) => updateComp(i, 'sqft', Number(e.target.value))} />
                    <Input placeholder="Sale Date" type="date" value={comp.sale_date} onChange={(e) => updateComp(i, 'sale_date', e.target.value)} />
                    <Input placeholder="Distance (mi)" type="number" value={comp.distance || ''} onChange={(e) => updateComp(i, 'distance', Number(e.target.value))} step="0.1" />
                  </div>
                  {comp.sale_price > 0 && comp.sqft > 0 && (
                    <p className="text-xs text-gray-400">
                      ${Math.round(comp.sale_price / comp.sqft)}/sqft
                    </p>
                  )}
                </div>
              ))}
              <Button variant="outline" onClick={calculateARV} icon={<Calculator className="h-4 w-4" />} className="w-full">
                Calculate ARV from Comps
              </Button>
              <Input label="ARV Override" type="number" value={arv || ''} onChange={(e) => setArv(Number(e.target.value))} helperText="Enter manually or calculate from comps above" />
            </CardContent>
          </Card>

          {/* Repairs */}
          <Card>
            <CardHeader><CardTitle>Repair Estimate</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-gray-500">
                Condition estimate: {formatCurrency(CONDITION_ESTIMATES[condition]?.[0])} – {formatCurrency(CONDITION_ESTIMATES[condition]?.[1])}
              </p>
              <div className="space-y-2">
                {lineItems.map((item, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-sm text-gray-600 w-48">{item.label}</span>
                    <Input
                      type="number"
                      value={item.amount || ''}
                      onChange={(e) => updateLineItem(i, Number(e.target.value))}
                      className="flex-1"
                      placeholder="0"
                    />
                  </div>
                ))}
              </div>
              <div className="border-t border-gray-200 pt-2 flex justify-between">
                <span className="text-sm font-medium text-gray-700">Total from Line Items</span>
                <span className="text-sm font-semibold">{formatCurrency(lineItems.reduce((s, l) => s + l.amount, 0))}</span>
              </div>
              <Input
                label="Manual Repair Override"
                type="number"
                value={repairOverride ?? ''}
                onChange={(e) => setRepairOverride(e.target.value ? Number(e.target.value) : null)}
                helperText="Leave blank to use line items"
              />
            </CardContent>
          </Card>

          {/* Assignment fee */}
          <Card>
            <CardContent>
              <Input
                label="Assignment Fee Target"
                type="number"
                value={assignmentFee}
                onChange={(e) => setAssignmentFee(Number(e.target.value))}
              />
            </CardContent>
          </Card>
        </div>

        {/* RIGHT: Results */}
        <div className="space-y-5">
          {/* MAO Result */}
          <div className={cn(
            'rounded-xl p-6 text-center',
            mao > 0 ? 'bg-[#1B3A5C] text-white' : 'bg-gray-100 text-gray-400'
          )}>
            <p className="text-sm font-medium opacity-70 uppercase tracking-wide">Maximum Allowable Offer</p>
            <p className="text-5xl font-bold mt-2">
              {mao > 0 ? formatCurrency(mao) : '—'}
            </p>
            {mao > 0 && (
              <div className="mt-4 text-sm opacity-70 space-y-1">
                <p>ARV {formatCurrency(arv)} × 70% = {formatCurrency(arv * 0.7)}</p>
                <p>− Repairs {formatCurrency(estimatedRepairs)}</p>
                <p>− Fee {formatCurrency(assignmentFee)}</p>
                <p className="font-semibold text-[#E8720C]">= MAO {formatCurrency(mao)}</p>
              </div>
            )}
          </div>

          {/* Scenarios */}
          {mao > 0 && (
            <Card>
              <CardHeader><CardTitle>Profit Scenarios</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[
                    { label: 'If you buy at MAO', offer: mao, profit: assignmentFee, pct: '0%' },
                    { label: 'If you buy 5% below MAO', offer: mao * 0.95, profit: assignmentFee + mao * 0.05, pct: '-5%' },
                    { label: 'If you buy 10% below MAO', offer: mao * 0.90, profit: assignmentFee + mao * 0.10, pct: '-10%' },
                  ].map((s) => (
                    <div key={s.label} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-gray-800">{s.label}</p>
                        <p className="text-xs text-gray-400">Offer: {formatCurrency(s.offer)}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-bold text-green-600">{formatCurrency(s.profit)}</p>
                        <p className="text-xs text-gray-400">your profit</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* AI Recommendation */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>AI Recommendation</CardTitle>
                <Button size="sm" variant="outline" onClick={handleGetAiRecommendation} loading={loadingAi}>
                  {aiRec ? 'Refresh' : 'Get AI Take'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {aiRec ? (
                <p className="text-sm text-gray-700 leading-relaxed">{aiRec}</p>
              ) : (
                <p className="text-sm text-gray-400">
                  Calculate ARV and repairs, then click "Get AI Take" for a recommendation.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Save to Lead */}
          {arv > 0 && (
            <Card>
              <CardHeader><CardTitle>Save to Lead</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Select
                  label="Select Lead"
                  value={saveLeadId}
                  onChange={(e) => setSaveLeadId(e.target.value)}
                  options={allLeads.map((l) => ({ value: l.id, label: l.property_address }))}
                  placeholder="Choose a lead..."
                />
                <Button
                  onClick={handleSaveToLead}
                  loading={savingToLead}
                  disabled={!saveLeadId}
                  icon={<Save className="h-4 w-4" />}
                  className="w-full"
                >
                  Save ARV + Repairs + MAO to Lead
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Summary */}
          {arv > 0 && (
            <Card>
              <CardHeader><CardTitle>Deal Summary</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {[
                    ['ARV', formatCurrency(arv)],
                    ['70% of ARV', formatCurrency(arv * 0.7)],
                    ['Estimated Repairs', formatCurrency(estimatedRepairs)],
                    ['Assignment Fee', formatCurrency(assignmentFee)],
                    ['MAO', formatCurrency(mao)],
                  ].map(([label, value]) => (
                    <div key={label} className="flex justify-between text-sm">
                      <span className="text-gray-500">{label}</span>
                      <span className={cn(
                        'font-medium',
                        label === 'MAO' ? 'text-[#1B3A5C] font-bold text-base' : 'text-gray-900'
                      )}>{value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
