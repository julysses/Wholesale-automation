import { useState } from 'react';
import {useProfile} from '@/hooks/useProfile';
import {useLandValuation} from '@/hooks/useLandValuation';
import type { LandLead, LandComps } from '@/types';
import { Calculator, TrendingUp, FileText, Info } from 'lucide-react';

interface Props {
  lead: LandLead;
  existing?: LandComps;
}

function fmt(n: number | undefined | null) {
  if (n===null||n===undefined) return '—';
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
  source_url: string;
}

const emptyRow = (): CompRow => ({ address: '', price: '', sqft: '', date: '', distance_mi: '', source_url: '' });

export function QuickCompCalculator({lead}:Props){
 const {profile,isApproved}=useProfile();
 return profile&&isApproved?<ValuationWorkspace key={`${profile.id}:${lead.id}`} actor={profile.id} lead={lead}/>:<p>Sign in as an approved operator to review valuation evidence.</p>;
}
function ValuationWorkspace({actor,lead}:{actor:string;lead:LandLead}){
 const workflow=useLandValuation(actor,lead.id);
 const [reload,setReload]=useState(0);
 const snapshot=workflow.query.data;
 return <div className="space-y-3">
  {workflow.notice&&<p role="status">{workflow.notice}</p>}{workflow.error&&<p role="alert">{workflow.error}</p>}
  {workflow.pending&&<div role="alert"><p>A valuation save is unconfirmed. Retry the original saved inputs before editing.</p><button disabled={workflow.busy} onClick={()=>void workflow.retry()}>Retry saved valuation</button></div>}
  <button disabled={workflow.locked||workflow.query.isFetching} onClick={()=>{setReload(value=>value+1);void workflow.query.refetch();}}>Reload saved analysis (discard unsaved edits)</button>
  {workflow.query.isLoading&&<p>Loading saved valuation…</p>}
  {workflow.query.error&&<p role="alert">Saved valuation unavailable: {workflow.query.error.message}</p>}
  {snapshot&&!workflow.query.error&&<>
   <p>Saved analyses: {snapshot.record_count}. {snapshot.record_count>1?'The newest record is selected; earlier records remain unchanged.':''}</p>
   <CalculatorForm key={`${snapshot.snapshot_hash}:${reload}`} lead={{...lead,property_address:snapshot.property_address,tav:snapshot.reference_tav??undefined}} existing={snapshot.comp as unknown as LandComps|undefined} locked={workflow.locked||workflow.query.isFetching} onSave={input=>workflow.save(snapshot.snapshot_hash,input)}/>
  </>}
 </div>;
}
function CalculatorForm({lead,existing,locked,onSave}:Props&{locked:boolean;onSave:(input:unknown)=>Promise<void>}){
  // Method 1: Direct land comps
  const [directRows, setDirectRows] = useState<CompRow[]>(
    existing?.direct_comp_details?.map(d => ({
      address: d.address, price: d.price, sqft: d.sqft??'',
      date: d.date??'', distance_mi: d.distance_mi??'', source_url:d.source_url??'',
    })) ?? [emptyRow()]
  );

  // Method 2: 15% rule
  const radius=existing ? existing.house_comp_radius_mi : 0.5;
  const [avgHouseArv, setAvgHouseArv] = useState<number | ''>(existing?.avg_house_arv ?? '');
  const [houseCompCount, setHouseCompCount] = useState<number | ''>(existing?.house_comp_count ?? '');

  // Method 3: TAV
  const [tav, setTav] = useState<number | ''>(existing ? existing.tav ?? '' : lead.tav ?? '');
  const [tavSource, setTavSource] = useState(existing?.tav_source ?? 'manual');

  const [assessmentDate,setAssessmentDate]=useState(existing?.tav_assessment_date??'');
  const [notes, setNotes] = useState(existing?.comp_notes ?? '');

  // ── Calculations ──────────────────────────────────────────────────────────
  const validDirectRows = directRows.filter(r => r.price && Number(r.price) > 0);
  const directCompAvg = validDirectRows.length > 0
    ? validDirectRows.reduce((sum, r) => sum + Number(r.price), 0) / validDirectRows.length
    : undefined;
  const directCompLow  = validDirectRows.length > 0 ? Math.min(...validDirectRows.map(r => Number(r.price))) : undefined;
  const directCompHigh = validDirectRows.length > 0 ? Math.max(...validDirectRows.map(r => Number(r.price))) : undefined;

  const arv15pct = avgHouseArv ? Number(avgHouseArv) * 0.15 : undefined;


  function save(){
   const rows=directRows.filter(row=>Object.values(row).some(value=>value!==''));
   void onSave({direct_comp_details:rows.map(row=>({address:row.address,price:row.price===''?null:row.price,sqft:row.sqft===''?null:row.sqft,date:row.date||null,distance_mi:row.distance_mi===''?null:row.distance_mi,source_url:row.source_url||null})),
    avg_house_arv:avgHouseArv===''?null:avgHouseArv,house_comp_count:houseCompCount===''?null:houseCompCount,
    tav:tav===''?null:tav,tav_source:tavSource,tav_assessment_date:assessmentDate||null,comp_notes:notes});
  }

  return (
    <fieldset disabled={locked} className="space-y-6">
      <div>
        <h3 className="text-base font-bold text-[#1B3A5C]">Quick-Comp Calculator</h3>
        <p className="text-xs text-gray-500 mt-0.5">{lead.property_address} · {lead.lot_size_acres ?? '?'} acres</p>
      </div>

      {/* ── Method 1: Direct Land Comps ───────────────────────────────────── */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-blue-700" />
          <span className="text-sm font-bold text-blue-800">Method 1 — Direct Land Comps</span>
          <InfoTip text="Compare sold vacant-land evidence. Verify sale date, location, size and comparability before relying on an average." />
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
                <th className="text-left pb-1.5">Source URL (optional)</th>
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
                      const r = [...directRows]; r[i] = { ...r[i], price: e.target.value===''?'':Number(e.target.value) }; setDirectRows(r);
                    }} placeholder="45000" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input type="number" value={row.sqft} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], sqft: e.target.value===''?'':Number(e.target.value) }; setDirectRows(r);
                    }} placeholder="10890" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input aria-label={`Comp ${i+1} sale date`} type="date" value={row.date} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], date: e.target.value }; setDirectRows(r);
                    }} className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1">
                    <input type="number" step="0.1" value={row.distance_mi} onChange={e => {
                      const r = [...directRows]; r[i] = { ...r[i], distance_mi: e.target.value===''?'':Number(e.target.value) }; setDirectRows(r);
                    }} placeholder="0.3" className="w-full border border-blue-200 rounded px-2 py-1 bg-white text-xs" />
                  </td>
                  <td className="pr-2 py-1"><input aria-label={`Comp ${i+1} source URL`} type="url" value={row.source_url} placeholder="https://…" onChange={e=>{const rows=[...directRows];rows[i]={...rows[i],source_url:e.target.value};setDirectRows(rows);}} className="border rounded px-2 py-1"/></td>
                  <td className="py-1">
                    <button onClick={() => setDirectRows(directRows.filter((_, idx) => idx !== i))}
                      className="text-red-400 hover:text-red-600 text-base leading-none px-1">×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button disabled={directRows.length>=50} onClick={() => setDirectRows([...directRows, emptyRow()])}
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
          <InfoTip text="A 15% reference calculation using the entered house values. Verify comparable selection and the saved radius before relying on it; this does not establish land market value." />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-orange-700 font-medium block mb-1">Avg House ARV ({radius==null?'radius unknown':`${radius}mi radius`})</label>
            <input type="number" value={avgHouseArv}
              onChange={e => setAvgHouseArv(e.target.value===''?'':Number(e.target.value))}
              placeholder="280000"
              className="w-full border border-orange-200 rounded-lg px-3 py-2 text-sm bg-white" />
          </div>
          <div>
            <label className="text-xs text-orange-700 font-medium block mb-1">House comp count</label>
            <input type="number" value={houseCompCount}
              onChange={e => setHouseCompCount(e.target.value===''?'':Number(e.target.value))}
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
          <InfoTip text="Tax assessed value is a separate reference and may differ from market value. Verify its source and assessment date." />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-green-700 font-medium block mb-1">TAV</label>
            <input type="number" value={tav}
              onChange={e => setTav(e.target.value===''?'':Number(e.target.value))}
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

      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        These estimates support valuation review. A human must establish the offer price
        and approve its exact terms in Human Offer Review. Saving this analysis does not
        set an offer, change the lead stage, or contact the seller.
      </div>

      <label className="block text-sm">Tax assessment date (optional)<input aria-label="Tax assessment date" type="date" value={assessmentDate} onChange={e=>setAssessmentDate(e.target.value)} className="block border rounded p-2"/></label>
      <p className="text-xs text-gray-500">Blank area, date, distance and source fields remain unknown. These calculations do not independently verify comparable sales or market value.</p>
      {/* Notes + Save */}
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-gray-500 block mb-1">Comp notes</label>
          <textarea aria-label="Comp notes" maxLength={10000} rows={2} value={notes} onChange={e => setNotes(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
        </div>
        <button onClick={save}
          disabled={locked}
          className="w-full py-2.5 bg-[#E8720C] text-white font-bold text-sm rounded-lg hover:bg-[#d4660b] disabled:opacity-50">
          Save Comp Analysis
        </button>
      </div>
    </fieldset>
  );
}
