import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useLeads, useDeleteLead, useCreateLead, useUpdateLead, useLogActivity } from '@/hooks/useLeads';
import { useLeadQualifier } from '@/hooks/useAIAgent';
import { useCreateDeal } from '@/hooks/useDeals';
import { OutreachTimeline } from '@/components/leads/OutreachTimeline';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { TableSkeleton } from '@/components/ui/skeleton';
import type { Lead } from '@/types';
import {
  formatDate, phoneFormat, getStatusClass, getStatusLabel,
  getScoreBadgeClass, truncate
} from '@/lib/utils';
import { cn } from '@/lib/utils';
import {
  Plus, Upload, Search, ChevronDown, ChevronLeft, ChevronRight,
  MoreHorizontal, Trash2, Bot, ArrowRight, Phone, Mail,
  MessageSquare, Eye, Ban
} from 'lucide-react';
import { toast } from 'sonner';
import Papa from 'papaparse';
import { supabase } from '@/lib/supabase';

const STATUS_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'new', label: 'New' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'responding', label: 'Responding' },
  { value: 'qualified_hot', label: 'Hot' },
  { value: 'qualified_warm', label: 'Warm' },
  { value: 'qualified_cold', label: 'Cold' },
  { value: 'offer_made', label: 'Offer Made' },
  { value: 'under_contract', label: 'Under Contract' },
  { value: 'dead', label: 'Dead' },
];

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'propstream', label: 'PropStream' },
  { value: 'batchleads', label: 'BatchLeads' },
  { value: 'facebook_ad', label: 'Facebook Ad' },
  { value: 'driving', label: 'Driving for $' },
  { value: 'referral', label: 'Referral' },
  { value: 'other', label: 'Other' },
];

const MOTIVATION_OPTIONS = [
  { value: '', label: 'All Motivations' },
  { value: 'absentee', label: 'Absentee' },
  { value: 'tax_delinquent', label: 'Tax Delinquent' },
  { value: 'pre_foreclosure', label: 'Pre-Foreclosure' },
  { value: 'probate', label: 'Probate' },
  { value: 'inherited', label: 'Inherited' },
  { value: 'vacant', label: 'Vacant' },
  { value: 'high_equity', label: 'High Equity' },
];

export function Leads() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [source, setSource] = useState('');
  const [motivation, setMotivation] = useState('');
  const [page, setPage] = useState(1);
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [detailLead, setDetailLead] = useState<Lead | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const { data, isLoading } = useLeads({ status, source, search, page, pageSize: 50 });
  const leads = data?.data ?? [];
  const total = data?.count ?? 0;
  const totalPages = Math.ceil(total / 50);

  const deleteLead = useDeleteLead();
  const createDeal = useCreateDeal();
  const [logActivityLead, setLogActivityLead] = useState<Lead | null>(null);

  const handleMoveToPipeline = async (lead: Lead) => {
    if (!confirm(`Create a pipeline deal for ${lead.property_address}?`)) return;
    await createDeal.mutateAsync({
      lead_id: lead.id,
      deal_name: lead.property_address,
      stage: 'offer_made',
      contract_price: lead.offer_price ?? lead.mao ?? undefined,
      arv: lead.estimated_arv ?? undefined,
      repair_estimate: lead.estimated_repairs ?? undefined,
      seller_name: `${lead.owner_first_name ?? ''} ${lead.owner_last_name ?? ''}`.trim() || undefined,
    });
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Leads</h1>
          <p className="text-sm text-gray-500 mt-0.5">{total} total leads</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" icon={<Upload className="h-4 w-4" />} onClick={() => setImportOpen(true)}>
            Import CSV
          </Button>
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAddOpen(true)}>
            Add Lead
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap items-center">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            placeholder="Search address, name, phone..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-[#1B3A5C]"
          />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} options={STATUS_OPTIONS} className="w-40" />
        <Select value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }} options={SOURCE_OPTIONS} className="w-36" />
        <Select value={motivation} onChange={(e) => { setMotivation(e.target.value); setPage(1); }} options={MOTIVATION_OPTIONS} className="w-40" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                {['Address', 'Owner', 'Phone', 'Source', 'Motivation', 'Score', 'Status', 'Last Contact', 'Next Follow-up', ''].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {isLoading ? (
                <tr><td colSpan={10} className="px-4 py-6"><TableSkeleton rows={8} cols={8} /></td></tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-16 text-center">
                    <div className="flex flex-col items-center gap-2 text-gray-400">
                      <Search className="h-10 w-10 opacity-30" />
                      <p className="font-medium">No leads found</p>
                      <p className="text-xs">Try adjusting your filters or import a CSV</p>
                    </div>
                  </td>
                </tr>
              ) : leads.map((lead) => (
                <tr key={lead.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => setDetailLead(lead)}>
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900 truncate max-w-48">{lead.property_address}</p>
                    <p className="text-xs text-gray-400">{lead.city}, {lead.state} {lead.zip_code}</p>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {lead.owner_first_name || lead.owner_last_name
                      ? `${lead.owner_first_name || ''} ${lead.owner_last_name || ''}`.trim()
                      : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-600">
                    {phoneFormat(lead.owner_phone_1) || <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {lead.source
                      ? <span className="capitalize text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{lead.source.replace(/_/g, ' ')}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {lead.motivation_tag
                      ? <span className="capitalize text-xs bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">{lead.motivation_tag.replace(/_/g, ' ')}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-bold', getScoreBadgeClass(lead.total_score))}>
                      {lead.total_score ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-medium', getStatusClass(lead.status))}>
                      {getStatusLabel(lead.status)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDate(lead.last_contact_date) || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDate(lead.next_follow_up_date) || '—'}
                  </td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="relative">
                      <button
                        onClick={() => setOpenMenuId(openMenuId === lead.id ? null : lead.id)}
                        className="p-1 rounded hover:bg-gray-100 text-gray-400"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {openMenuId === lead.id && (
                        <div className="absolute right-0 top-8 z-10 w-44 bg-white border border-gray-200 rounded-lg shadow-lg py-1">
                          <button className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50" onClick={() => { setDetailLead(lead); setOpenMenuId(null); }}>
                            <Eye className="h-3.5 w-3.5" /> View / Edit
                          </button>
                          <button className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                            onClick={() => { handleMoveToPipeline(lead); setOpenMenuId(null); }}>
                            <ArrowRight className="h-3.5 w-3.5" /> Move to Pipeline
                          </button>
                          <button className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                            onClick={() => { setLogActivityLead(lead); setOpenMenuId(null); }}>
                            <Phone className="h-3.5 w-3.5" /> Log Activity
                          </button>
                          <button className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50" onClick={() => { if (confirm('Delete this lead?')) deleteLead.mutate(lead.id); setOpenMenuId(null); }}>
                            <Trash2 className="h-3.5 w-3.5" /> Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-gray-200 flex items-center justify-between">
            <p className="text-xs text-gray-500">
              Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, total)} of {total}
            </p>
            <div className="flex gap-1">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="p-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="p-1.5 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      <LeadFormModal open={addOpen} onClose={() => setAddOpen(false)} />
      <ImportCSVModal open={importOpen} onClose={() => setImportOpen(false)} />
      {logActivityLead && (
        <LogActivityModal lead={logActivityLead} onClose={() => setLogActivityLead(null)} />
      )}
      {detailLead && (
        <LeadDetailDrawer lead={detailLead} onClose={() => setDetailLead(null)} />
      )}
    </div>
  );
}

// ─── Lead Form Modal ──────────────────────────────────────────────────────────
function LeadFormModal({ open, onClose, lead }: { open: boolean; onClose: () => void; lead?: Lead }) {
  const createLead = useCreateLead();
  const updateLead = useUpdateLead();
  const isEdit = !!lead;

  const [form, setForm] = useState({
    property_address: lead?.property_address || '',
    city: lead?.city || '',
    state: lead?.state || 'TX',
    zip_code: lead?.zip_code || '',
    property_type: lead?.property_type || 'SFR',
    bedrooms: lead?.bedrooms || '',
    bathrooms: lead?.bathrooms || '',
    sqft: lead?.sqft || '',
    owner_first_name: lead?.owner_first_name || '',
    owner_last_name: lead?.owner_last_name || '',
    owner_phone_1: lead?.owner_phone_1 || '',
    owner_email: lead?.owner_email || '',
    source: lead?.source || '',
    motivation_tag: lead?.motivation_tag || '',
    status: lead?.status || 'new',
    asking_price: lead?.asking_price || '',
    estimated_equity_pct: lead?.estimated_equity_pct || '',
    seller_notes: lead?.seller_notes || '',
  });

  const set = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.property_address || !form.city) return toast.error('Address and city required');
    if (isEdit && lead) {
      await updateLead.mutateAsync({ id: lead.id, updates: form as Partial<Lead> });
    } else {
      await createLead.mutateAsync(form as Partial<Lead>);
    }
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? 'Edit Lead' : 'Add Lead'} size="xl">
      <form onSubmit={handleSubmit} className="p-6 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Input label="Property Address *" value={form.property_address} onChange={(e) => set('property_address', e.target.value)} />
          </div>
          <Input label="City *" value={form.city} onChange={(e) => set('city', e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <Input label="State" value={form.state} onChange={(e) => set('state', e.target.value)} />
            <Input label="Zip Code" value={form.zip_code} onChange={(e) => set('zip_code', e.target.value)} />
          </div>
          <Input label="Beds" type="number" value={form.bedrooms} onChange={(e) => set('bedrooms', e.target.value)} />
          <Input label="Baths" type="number" step="0.5" value={form.bathrooms} onChange={(e) => set('bathrooms', e.target.value)} />
          <Input label="Sqft" type="number" value={form.sqft} onChange={(e) => set('sqft', e.target.value)} />
          <Select label="Property Type" value={form.property_type} onChange={(e) => set('property_type', e.target.value)}
            options={[{value:'SFR',label:'SFR'},{value:'duplex',label:'Duplex'},{value:'MFR',label:'MFR'},{value:'land',label:'Land'}]} />
        </div>
        <hr className="border-gray-100" />
        <div className="grid grid-cols-2 gap-4">
          <Input label="Owner First Name" value={form.owner_first_name} onChange={(e) => set('owner_first_name', e.target.value)} />
          <Input label="Owner Last Name" value={form.owner_last_name} onChange={(e) => set('owner_last_name', e.target.value)} />
          <Input label="Phone 1" type="tel" value={form.owner_phone_1} onChange={(e) => set('owner_phone_1', e.target.value)} />
          <Input label="Email" type="email" value={form.owner_email} onChange={(e) => set('owner_email', e.target.value)} />
          <Select label="Source" value={form.source} onChange={(e) => set('source', e.target.value)}
            options={SOURCE_OPTIONS.filter(o => o.value)} placeholder="Select source" />
          <Select label="Motivation" value={form.motivation_tag} onChange={(e) => set('motivation_tag', e.target.value)}
            options={MOTIVATION_OPTIONS.filter(o => o.value)} placeholder="Select motivation" />
          <Input label="Asking Price" type="number" value={form.asking_price} onChange={(e) => set('asking_price', e.target.value)} />
          <Input label="Est. Equity %" type="number" value={form.estimated_equity_pct} onChange={(e) => set('estimated_equity_pct', e.target.value)} />
          <Select label="Status" value={form.status} onChange={(e) => set('status', e.target.value)}
            options={STATUS_OPTIONS.filter(o => o.value)} />
        </div>
        <Textarea label="Seller Notes" value={form.seller_notes} onChange={(e) => set('seller_notes', e.target.value)} rows={3} />
        <div className="flex justify-end gap-3">
          <Button variant="outline" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={createLead.isPending || updateLead.isPending}>
            {isEdit ? 'Save Changes' : 'Add Lead'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ─── Import CSV Modal ─────────────────────────────────────────────────────────
function ImportCSVModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string[][]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ imported: number; errors: number } | null>(null);

  const DB_FIELDS = [
    'property_address', 'city', 'state', 'zip_code', 'owner_first_name',
    'owner_last_name', 'owner_phone_1', 'owner_email', 'source', 'motivation_tag',
    'bedrooms', 'bathrooms', 'sqft', 'asking_price',
  ];

  const [mapping, setMapping] = useState<Record<string, string>>({});

  const handleFile = (f: File) => {
    setFile(f);
    Papa.parse(f, {
      header: false,
      preview: 6,
      complete: (res) => {
        const rows = res.data as string[][];
        if (rows.length > 0) {
          setHeaders(rows[0]);
          setPreview(rows.slice(1, 5));
          // Auto-map common headers
          const autoMap: Record<string, string> = {};
          rows[0].forEach((h, i) => {
            const normalized = h.toLowerCase().replace(/[^a-z0-9]/g, '_');
            if (DB_FIELDS.includes(normalized)) autoMap[normalized] = String(i);
            if (normalized.includes('address') && !autoMap['property_address']) autoMap['property_address'] = String(i);
            if (normalized.includes('first') && !autoMap['owner_first_name']) autoMap['owner_first_name'] = String(i);
            if (normalized.includes('last') && !autoMap['owner_last_name']) autoMap['owner_last_name'] = String(i);
            if (normalized.includes('phone') && !autoMap['owner_phone_1']) autoMap['owner_phone_1'] = String(i);
            if (normalized.includes('city') && !autoMap['city']) autoMap['city'] = String(i);
            if (normalized.includes('zip') && !autoMap['zip_code']) autoMap['zip_code'] = String(i);
          });
          setMapping(autoMap);
        }
      },
    });
  };

  const handleImport = async () => {
    if (!file || !mapping['property_address'] || !mapping['city']) {
      toast.error('Must map "property_address" and "city" columns');
      return;
    }
    setImporting(true);
    let imported = 0, errors = 0;

    await new Promise<void>((resolve) => {
      Papa.parse(file, {
        header: false,
        skipEmptyLines: true,
        complete: async (res) => {
          const rows = (res.data as string[][]).slice(1);
          const CHUNK = 100;
          for (let i = 0; i < rows.length; i += CHUNK) {
            const chunk = rows.slice(i, i + CHUNK).map((row) => {
              const record: Record<string, string | number> = { status: 'new', state: 'TX' };
              Object.entries(mapping).forEach(([field, colIdx]) => {
                const val = row[Number(colIdx)]?.trim();
                if (val) record[field] = val;
              });
              return record;
            }).filter((r) => r.property_address && r.city);
            const { error } = await supabase.from('leads').insert(chunk);
            if (error) errors += chunk.length;
            else imported += chunk.length;
          }
          resolve();
        },
      });
    });

    setImporting(false);
    setResult({ imported, errors });
  };

  return (
    <Modal open={open} onClose={() => { onClose(); setFile(null); setResult(null); }} title="Import Leads from CSV" size="xl">
      <div className="p-6 space-y-5">
        {result ? (
          <div className="text-center py-8 space-y-3">
            <div className="text-5xl">✅</div>
            <p className="text-xl font-bold text-gray-900">{result.imported} leads imported</p>
            {result.errors > 0 && <p className="text-sm text-red-500">{result.errors} rows had errors</p>}
            <Button onClick={() => { onClose(); setFile(null); setResult(null); }}>Done</Button>
          </div>
        ) : (
          <>
            {/* Drop zone */}
            <div
              className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center hover:border-[#1B3A5C] transition-colors cursor-pointer"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
              onClick={() => document.getElementById('csv-input')?.click()}
            >
              <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
              <p className="font-medium text-gray-700">{file ? file.name : 'Drop CSV here or click to browse'}</p>
              <p className="text-xs text-gray-400 mt-1">CSV format, any column order</p>
              <input id="csv-input" type="file" accept=".csv" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
            </div>

            {headers.length > 0 && (
              <>
                {/* Column mapping */}
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-2">Map CSV columns to database fields</p>
                  <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                    {DB_FIELDS.map((field) => (
                      <div key={field} className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 w-36 shrink-0">{field}</span>
                        <select
                          value={mapping[field] ?? ''}
                          onChange={(e) => setMapping({ ...mapping, [field]: e.target.value })}
                          className="flex-1 border border-gray-300 rounded px-2 py-1 text-xs"
                        >
                          <option value="">— skip —</option>
                          {headers.map((h, i) => (
                            <option key={i} value={String(i)}>{h} (col {i + 1})</option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Preview */}
                {preview.length > 0 && (
                  <div className="overflow-x-auto rounded-lg border border-gray-200">
                    <table className="text-xs">
                      <thead>
                        <tr className="bg-gray-50">{headers.map((h, i) => <th key={i} className="px-2 py-1.5 text-left border-b border-gray-200 whitespace-nowrap">{h}</th>)}</tr>
                      </thead>
                      <tbody>
                        {preview.map((row, i) => (
                          <tr key={i} className="border-b border-gray-100">
                            {row.map((cell, j) => <td key={j} className="px-2 py-1.5 whitespace-nowrap truncate max-w-24">{cell}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="flex justify-end gap-3">
                  <Button variant="outline" onClick={onClose}>Cancel</Button>
                  <Button onClick={handleImport} loading={importing} icon={<Upload className="h-4 w-4" />}>
                    Import {file ? '' : 'CSV'}
                  </Button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

// ─── Lead Detail Drawer ───────────────────────────────────────────────────────
function LeadDetailDrawer({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const updateLead = useUpdateLead();
  const { qualify, loading: aiLoading, result: aiResult } = useLeadQualifier();
  const [form, setForm] = useState<Partial<Lead>>(lead);
  const [activeTab, setActiveTab] = useState<'details' | 'timeline'>('details');
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const handleSave = async () => {
    await updateLead.mutateAsync({ id: lead.id, updates: form });
    onClose();
  };

  const handleQualify = () =>
    qualify({
      lead_id: lead.id,
      property_address: lead.property_address,
      seller_notes: form.seller_notes || '',
      estimated_equity_pct: form.estimated_equity_pct,
    });

  return (
    <Modal open={true} onClose={onClose} title={lead.property_address} size="2xl">
      <div className="p-6">
        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-6">
          {(['details', 'timeline'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
                activeTab === tab
                  ? 'border-[#1B3A5C] text-[#1B3A5C]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              {tab === 'timeline' ? 'Activity Timeline' : 'Details'}
            </button>
          ))}
        </div>
        {activeTab === 'details' && (<div className="space-y-6">
        {/* Scores */}
        <div className="bg-gray-50 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-gray-700">Qualification Score</p>
            <span className={cn('px-3 py-1 rounded-full text-sm font-bold', getScoreBadgeClass(form.total_score))}>
              {form.total_score ?? 0} / 15
            </span>
          </div>
          <div className="grid grid-cols-5 gap-3">
            {[
              ['Motivation', 'score_motivation'],
              ['Timeline', 'score_timeline'],
              ['Equity', 'score_equity'],
              ['Condition', 'score_condition'],
              ['Flexibility', 'score_flexibility'],
            ].map(([label, key]) => (
              <div key={key} className="text-center">
                <p className="text-xs text-gray-500 mb-1">{label}</p>
                <div className="flex gap-1 justify-center">
                  {[1, 2, 3].map((v) => (
                    <button key={v} onClick={() => set(key, v)}
                      className={cn('w-7 h-7 rounded text-xs font-bold border transition-colors',
                        (form as Record<string, unknown>)[key] === v
                          ? 'bg-[#1B3A5C] text-white border-[#1B3A5C]'
                          : 'bg-white text-gray-400 border-gray-300 hover:border-[#1B3A5C]'
                      )}>
                      {v}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Property + Owner */}
        <div className="grid grid-cols-2 gap-4">
          <Input label="Property Address" value={form.property_address || ''} onChange={(e) => set('property_address', e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <Input label="City" value={form.city || ''} onChange={(e) => set('city', e.target.value)} />
            <Input label="Zip" value={form.zip_code || ''} onChange={(e) => set('zip_code', e.target.value)} />
          </div>
          <Input label="Owner First" value={form.owner_first_name || ''} onChange={(e) => set('owner_first_name', e.target.value)} />
          <Input label="Owner Last" value={form.owner_last_name || ''} onChange={(e) => set('owner_last_name', e.target.value)} />
          <Input label="Phone 1" value={form.owner_phone_1 || ''} onChange={(e) => set('owner_phone_1', e.target.value)} />
          <Input label="Email" value={form.owner_email || ''} onChange={(e) => set('owner_email', e.target.value)} />
          <Select label="Status" value={form.status || 'new'} onChange={(e) => set('status', e.target.value)}
            options={STATUS_OPTIONS.filter(o => o.value)} />
          <Select label="Motivation" value={form.motivation_tag || ''} onChange={(e) => set('motivation_tag', e.target.value)}
            options={MOTIVATION_OPTIONS.filter(o => o.value)} placeholder="Select motivation" />
          <Input label="Asking Price" type="number" value={form.asking_price || ''} onChange={(e) => set('asking_price', Number(e.target.value))} />
          <Input label="Est. Equity %" type="number" value={form.estimated_equity_pct || ''} onChange={(e) => set('estimated_equity_pct', Number(e.target.value))} />
          <Input label="Next Follow-up" type="date" value={form.next_follow_up_date || ''} onChange={(e) => set('next_follow_up_date', e.target.value)} />
        </div>

        <Textarea label="Seller Notes" value={form.seller_notes || ''} onChange={(e) => set('seller_notes', e.target.value)} rows={3} />
        <Textarea label="Internal Notes" value={form.internal_notes || ''} onChange={(e) => set('internal_notes', e.target.value)} rows={2} />

        {/* AI Qualifier */}
        <div className="border border-gray-200 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <Bot className="h-4 w-4 text-[#E8720C]" /> AI Qualifier
            </p>
            <Button size="sm" variant="secondary" onClick={handleQualify} loading={aiLoading}>
              Run Qualifier
            </Button>
          </div>
          {(aiResult || form.ai_qualification_summary) && (
            <div className="bg-orange-50 rounded-lg p-3 space-y-2">
              {aiResult && (
                <div className="flex gap-2">
                  <span className={cn('px-2 py-0.5 rounded text-xs font-bold',
                    aiResult.tier === 'HOT' ? 'bg-red-100 text-red-700' :
                    aiResult.tier === 'WARM' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-blue-100 text-blue-700'
                  )}>
                    {aiResult.tier}
                  </span>
                  <span className="text-xs text-gray-600">Score: {aiResult.total_score}/15</span>
                </div>
              )}
              <p className="text-xs text-gray-700">{aiResult?.qualification_summary || form.ai_qualification_summary}</p>
              {aiResult?.recommended_next_action && (
                <p className="text-xs font-medium text-[#1B3A5C]">→ {aiResult.recommended_next_action}</p>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} loading={updateLead.isPending}>Save Changes</Button>
        </div>
        </div>)}
        {activeTab === 'timeline' && (
          <OutreachTimeline leadId={lead.id} />
        )}
      </div>
    </Modal>
  );
}

function LogActivityModal({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const logActivity = useLogActivity();
  const [form, setForm] = useState({
    channel: 'call',
    direction: 'outbound',
    status: 'answered',
    message: '',
    response: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await logActivity.mutateAsync({
      lead_id: lead.id,
      channel: form.channel,
      direction: form.direction,
      status: form.status,
      message: form.message || undefined,
      response: form.response || undefined,
    });
    onClose();
  };

  return (
    <Modal open={true} onClose={onClose} title={`Log Activity — ${lead.property_address}`} size="md">
      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Select label="Channel" value={form.channel}
            onChange={(e) => setForm({ ...form, channel: e.target.value })}
            options={[
              { value: 'call', label: 'Call' },
              { value: 'sms', label: 'SMS' },
              { value: 'email', label: 'Email' },
              { value: 'voicemail', label: 'Voicemail' },
              { value: 'direct_mail', label: 'Direct Mail' },
              { value: 'in_person', label: 'In Person' },
            ]} />
          <Select label="Direction" value={form.direction}
            onChange={(e) => setForm({ ...form, direction: e.target.value })}
            options={[
              { value: 'outbound', label: 'Outbound' },
              { value: 'inbound', label: 'Inbound' },
            ]} />
          <Select label="Status" value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
            options={[
              { value: 'answered', label: 'Answered' },
              { value: 'no_answer', label: 'No Answer' },
              { value: 'voicemail', label: 'Left Voicemail' },
              { value: 'sent', label: 'Sent' },
              { value: 'delivered', label: 'Delivered' },
            ]} />
        </div>
        <Textarea label="Message / Notes" value={form.message}
          onChange={(e) => setForm({ ...form, message: e.target.value })}
          placeholder="What was said or sent..." rows={3} />
        <Textarea label="Seller Response (if any)" value={form.response}
          onChange={(e) => setForm({ ...form, response: e.target.value })}
          placeholder="What the seller said back..." rows={2} />
        <div className="flex justify-end gap-3">
          <Button variant="outline" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={logActivity.isPending}>Log Activity</Button>
        </div>
      </form>
    </Modal>
  );
}
