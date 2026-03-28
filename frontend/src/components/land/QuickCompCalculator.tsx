import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { LandLead, LandComps } from '@/types';
import { Calculator, TrendingUp, DollarSign, FileText, Info } from 'lucide-react';

interface Props {
  lead: LandLead;
  existing?: LandComps;
}

function fmt(n: number | undefined | null) {
  if (!n) return '—';
  return '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function InfoTip({ text }: { text: string }) {
  return (
    <span title={text} className="ml-1 inline-flex">
      <Info className="h-3.5 w-3.5 text-gray-400 cursor-help" />
    </span>
  );
}

interface CompRow {
  address: string;
  price: number | '';
  sqft: number | '';
  date: string;
  distance_mi: number | '';
}

const emptyRow = (): CompRow => ({ address: '', price: '', sqft: '', date: '', distance_mi: '' });

export function QuickCompCalculator({ lead, existing }: Props) {
  const qc = useQueryClient();

  // Method 1: Direct land comps
  const [directRows, setDirectRows] = useState<CompRow[]>(
    existing?.direct_comp_details?.map(d => ({
      address: d.address, price: d.price, sqft: d.sqft,
      date: d.date, distance_mi: d.distance_mi,
    })) ?? [emptyRow()]
  );

  // Method 2: 15% rule
  const [avgHouseArv, setAvgHouseArv] = useState<number | ''>(existing?.avg_house_arv ?? '');
  const [houseCompCount, setHouseCompCount] = useState<number | ''>(existing?.house_comp_count ?? '');

  // Method 3: TAV
  const [tav, setTav] = useState<number | ''>(existing?.tav ?? lead.tav ?? '');
  const [tavSource, setTavSource] = useState(existing?.tav_source ?? 'county');

  const [notes, setNotes] = useState(existing?.comp_notes ?? '');

  // ── Calculations ──────────────────────────────────────────────────────────
  const validDirectRows = directRows.filter(r => r.price && Number(r.price) > 0);
  const directCompAvg = validDirectRows.length > 0
    ? validDirectRows.reduce((sum, r) => sum + Number(r.price), 0) / validDirectRows.length
    : undefined;
  const directCompLow  = validDirectRows.length > 0 ? Math.min(...validDirectRows.map(r => Number(r.price))) : undefined;
  const directCompHigh = validDirectRows.length > 0 ? Math.max(...validDirectRows.map(r => Number(r.price))) : undefined;

  const arv15pct = avgHouseArv ? Number(avgHouseArv) * 0.15 : undefined;

  // Recommended offer: 70% of the lowest of the three methods
  const values = [directCompAvg, arv15pct, tav ? Number(tav) : undefined].filter((v): v is number => v !== undefined);
  const lowestValue = values.length > 0 ? Math.min(...values) : undefined;
  const recommendedLow  = lowestValue ? lowestValue * 0.65 : undefined;
  const recommendedHigh = lowestValue ? lowestValue * 0.75 : undefined;

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        land_lead_id: lead.id,
        direct_comp_avg:    directCompAvg,
        direct_comp_count:  validDirectRows.length,
        direct_comp_low:    directCompLow,
        direct_comp_high:   directCompHigh,
        direct_comp_details: validDirectRows.map(r => ({
          address: r.address, price: Number(r.price),
          sqft: Number(r.sqft), date: r.date, distance_mi: Number(r.distance_mi),
        })),
        avg_house_arv:      avgHouseArv ? Number(avgHouseArv) : null,
        arv_15pct_value:    arv15pct,
        house_comp_count:   houseCompCount ? Number(houseCompCount) : null,
        tav:                tav ? Number(tav) : null,
        tav_source:         tavSource,
        recommended_offer_low:  recommendedLow,
        recommended_offer_high: recommendedHigh,
        comp_notes: notes,
      };

      if (existing?.id) {
        const { error } = await supabase.from('land_comps').update(payload).eq('id', existing.id);
        if (error) throw error;
      } else {
        const { error } = await supabase.from('land_comps').insert(payload);
        if (error) throw error;
      }

      await supabase.from('land_leads').update({
        status: 'comped',
        mao: recommendedHigh,
        tav: tav ? Number(tav) : undefined,
      }).eq('id', lead.id);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['land_leads'] }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-bold text-[#1B3A5C]">Quick-Comp Calculator</h3>
        <p className="text-xs text-gray-500 mt-0.5">{lead.property_address} · {lead.lot_size_acres ?? '?'} acres</p>
      </div>

      {/* ── Method 1: Direct Land Comps ───────────────────────────────────── */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-blue-700" />
          <span className="text-sm font-bold text-blue-800">Method 1 — Direct Land Comps</span>
          <InfoTip text="Average of nearby sold vacant land records. Strongest signal." />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-blue-700 border-b border-blue-200">
                <th className="text-left pb-1.5 font-semibold">Address</th>
                <th className="text-left pb-1.5 font-semibold w-24">Sale Price</th>
                <th className="text-left pb-1.5 font-semibold w-20">Sqft</th>
                <th className="text-left pb-1.5 font-semibold w-28">Sale Date</th>
                <th className="text-left pb-1.5 font-semibold w-16">Mi away</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="space-y-1">
              {directRows.map((row, i) => (
                <tr key={i}>
                  <td className="pr-2 py-1">
                    <input value={row.address} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], address: e.target.value }; setDirectRows(r);
                    }} placeholder="123 Oak St" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input type="number" value={row.price} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], price: parseFloat(e.target.value) || '' }; setDirectRows(r);
                    }} placeholder="45000" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input type="number" value={row.sqft} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], sqft: parseInt(e.target.value) || '' }; setDirectRows(r);
                    }} placeholder="10890" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input type="date" value={row.date} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], date: e.target.value }; setDirectRows(r);
                    }} className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input type="number" step="0.1" value={row.distance_mi} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], distance_mi: parseFloat(e.target.value) || '' }; setDirectRows(r);
                    }} placeholder="0.3" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="py-1">
                    <button onClick={() => setDirectRows(directRows.filter((_, idx) => idx !== i))}
                      className="text-red-400 hover:text-red-600 text-base leading-none px-1">×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button onClick={() => setDirectRows([...directRows, emptyRow()])}
          className="text-xs text-blue-700 hover:text-blue-900 font-medium">+ Add comp</button>
        {directCompAvg && (
          <div className="flex gap-4 pt-1 border-t border-blue-200 text-xs text-blue-800 font-medium">
            <span>Avg: <strong>{fmt(directCompAvg)}</strong></span>
            <span>Low: <strong>{fmt(directCompLow)}</strong></span>
            <span>High: <strong>{fmt(directCompHigh)}</strong></span>
            <span>Count: <strong>{validDirectRows.length}</strong></span>
          </div>
        )}
      </div>

      {/* ── Method 2: 15% Rule ────────────────────────────────────────────── */}
      <div className="bg-orange-50 border border-orange-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Calculator className="h-4 w-4 text-orange-700" />
          <span className="text-sm font-bold text-orange-800">Method 2 — The 15% Rule</span>
          <InfoTip text="15% of the average ARV of sold houses within 0.5 miles. Use when no direct land comps exist." />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-orange-700 font-medium block mb-1">Avg House ARV (0.5mi radius)</label>
            <input type="number" value={avgHouseArv}
              onChange={e => setAvgHouseArv(parseFloat(e.target.value) || '')}
              placeholder="280000"
              className="w-full border border-orange-200 rounded-lg px-3 py-2 text-sm bg-white" />
          </div>
          <div>
            <label className="text-xs text-orange-700 font-medium block mb-1">House comp count</label>
            <input type="number" value={houseCompCount}
              onChange={e => setHouseCompCount(parseInt(e.target.value) || '')}
              placeholder="6"
              className="w-full border border-orange-200 rounded-lg px-3 py-2 text-sm bg-white" />
          </div>
        </div>
        {arv15pct && (
          <div className="text-sm font-bold text-orange-800 pt-1 border-t border-orange-200">
            15% of {fmt(Number(avgHouseArv))} = <span className="text-lg">{fmt(arv15pct)}</span>
          </div>
        )}
      </div>

      {/* ── Method 3: TAV ─────────────────────────────────────────────────── */}
      <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-green-700" />
          <span className="text-sm font-bold text-green-800">Method 3 — Tax Assessed Value (TAV)</span>
          <InfoTip text="The county's assessed value. Usually conservative — useful as a floor, not a ceiling." />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-green-700 font-medium block mb-1">TAV</label>
            <input type="number" value={tav}
              onChange={e => setTav(parseFloat(e.target.value) || '')}
              placeholder="42000"
              className="w-full border border-green-200 rounded-lg px-3 py-2 text-sm bg-white" />
          </div>
          <div>
            <label className="text-xs text-green-700 font-medium block mb-1">Source</label>
            <select value={tavSource} onChange={e => setTavSource(e.target.value)}
              className="w-full border border-green-200 rounded-lg px-3 py-2 text-sm bg-white">
              <option value="county">County Appraiser</option>
              <option value="xleads">XLeads Import</option>
              <option value="manual">Manually Entered</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── Recommended Offer ─────────────────────────────────────────────── */}
      {lowestValue && (
        <div className="bg-[#1B3A5C] text-white rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <DollarSign className="h-5 w-5 text-[#E8720C]" />
            <span className="font-bold text-base">Recommended Offer Range</span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-center mb-3">
            {directCompAvg && (
              <div>
                <p className="text-white/60 text-xs mb-1">Direct Comps</p>
                <p className="text-white font-bold text-lg">{fmt(directCompAvg)}</p>
              </div>
            )}
            {arv15pct && (
              <div>
                <p className="text-white/60 text-xs mb-1">15% Rule</p>
                <p className="text-white font-bold text-lg">{fmt(arv15pct)}</p>
              </div>
            )}
            {tav && (
              <div>
                <p className="text-white/60 text-xs mb-1">TAV</p>
                <p className="text-white font-bold text-lg">{fmt(Number(tav))}</p>
              </div>
            )}
          </div>
          <div className="border-t border-white/20 pt-3">
            <p className="text-white/60 text-xs mb-1">Offer range (65–75% of lowest value)</p>
            <p className="text-[#E8720C] font-black text-2xl">{fmt(recommendedLow)} – {fmt(recommendedHigh)}</p>
          </div>
        </div>
      )}

      {/* Notes + Save */}
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">Comp notes</label>
          <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
        </div>
        <button onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || values.length === 0}
          className="w-full py-2.5 bg-[#E8720C] text-white font-bold text-sm rounded-lg hover:bg-[#d4660b] disabled:opacity-50">
          {saveMutation.isPending ? 'Saving…' : 'Save Comp Analysis'}
        </button>
      </div>
    </div>
  );
}
