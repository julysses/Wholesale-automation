import { useState } from 'react';
import { useBuyers, useCreateBuyer, useUpdateBuyer, useDeleteBuyer } from '@/hooks/useBuyers';
import { useBuyerMatcher } from '@/hooks/useAIAgent';
import { useDeals } from '@/hooks/useDeals';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { TableSkeleton } from '@/components/ui/skeleton';
import type { Buyer } from '@/types';
import { getTierClass, phoneFormat, formatDate, formatCurrency } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { Plus, Search, MoreHorizontal, Trash2, Edit, Bot } from 'lucide-react';
import { toast } from 'sonner';

const STRATEGY_OPTIONS = ['fix_flip', 'buy_hold', 'brrrr', 'str'];
const PROPERTY_TYPE_OPTIONS = ['SFR', 'duplex', 'MFR', 'land', 'condo'];
const SOURCE_OPTIONS = [
  { value: 'rei_meetup', label: 'REI Meetup' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'biggerpockets', label: 'BiggerPockets' },
  { value: 'referral', label: 'Referral' },
  { value: 'title_co', label: 'Title Company' },
  { value: 'linkedin', label: 'LinkedIn' },
];

export function Buyers() {
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [editBuyer, setEditBuyer] = useState<Buyer | null>(null);
  const [matchOpen, setMatchOpen] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const { data: buyers = [], isLoading } = useBuyers({ search, tier: tier || undefined });
  const deleteBuyer = useDeleteBuyer();

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Buyers</h1>
          <p className="text-sm text-gray-500 mt-0.5">{buyers.length} buyers in database</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" icon={<Bot className="h-4 w-4" />} onClick={() => setMatchOpen(true)}>
            Blast New Deal
          </Button>
          <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setAddOpen(true)}>
            Add Buyer
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search buyers..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-[#1B3A5C]"
          />
        </div>
        <Select value={tier} onChange={(e) => setTier(e.target.value)}
          options={[{ value: '', label: 'All Tiers' }, { value: 'A', label: 'Tier A' }, { value: 'B', label: 'Tier B' }, { value: 'C', label: 'Tier C' }]}
          className="w-32" />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                {['Name', 'Company', 'Phone', 'Email', 'Tier', 'Strategy', 'Zip Targets', 'Max Price', 'Close Speed', 'POF', 'Deals', 'Last Contact', ''].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {isLoading ? (
                <tr><td colSpan={13} className="px-4 py-6"><TableSkeleton rows={6} cols={7} /></td></tr>
              ) : buyers.length === 0 ? (
                <tr>
                  <td colSpan={13} className="px-4 py-16 text-center">
                    <p className="text-gray-400 font-medium">No buyers found</p>
                    <p className="text-xs text-gray-300 mt-1">Add your first buyer to get started</p>
                  </td>
                </tr>
              ) : buyers.map((buyer) => (
                <tr key={buyer.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900 whitespace-nowrap">
                    {buyer.first_name} {buyer.last_name}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{buyer.company || '—'}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{phoneFormat(buyer.phone)}</td>
                  <td className="px-4 py-3 text-gray-600 truncate max-w-32">{buyer.email || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-bold', getTierClass(buyer.tier))}>
                      {buyer.tier}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 flex-wrap">
                      {(buyer.strategy || []).map((s) => (
                        <span key={s} className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded uppercase">{s}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {(buyer.target_zips || []).slice(0, 3).join(', ')}{(buyer.target_zips?.length || 0) > 3 ? '…' : ''}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-600">{buyer.max_price ? formatCurrency(buyer.max_price) : '—'}</td>
                  <td className="px-4 py-3 text-gray-600">{buyer.close_speed_days ? `${buyer.close_speed_days}d` : '—'}</td>
                  <td className="px-4 py-3">
                    {buyer.pof_verified
                      ? <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">✓ Verified</span>
                      : <span className="text-xs text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-center font-semibold text-gray-700">{buyer.deals_closed}</td>
                  <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{formatDate(buyer.last_contact_date)}</td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="relative">
                      <button onClick={() => setOpenMenuId(openMenuId === buyer.id ? null : buyer.id)}
                        className="p-1 rounded hover:bg-gray-100 text-gray-400">
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {openMenuId === buyer.id && (
                        <div className="absolute right-0 top-8 z-10 w-36 bg-white border border-gray-200 rounded-lg shadow-lg py-1">
                          <button className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                            onClick={() => { setEditBuyer(buyer); setOpenMenuId(null); }}>
                            <Edit className="h-3.5 w-3.5" /> Edit
                          </button>
                          <button className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                            onClick={() => { if (confirm('Delete buyer?')) deleteBuyer.mutate(buyer.id); setOpenMenuId(null); }}>
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
      </div>

      <BuyerFormModal open={addOpen || !!editBuyer} buyer={editBuyer} onClose={() => { setAddOpen(false); setEditBuyer(null); }} />
      <BuyerMatchModal open={matchOpen} onClose={() => setMatchOpen(false)} />
    </div>
  );
}

// ─── Buyer Form Modal ─────────────────────────────────────────────────────────
function BuyerFormModal({ open, onClose, buyer }: { open: boolean; onClose: () => void; buyer?: Buyer | null }) {
  const createBuyer = useCreateBuyer();
  const updateBuyer = useUpdateBuyer();
  const isEdit = !!buyer;

  const [form, setForm] = useState({
    first_name: buyer?.first_name || '',
    last_name: buyer?.last_name || '',
    company: buyer?.company || '',
    email: buyer?.email || '',
    phone: buyer?.phone || '',
    source: buyer?.source || '',
    tier: buyer?.tier || 'C',
    target_zips_str: (buyer?.target_zips || []).join(', '),
    min_price: buyer?.min_price || '',
    max_price: buyer?.max_price || '',
    strategy: buyer?.strategy || [] as string[],
    property_types: buyer?.property_types || [] as string[],
    close_speed_days: buyer?.close_speed_days || '',
    pof_verified: buyer?.pof_verified || false,
    pof_amount: buyer?.pof_amount || '',
    notes: buyer?.notes || '',
  });

  const toggleArr = (key: 'strategy' | 'property_types', val: string) => {
    setForm((f) => ({
      ...f,
      [key]: f[key].includes(val) ? f[key].filter((v) => v !== val) : [...f[key], val],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.first_name || !form.last_name) return toast.error('Name required');
    const payload = {
      ...form,
      target_zips: form.target_zips_str.split(',').map((z) => z.trim()).filter(Boolean),
      min_price: form.min_price ? Number(form.min_price) : null,
      max_price: form.max_price ? Number(form.max_price) : null,
      close_speed_days: form.close_speed_days ? Number(form.close_speed_days) : null,
      pof_amount: form.pof_amount ? Number(form.pof_amount) : null,
    };
    if (isEdit && buyer) {
      await updateBuyer.mutateAsync({ id: buyer.id, updates: payload as Partial<Buyer> });
    } else {
      await createBuyer.mutateAsync(payload as Partial<Buyer>);
    }
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={isEdit ? 'Edit Buyer' : 'Add Buyer'} size="xl">
      <form onSubmit={handleSubmit} className="p-6 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <Input label="First Name *" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          <Input label="Last Name *" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          <Input label="Company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
          <Select label="Source" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}
            options={SOURCE_OPTIONS} placeholder="Select source" />
          <Input label="Phone" type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <Input label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>

        <Input label="Target Zip Codes (comma-separated)" value={form.target_zips_str}
          onChange={(e) => setForm({ ...form, target_zips_str: e.target.value })}
          placeholder="75001, 75002, 75006" />

        <div className="grid grid-cols-3 gap-4">
          <Input label="Min Price" type="number" value={form.min_price} onChange={(e) => setForm({ ...form, min_price: e.target.value })} />
          <Input label="Max Price" type="number" value={form.max_price} onChange={(e) => setForm({ ...form, max_price: e.target.value })} />
          <Input label="Close Speed (days)" type="number" value={form.close_speed_days} onChange={(e) => setForm({ ...form, close_speed_days: e.target.value })} />
          <Select label="Tier" value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })}
            options={[{ value: 'A', label: 'A — Closed with us' }, { value: 'B', label: 'B — Active' }, { value: 'C', label: 'C — Inquired' }]} />
          <Input label="POF Amount" type="number" value={form.pof_amount} onChange={(e) => setForm({ ...form, pof_amount: e.target.value })} />
          <div className="flex items-center gap-2 pt-6">
            <input type="checkbox" id="pof-verified" checked={form.pof_verified}
              onChange={(e) => setForm({ ...form, pof_verified: e.target.checked })}
              className="w-4 h-4 rounded border-gray-300" />
            <label htmlFor="pof-verified" className="text-sm text-gray-700">POF Verified</label>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">Strategy</p>
          <div className="flex gap-2 flex-wrap">
            {STRATEGY_OPTIONS.map((s) => (
              <button key={s} type="button" onClick={() => toggleArr('strategy', s)}
                className={cn('px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                  form.strategy.includes(s)
                    ? 'bg-[#1B3A5C] text-white border-[#1B3A5C]'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-[#1B3A5C]'
                )}>
                {s.replace(/_/g, '/')}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">Property Types</p>
          <div className="flex gap-2 flex-wrap">
            {PROPERTY_TYPE_OPTIONS.map((t) => (
              <button key={t} type="button" onClick={() => toggleArr('property_types', t)}
                className={cn('px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                  form.property_types.includes(t)
                    ? 'bg-[#E8720C] text-white border-[#E8720C]'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-[#E8720C]'
                )}>
                {t}
              </button>
            ))}
          </div>
        </div>

        <Textarea label="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={2} />

        <div className="flex justify-end gap-3">
          <Button variant="outline" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={createBuyer.isPending || updateBuyer.isPending}>
            {isEdit ? 'Save Changes' : 'Add Buyer'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ─── Buyer Match Modal ────────────────────────────────────────────────────────
function BuyerMatchModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: deals = [] } = useDeals();
  const { match, loading, result, error } = useBuyerMatcher();
  const [selectedDealId, setSelectedDealId] = useState('');

  const activeDeal = deals.find((d) => d.id === selectedDealId);

  const handleMatch = () => {
    if (!activeDeal) return toast.error('Select a deal');
    match({
      deal_id: activeDeal.id,
      property_address: activeDeal.lead?.property_address || activeDeal.deal_name || '',
      contract_price: activeDeal.contract_price,
      buyer_price: activeDeal.buyer_price,
      arv: activeDeal.arv,
      repair_estimate: activeDeal.repair_estimate,
      zip_code: activeDeal.lead?.zip_code,
      closing_date: activeDeal.closing_date,
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="Blast New Deal to Buyers" size="xl">
      <div className="p-6 space-y-5">
        <Select
          label="Select Deal"
          value={selectedDealId}
          onChange={(e) => setSelectedDealId(e.target.value)}
          options={deals.filter((d) => !['closed', 'cancelled'].includes(d.stage)).map((d) => ({
            value: d.id,
            label: d.lead?.property_address || d.deal_name || d.id,
          }))}
          placeholder="Choose a deal..."
        />

        <Button onClick={handleMatch} loading={loading} disabled={!selectedDealId} className="w-full">
          <Bot className="h-4 w-4 mr-2" /> Find Matching Buyers
        </Button>

        {error && <p className="text-sm text-red-500">{error}</p>}

        {result && (
          <div className="space-y-4">
            {/* Ranked buyers */}
            <div>
              <p className="text-sm font-semibold text-gray-700 mb-2">
                {result.ranked_buyers?.length || 0} Matched Buyers (ranked by fit)
              </p>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {(result.ranked_buyers || []).map((match, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <span className="text-lg font-bold text-[#1B3A5C] w-8 shrink-0">#{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-sm text-gray-900">
                          {match.buyer?.first_name} {match.buyer?.last_name}
                        </p>
                        <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-semibold">
                          {match.fit_score}% fit
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{match.fit_reason}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Blast templates */}
            {result.blast_email_subject && (
              <div className="space-y-3">
                <div className="border border-gray-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-500 mb-1">EMAIL SUBJECT</p>
                  <p className="text-sm font-medium text-gray-800">{result.blast_email_subject}</p>
                </div>
                <div className="border border-gray-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-500 mb-1">EMAIL BODY</p>
                  <p className="text-sm text-gray-700 whitespace-pre-line">{result.blast_email_body}</p>
                </div>
                <div className="border border-gray-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-gray-500 mb-1">SMS</p>
                  <p className="text-sm text-gray-700">{result.blast_sms}</p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
