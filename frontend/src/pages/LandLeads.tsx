import { apiFetch } from '@/lib/api';
import { queryAll } from '@/lib/queryAll';
import { LotInbox } from '@/components/land/LotInbox';
import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { LandLead, LandZoning, LandStatus } from '@/types';
import { SevenMustsForm } from '@/components/land/SevenMustsForm';
import { QuickCompCalculator } from '@/components/land/QuickCompCalculator';
import { LandBuyerHub } from '@/components/land/LandBuyerHub';
import {
  MapPin, Upload, Star, CheckCircle, XCircle, Clock,
  Phone, DollarSign, TreePine, Zap, Droplets, AlertTriangle,
  X, ChevronDown
} from 'lucide-react';
import Papa from 'papaparse';

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n?: number | null) => n != null ? '$' + n.toLocaleString('en-US', { maximumFractionDigits: 0 }) : '—';
const acr = (n?: number | null) => n ? n.toFixed(2) + ' ac' : '—';

const STATUS_COLORS: Record<string, string> = {
  new:            'bg-gray-100 text-gray-600',
  vetting:        'bg-yellow-100 text-yellow-700',
  vetted:         'bg-blue-100 text-blue-700',
  comped:         'bg-purple-100 text-purple-700',
  offer_made:     'bg-orange-100 text-orange-700',
  under_contract: 'bg-green-100 text-green-700',
  dead:           'bg-red-100 text-red-600',
};

const ZONING_LABELS: Record<LandZoning, string> = {
  single_family: 'SF',
  multifamily:   'MF',
  commercial:    'Comm',
  agricultural:  'Ag',
  mixed:         'Mixed',
  unknown:       '?',
};

// ── XLeads CSV column mapping ─────────────────────────────────────────────────
const XLEADS_MAP: Record<string, keyof LandLead> = {
  'Property Address': 'property_address',
  'City':             'city',
  'State':            'state',
  'Zip':              'zip_code',
  'County':           'county',
  'APN':              'apn',
  'Owner Name':       'owner_name',
  'Owner Phone 1':    'owner_phone_1',
  'Owner Phone 2':    'owner_phone_2',
  'Owner Mailing':    'owner_mailing_address',
  'Lot Size (Acres)': 'lot_size_acres',
  'TAV':              'tav',
  'Zoning':           'zoning_raw',
};

function mapXLeadsRow(row: Record<string, string>): Partial<LandLead> {
  const lead: Partial<LandLead> = { state: 'TX' };
  for (const [col, field] of Object.entries(XLEADS_MAP)) {
    const val = row[col]?.trim();
    if (!val) continue;
    if (field === 'lot_size_acres' || field === 'tav') {
      const number = Number(val.replace(/[$,]/g, ''));
      if (!Number.isFinite(number)) throw new Error(`Invalid number in ${col}`);
      (lead as Record<string, unknown>)[field] = number;
    } else {
      (lead as Record<string, unknown>)[field] = field === 'state' ? val.toUpperCase() : val;
    }
  }
  // Derive lot_size_sqft
  if (lead.lot_size_acres) lead.lot_size_sqft = Math.round(lead.lot_size_acres * 43560);
  // Derive xleads_id from APN or address
  lead.xleads_id = row['XLeads ID'] || row['APN'] || undefined;
  return lead;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
type Tab = 'leads' | 'vetting' | 'comps' | 'buyers';
const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: 'leads',   label: 'All Land Leads', icon: MapPin },
  { id: 'vetting', label: '7 Musts Vetting', icon: CheckCircle },
  { id: 'comps',   label: 'Quick-Comp',      icon: DollarSign },
  { id: 'buyers',  label: 'Buyer Hub',       icon: Star },
];

// ── Hooks ─────────────────────────────────────────────────────────────────────
function useLandLeads() {
  return useQuery({
    // Separate the complete snapshot from any cached, capped result from older UI.
    queryKey: ['land_leads', 'all-pages'],
    queryFn: async () => {
      let expectedCount: number | undefined;
      const identities = new Set<string>();
      const rows = await queryAll<LandLead>(async (from, to) => {
        const result = await supabase.from('land_leads').select('*', { count: 'exact' })
          .order('created_at', { ascending: false }).order('id', { ascending: true }).range(from, to);
        if (result.error) throw new Error(result.error.message);
        if (!Number.isInteger(result.count) || result.count === null || result.count < 0) {
          throw new Error('Land record count could not be confirmed. Refresh again.');
        }
        if (expectedCount !== undefined && expectedCount !== result.count) {
          throw new Error('Land records changed while loading. Refresh again.');
        }
        expectedCount = result.count;
        for (const row of result.data ?? []) {
          if (typeof row.id !== 'string' || !row.id || identities.has(row.id)) {
            throw new Error('Land records changed while loading. Refresh again.');
          }
          identities.add(row.id);
        }
        if (identities.size > expectedCount) {
          throw new Error('Land records changed while loading. Refresh again.');
        }
        return result;
      });
      if (rows.length !== expectedCount || identities.size !== rows.length) {
        throw new Error('Land records changed while loading or could not be read completely. Refresh again.');
      }
      return rows;
    },
    refetchInterval: 30000,
  });
}

// ── Lead card ─────────────────────────────────────────────────────────────────
function LandLeadCard({ lead, onSelect }: { lead: LandLead; onSelect: (l: LandLead) => void }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-sm font-bold text-gray-900">{lead.property_address}</p>
            {lead.infill_lot && (
              <span className="px-1.5 py-0.5 rounded text-xs font-bold bg-[#E8720C] text-white flex items-center gap-0.5">
                <Star className="h-3 w-3" /> Infill
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500">{lead.city}, {lead.state} {lead.zip_code} · {lead.owner_name??'Owner not verified'}</p>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${STATUS_COLORS[lead.status] ?? 'bg-gray-100 text-gray-600'}`}>
          {lead.status.replace('_', ' ')}
        </span>
      </div>

      {/* Land details */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="text-center bg-gray-50 rounded-lg p-2">
          <p className="text-xs text-gray-400">Lot Size</p>
          <p className="text-sm font-bold text-gray-800">{acr(lead.lot_size_acres)}</p>
        </div>
        <div className="text-center bg-gray-50 rounded-lg p-2">
          <p className="text-xs text-gray-400">Zoning</p>
          <p className="text-sm font-bold text-gray-800">
            {lead.zoning ? ZONING_LABELS[lead.zoning] : lead.zoning_raw ?? '—'}
          </p>
        </div>
        <div className="text-center bg-gray-50 rounded-lg p-2">
          <p className="text-xs text-gray-400">TAV</p>
          <p className="text-sm font-bold text-gray-800">{fmt(lead.tav)}</p>
        </div>
      </div>

      {/* Utility icons */}
      <div className="flex items-center gap-3 mb-3">
        <span title={`Water: ${lead.water_source}`}
          className={`flex items-center gap-1 text-xs ${lead.water_source === 'city' ? 'text-blue-600' : lead.water_source === 'none' ? 'text-red-500' : 'text-gray-400'}`}>
          <Droplets className="h-3.5 w-3.5" />
          {lead.water_source === 'city' ? 'City water' : lead.water_source === 'well' ? 'Well' : lead.water_source === 'none' ? 'No water' : 'Water?'}
        </span>
        <span title={`Power: ${lead.power_available}`}
          className={`flex items-center gap-1 text-xs ${lead.power_available ? 'text-yellow-600' : 'text-gray-400'}`}>
          <Zap className="h-3.5 w-3.5" />
          {lead.power_available ? 'Power OK' : 'Power?'}
        </span>
        {lead.is_buildable === false && (
          <span className="flex items-center gap-1 text-xs text-red-500">
            <AlertTriangle className="h-3.5 w-3.5" /> Build issues
          </span>
        )}
        {lead.vetting_passed === true && (
          <span className="flex items-center gap-1 text-xs text-green-600">
            <CheckCircle className="h-3.5 w-3.5" /> Vetted ✓
          </span>
        )}
        {lead.vetting_passed === false && (
          <span className="flex items-center gap-1 text-xs text-red-500">
            <XCircle className="h-3.5 w-3.5" /> Failed vetting
          </span>
        )}
      </div>

      {/* Offer range */}
      {lead.mao && (
        <div className="bg-[#1B3A5C]/5 rounded-lg px-3 py-2 mb-3">
          <p className="text-xs text-gray-500">Max offer (MAO)</p>
          <p className="text-base font-black text-[#1B3A5C]">{fmt(lead.mao)}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-2 border-t border-gray-100">
        {lead.owner_phone_1 && (
          <a href={`tel:${lead.owner_phone_1}`}
            className="flex items-center gap-1 text-xs text-gray-600 hover:text-[#1B3A5C] font-medium">
            <Phone className="h-3.5 w-3.5" /> {lead.owner_phone_1}
          </a>
        )}
        <button onClick={() => onSelect(lead)}
          className="ml-auto flex items-center gap-1 px-3 py-1.5 text-xs font-bold bg-[#1B3A5C] text-white rounded-lg hover:bg-[#152d47]">
          Open <ChevronDown className="h-3.5 w-3.5 -rotate-90" />
        </button>
      </div>
    </div>
  );
}

// ── Import modal ──────────────────────────────────────────────────────────────
export function LandLeadImportModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<Partial<LandLead>[]>([]);
  const preview = rows.slice(0, 5);
  const reference = useRef<string | null>(null);
  const fileRead = useRef(0);
  const [fileName, setFileName] = useState('');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<{ imported: number; existing: number; skipped: number } | null>(null);

  const importMutation = useMutation({
    retry: false,
    mutationFn: async () => {
      const valid = rows.filter(row => row.owner_name && row.property_address && row.city)
        .map(({ xleads_id, ...row }) => ({ ...row, ...(xleads_id ? { external_id: xleads_id } : {}) }));
      const requestId = reference.current;
      if (!valid.length || !requestId) throw new Error('No valid rows found');
      const response = await apiFetch('/api/land/imports', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, rows: valid }),
      });
      const saved = await response.json();
      const receipt = saved?.receipt, counts = receipt?.result;
      if (receipt?.id !== requestId || !Array.isArray(receipt?.payload)
          || receipt.payload.length !== valid.length
          || !valid.every((row, i) => Object.keys(row).length === Object.keys(receipt.payload[i] || {}).length
            && Object.entries(row).every(([key, value]) => receipt.payload[i][key] === value))
          || !counts || !Number.isInteger(counts.imported) || counts.imported < 0
          || !Number.isInteger(counts.existing) || counts.existing < 0
          || counts.imported + counts.existing !== valid.length || saved.outreach_authorized !== false) {
        throw new Error('The server did not confirm the original import receipt.');
      }
      return { imported: counts.imported as number, existing: counts.existing as number,
        skipped: rows.length - valid.length };
    },
    onSuccess: (saved) => { setResult(saved); setMessage(''); },
    onError: (error) => { setMessage(error.message); },
    onSettled: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ['land_leads'] }),
        qc.invalidateQueries({ queryKey: ['tasks'] })]);
    },
  });

  const handleFile = (file: File) => {
    if (importMutation.isPending) return;
    const read = ++fileRead.current;
    setFileName(file.name); setRows([]); setResult(null); setMessage(''); reference.current = null;
    Papa.parse(file, {
      header: true, skipEmptyLines: true,
      complete: (parsed) => {
        if (read !== fileRead.current) return;
        try {
          if (parsed.errors.length) throw new Error('The CSV could not be parsed. Review its columns and quoting.');
          const mapped = (parsed.data as Record<string, string>[]).map(mapXLeadsRow);
          if (!mapped.length || mapped.length > 10000) throw new Error('Select a CSV with 1 to 10,000 rows.');
          setRows(mapped); reference.current = crypto.randomUUID();
        } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not read CSV.'); }
      },
      error: (error) => { if (read === fileRead.current) setMessage(error.message); },
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl">
        <div className="flex items-center justify-between p-5 border-b">
          <div>
            <h2 className="text-base font-bold text-[#1B3A5C]">Import Land CSV</h2>
            <p className="text-xs text-gray-500 mt-0.5">Accepts PropStream or compatible CSV exports with matching columns</p>
          </div>
          <button onClick={onClose}><X className="h-5 w-5 text-gray-400 hover:text-gray-600" /></button>
        </div>

        <div className="p-5 space-y-4">
          {message && <p role="alert" className="text-sm text-red-700">{message} Review saved land records before retrying.</p>}
          {result ? (
            <div className="text-center py-8 space-y-2">
              <CheckCircle className="h-10 w-10 text-green-500 mx-auto" />
              <p className="font-bold text-gray-900">Import complete!</p>
              <p className="text-sm text-gray-600">{result.imported} leads imported · {result.existing} existing records preserved · {result.skipped} skipped (missing required fields)</p>
              <button onClick={onClose} className="mt-4 px-5 py-2 bg-[#1B3A5C] text-white text-sm font-bold rounded-lg">Done</button>
            </div>
          ) : (
            <>
              {/* Drop zone */}
              <div
                onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
                className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-[#1B3A5C] transition-colors">
                <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                <p className="text-sm font-medium text-gray-700">{fileName || 'Drop your CSV here or click to browse'}</p>
                <p className="text-xs text-gray-400 mt-1">Standard CSV · Up to 10,000 rows</p>
              </div>
              <input ref={fileRef} type="file" accept=".csv" className="hidden" disabled={importMutation.isPending}
                onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />

              {/* Column mapping reference */}
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-bold text-gray-600 mb-2">Supported column headers:</p>
                <div className="flex flex-wrap gap-1">
                  {Object.keys(XLEADS_MAP).map(col => (
                    <span key={col} className="text-xs bg-white border border-gray-200 px-2 py-0.5 rounded font-mono">{col}</span>
                  ))}
                </div>
              </div>

              {/* Preview */}
              {preview.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-bold text-gray-600">Preview (first 5 rows):</p>
                  <div className="overflow-x-auto rounded-lg border border-gray-200">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr>
                          {['Owner', 'Address', 'City', 'Acres', 'TAV'].map(h => (
                            <th key={h} className="px-3 py-2 text-left text-gray-500 font-semibold">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.map((row, i) => (
                          <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                            <td className="px-3 py-1.5">{row.owner_name ?? '—'}</td>
                            <td className="px-3 py-1.5">{row.property_address ?? '—'}</td>
                            <td className="px-3 py-1.5">{row.city ?? '—'}</td>
                            <td className="px-3 py-1.5">{row.lot_size_acres ?? '—'}</td>
                            <td className="px-3 py-1.5">{row.tav != null ? fmt(row.tav as number) : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <button onClick={() => { setMessage(''); importMutation.mutate(); }}
                    disabled={importMutation.isPending}
                    className="w-full py-2.5 bg-[#E8720C] text-white font-bold text-sm rounded-lg hover:bg-[#d4660b] disabled:opacity-60">
                    {importMutation.isPending ? 'Importing…' : message ? 'Retry original import' : `Import ${rows.length} leads`}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Detail drawer ─────────────────────────────────────────────────────────────
function LeadDrawer({ lead, onClose }: { lead: LandLead; onClose: () => void }) {
  const [drawerTab, setDrawerTab] = useState<'vetting' | 'comps' | 'buyers'>('vetting');
  return (
    <div className="fixed inset-0 bg-black/40 z-40 flex justify-end">
      <div className="w-full max-w-lg bg-white h-full flex flex-col shadow-2xl">
        {/* Drawer header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div>
            <p className="text-sm font-bold text-[#1B3A5C]">{lead.property_address}</p>
            <p className="text-xs text-gray-500">{lead.owner_name??'Owner not verified'} · {acr(lead.lot_size_acres)}</p>
          </div>
          <button onClick={onClose}><X className="h-5 w-5 text-gray-400 hover:text-gray-600" /></button>
        </div>
        {/* Drawer tabs */}
        <div className="flex border-b">
          {(['vetting', 'comps', 'buyers'] as const).map(t => (
            <button key={t} onClick={() => setDrawerTab(t)}
              className={`flex-1 py-2.5 text-xs font-bold capitalize transition-colors ${
                drawerTab === t ? 'border-b-2 border-[#E8720C] text-[#E8720C]' : 'text-gray-500 hover:text-gray-700'
              }`}>
              {t === 'vetting' ? '7 Musts' : t === 'comps' ? 'Quick-Comp' : 'Buyer Hub'}
            </button>
          ))}
        </div>
        {/* Drawer content */}
        <div className="flex-1 overflow-y-auto p-4">
          {drawerTab === 'vetting' && <SevenMustsForm lead={lead} existing={lead.vetting} onComplete={() => setDrawerTab('comps')} />}
          {drawerTab === 'comps'   && <QuickCompCalculator key={lead.id} lead={lead} existing={lead.comps} />}
          {drawerTab === 'buyers'  && <LandBuyerHub lead={lead} />}
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function LandLeads() {
  const [tab, setTab] = useState<Tab>('leads');
  const [selectedLead, setSelectedLead] = useState<LandLead | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [statusFilter, setStatusFilter] = useState<LandStatus | ''>('');

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const { data: allLeads, error, isPending, isFetching, refetch } = useLandLeads();
  const hasData = allLeads !== undefined;
  const searchTerm = search.trim().toLowerCase();
  const leads = (allLeads ?? []).filter(lead => (!statusFilter || lead.status === statusFilter)
    && (!searchTerm || [lead.property_address, lead.city, lead.owner_name, lead.apn].join(' ').toLowerCase().includes(searchTerm)));
  const eligible = tab === 'vetting' ? leads.filter(lead => !lead.vetting_passed && lead.status !== 'dead')
    : tab === 'comps' ? leads.filter(lead => lead.vetting_passed === true && lead.status !== 'dead') : leads;
  const pageSize = 25;
  const lastPage = Math.max(0, Math.ceil(eligible.length / pageSize) - 1);
  const visiblePage = Math.min(page, lastPage);
  const visibleLeads = eligible.slice(visiblePage * pageSize, (visiblePage + 1) * pageSize);

  async function openLinkedLand(id:string,leadId:string){
    const {data,error}=await supabase.from('land_leads').select('*').eq('id',id).eq('lead_id',leadId).single();
    if(error)throw error;
    if(!data||data.id!==id||data.lead_id!==leadId)throw new Error('Linked land record could not be confirmed.');
    setSelectedLead(data as LandLead);
  }
  const counts = allLeads ? {
    total:     allLeads.length,
    vetting:   allLeads.filter(l => l.status === 'vetting' || l.status === 'new').length,
    vetted:    allLeads.filter(l => l.vetting_passed === true).length,
    comped:    allLeads.filter(l => l.status === 'comped').length,
    contract:  allLeads.filter(l => l.status === 'under_contract').length,
    infill:    allLeads.filter(l => l.infill_lot === true).length,
  } : null;

  return (
    <div className="p-6 space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-green-100 rounded-xl">
            <TreePine className="h-6 w-6 text-green-700" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[#1B3A5C]">Vacant Land</h1>
            <p className="text-xs text-gray-500 mt-0.5">
              {counts ? <><span>{counts.total.toLocaleString('en-US')} leads · {counts.infill.toLocaleString('en-US')} infill lots · {counts.contract.toLocaleString('en-US')} under contract</span>
                {(error || isFetching) && <span> · Last confirmed refresh</span>}</> : error ? 'Land totals unavailable' : 'Loading land totals…'}
            </p>
          </div>
        </div>
        <button onClick={() => setShowImport(true)}
          className="flex items-center gap-2 px-4 py-2 bg-[#1B3A5C] text-white text-sm font-bold rounded-xl hover:bg-[#152d47]">
          <Upload className="h-4 w-4" /> Import CSV
        </button>
      </div>

      <LotInbox onOpen={openLinkedLand}/>
      {/* Funnel strip */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: 'Needs Vetting', value: counts?.vetting ?? '—',  color: 'bg-yellow-50 border-yellow-200 text-yellow-700' },
          { label: 'Passed Vetting', value: counts?.vetted ?? '—',  color: 'bg-blue-50 border-blue-200 text-blue-700' },
          { label: 'Comped',         value: counts?.comped ?? '—',  color: 'bg-purple-50 border-purple-200 text-purple-700' },
          { label: 'Under Contract', value: counts?.contract ?? '—',color: 'bg-green-50 border-green-200 text-green-700' },
          { label: 'Infill Lots',    value: counts?.infill ?? '—',  color: 'bg-orange-50 border-orange-200 text-orange-700' },
        ].map(({ label, value, color }) => (
          <div key={label} className={`rounded-xl border p-3 text-center ${color}`}>
            <p className="text-2xl font-black">{value}</p>
            <p className="text-xs font-medium mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => { setTab(t.id); setPage(0); }}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t.id ? 'bg-white text-[#1B3A5C] shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}>
              <Icon className="h-4 w-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p>Land records could not be loaded. {hasData ? 'Showing previously loaded records. ' : ''}{error.message}</p>
        <button onClick={() => { void refetch(); }} disabled={isFetching} className="mt-2 font-semibold underline disabled:opacity-50">Retry loading land records</button>
      </div>}
      {!hasData && isPending && <p role="status">Loading land records…</p>}
      {hasData && isFetching && <p role="status" className="text-sm text-gray-500">Refreshing land records…</p>}
      {hasData && tab !== 'buyers' && <div className="flex flex-wrap items-center gap-3">
        <input type="search" aria-label="Search land records" placeholder="Address, city, owner or parcel"
          value={search} onChange={event => { setSearch(event.target.value); setPage(0); }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <select aria-label="Land status" value={statusFilter}
          onChange={event => { setStatusFilter(event.target.value as LandStatus | ''); setPage(0); }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm">
          <option value="">All statuses</option><option value="new">New</option><option value="vetting">Vetting</option>
          <option value="vetted">Vetted</option><option value="comped">Comped</option><option value="offer_made">Offer Made</option>
          <option value="under_contract">Under Contract</option><option value="dead">Dead</option>
        </select>
        <span className="text-sm text-gray-500">{eligible.length.toLocaleString('en-US')} matching records</span>
      </div>}
      {hasData && tab !== 'buyers' && eligible.length > pageSize && <nav aria-label="Land record pages" className="flex items-center gap-4 text-sm">
        <button aria-label="Previous land page" disabled={visiblePage === 0} onClick={() => setPage(visiblePage - 1)} className="font-semibold disabled:opacity-40">Previous</button>
        <span>{(visiblePage * pageSize + 1).toLocaleString('en-US')}–{Math.min((visiblePage + 1) * pageSize, eligible.length).toLocaleString('en-US')} of {eligible.length.toLocaleString('en-US')}</span>
        <button aria-label="Next land page" disabled={visiblePage === lastPage} onClick={() => setPage(visiblePage + 1)} className="font-semibold disabled:opacity-40">Next</button>
      </nav>}

      {/* Tab content */}
      {hasData && tab === 'leads' && (
        <div className="space-y-4">
          {leads.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <TreePine className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm font-medium">{searchTerm || statusFilter ? 'No matching land leads' : error ? 'No records in the last confirmed refresh' : 'No land leads yet'}</p>
              <p className="text-xs mt-1">Import a CSV or add manually</p>
              <button onClick={() => setShowImport(true)}
                className="mt-4 px-4 py-2 bg-[#1B3A5C] text-white text-sm font-bold rounded-lg">
                Import CSV
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {visibleLeads.map(lead => (
                <LandLeadCard key={lead.id} lead={lead} onSelect={setSelectedLead} />
              ))}
            </div>
          )}
        </div>
      )}

      {hasData && tab === 'vetting' && (
        <div>
          {eligible.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <CheckCircle className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No leads awaiting vetting</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {visibleLeads.map(lead => (
                <div key={lead.id} className="bg-white rounded-xl border border-yellow-200 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <p className="text-sm font-bold text-gray-900">{lead.property_address}</p>
                      <p className="text-xs text-gray-500">{lead.owner_name??'Owner not verified'} · {acr(lead.lot_size_acres)}</p>
                    </div>
                    <Clock className="h-4 w-4 text-yellow-500" />
                  </div>
                  <SevenMustsForm lead={lead} existing={lead.vetting} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {hasData && tab === 'comps' && (
        <div>
          {eligible.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <DollarSign className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No vetted leads ready for comping</p>
              <p className="text-xs mt-1">Complete 7 Musts vetting first</p>
            </div>
          ) : (
            <div className="space-y-6">
              {visibleLeads.map(lead => (
                <div key={lead.id} className="bg-white rounded-xl border border-gray-200 p-5">
                  <div className="flex items-center gap-2 mb-4 pb-3 border-b border-gray-100">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <p className="text-sm font-bold text-gray-900">{lead.property_address}</p>
                    <span className="text-xs text-gray-400">· {lead.owner_name??'Owner not verified'} · {acr(lead.lot_size_acres)}</span>
                  </div>
                  <QuickCompCalculator key={lead.id} lead={lead} existing={lead.comps} />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'buyers' && <LandBuyerHub />}

      {/* Lead detail drawer */}
      {selectedLead && (
        <LeadDrawer lead={selectedLead} onClose={() => setSelectedLead(null)} />
      )}

      {/* Import modal */}
      {showImport && <LandLeadImportModal onClose={() => setShowImport(false)} />}
    </div>
  );
}
