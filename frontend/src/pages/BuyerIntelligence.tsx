import { apiFetch } from '@/lib/api';
/**
 * BuyerIntelligence — Investor Buyer Intelligence Engine (IBIE) Dashboard.
 *
 * 4 tabs:
 *   Leaderboard   — Top buyers ranked by IBIE score, filters, profile drawer
 *   Import        — Upload county records / PropStream CSV
 *   Deal Match    — Select a deal → ranked buyer list → blast outreach
 *   Outreach Log  — SMS/email sent history with response tracking
 */

import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/lib/supabase';
import { BuyerScoreRing, BuyerScoreBadge } from '@/components/buyers/BuyerScoreRing';
import { BuyerImportModal } from '@/components/buyers/BuyerImportModal';
import { DealMatchingPanel } from '@/components/buyers/DealMatchingPanel';
import { OutreachLauncher, type DealContext } from '@/components/buyers/OutreachLauncher';
import { BuyerProfileDrawer } from '@/components/buyers/BuyerProfileDrawer';
import { Button } from '@/components/ui/button';
import { cn, formatCurrency, formatDate, phoneFormat } from '@/lib/utils';
import {
  Users, Upload, Zap, MessageSquare, RefreshCw, Filter,
  Search, ChevronDown, TrendingUp, Building2, DollarSign,
  Star, Award, Flame
} from 'lucide-react';
import { toast } from 'sonner';

// ── Types ─────────────────────────────────────────────────────────────────────

interface IBIEBuyer {
  id: string;
  first_name: string;
  last_name: string;
  company?: string;
  entity_name?: string;
  email?: string;
  phone?: string;
  market?: string;
  buyer_type_ibie?: string;
  ibie_score: number;
  ibie_tier: string;
  cash_buyer: boolean;
  repeat_buyer: boolean;
  total_purchases_12mo: number;
  properties_owned: number;
  avg_purchase_price?: number;
  last_purchase_date?: string;
  tags: string[];
  deals_closed: number;
  pof_verified: boolean;
  pof_amount?: number;
  target_zips?: string[];
  min_price?: number;
  max_price?: number;
  active: boolean;
  sms_opt_in: boolean;
  email_opt_in: boolean;
  transaction_count?: number;
  outreach_ignore_count?: number;
  ai_classified_at?: string;
}

interface OutreachRow {
  id: string;
  created_at: string;
  channel: string;
  status: string;
  body: string;
  to_address: string;
  buyer_id: string;
  replied_at?: string;
  buyers?: { first_name: string; last_name: string };
}

interface SegmentSummary {
  ibie_tier: string;
  buyer_type_ibie: string;
  buyer_count: number;
  avg_score: number;
  cash_buyer_count: number;
  repeat_buyer_count: number;
  avg_purchases_12mo: number;
  avg_buy_price: number;
}

// ── KPI strip ─────────────────────────────────────────────────────────────────

function KpiStrip({ buyers }: { buyers: IBIEBuyer[] }) {
  const total     = buyers.length;
  const tierA     = buyers.filter((b) => b.ibie_tier === 'A').length;
  const tierB     = buyers.filter((b) => b.ibie_tier === 'B').length;
  const cash      = buyers.filter((b) => b.cash_buyer).length;
  const repeat    = buyers.filter((b) => b.repeat_buyer).length;
  const avgScore  = total ? Math.round(buyers.reduce((s, b) => s + (b.ibie_score || 0), 0) / total) : 0;

  const kpis = [
    { label: 'Total Buyers', value: total.toLocaleString(), icon: <Users className="h-4 w-4 text-[#1B3A5C]" />, bg: 'bg-blue-50' },
    { label: 'Tier A (≥75)', value: tierA.toLocaleString(), icon: <Award className="h-4 w-4 text-green-600" />, bg: 'bg-green-50' },
    { label: 'Tier B (50–74)', value: tierB.toLocaleString(), icon: <Star className="h-4 w-4 text-blue-600" />, bg: 'bg-blue-50' },
    { label: 'Cash Buyers', value: cash.toLocaleString(), icon: <DollarSign className="h-4 w-4 text-green-600" />, bg: 'bg-green-50' },
    { label: 'Repeat Buyers', value: repeat.toLocaleString(), icon: <TrendingUp className="h-4 w-4 text-purple-600" />, bg: 'bg-purple-50' },
    { label: 'Avg IBIE Score', value: String(avgScore), icon: <Flame className="h-4 w-4 text-[#E8720C]" />, bg: 'bg-orange-50' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {kpis.map((k) => (
        <div key={k.label} className={cn('rounded-xl p-4 border border-gray-100 shadow-sm', k.bg)}>
          <div className="flex items-center gap-2 mb-1">{k.icon}<p className="text-xs text-gray-500">{k.label}</p></div>
          <p className="text-2xl font-bold text-gray-900">{k.value}</p>
        </div>
      ))}
    </div>
  );
}

// ── Tab nav ───────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'leaderboard', label: 'Leaderboard', icon: Users },
  { id: 'import',      label: 'Import',      icon: Upload },
  { id: 'match',       label: 'Deal Match',  icon: Zap },
  { id: 'outreach',    label: 'Outreach Log',icon: MessageSquare },
] as const;

type TabId = typeof TABS[number]['id'];

// ── Main page ─────────────────────────────────────────────────────────────────

export function BuyerIntelligence() {
  const [tab, setTab] = useState<TabId>('leaderboard');
  const [buyers, setBuyers] = useState<IBIEBuyer[]>([]);
  const [outreachLog, setOutreachLog] = useState<OutreachRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [rescoring, setRescoring] = useState(false);

  // Filters
  const [search, setSearch] = useState('');
  const [filterTier, setFilterTier] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterMarket, setFilterMarket] = useState('');
  const [cashOnly, setCashOnly] = useState(false);

  // UI state
  const [importOpen, setImportOpen] = useState(false);
  const [activeBuyer, setActiveBuyer] = useState<IBIEBuyer | null>(null);
  const [matchSelectedIds, setMatchSelectedIds] = useState<string[]>([]);
  const [matchDeal, setMatchDeal] = useState<DealContext>({});

  const loadBuyers = useCallback(async () => {
    setLoading(true);
    try {
      let query = supabase.from('buyer_leaderboard').select('*').order('ibie_score', { ascending: false }).limit(500);
      if (filterTier)   query = query.eq('ibie_tier', filterTier);
      if (filterType)   query = query.eq('buyer_type_ibie', filterType);
      if (filterMarket) query = query.eq('market', filterMarket);
      if (cashOnly)     query = query.eq('cash_buyer', true);

      const { data, error } = await query;
      if (error) throw error;
      setBuyers((data as IBIEBuyer[]) || []);
    } catch (err) {
      toast.error(`Failed to load buyers: ${err}`);
    } finally {
      setLoading(false);
    }
  }, [filterTier, filterType, filterMarket, cashOnly]);

  const loadOutreachLog = async () => {
    const { data } = await supabase
      .from('buyer_outreach_log')
      .select('*, buyers(first_name, last_name)')
      .order('created_at', { ascending: false })
      .limit(100);
    setOutreachLog((data as OutreachRow[]) || []);
  };

  useEffect(() => { loadBuyers(); }, [loadBuyers]);
  useEffect(() => { if (tab === 'outreach') loadOutreachLog(); }, [tab]);

  const handleRescore = async () => {
    setRescoring(true);
    try {
      await apiFetch('/api/buyers/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      toast.success('Re-scoring queued — refresh in 30 seconds');
    } catch {
      toast.error('Re-score failed');
    } finally {
      setRescoring(false);
    }
  };

  // Client-side search filter
  const filtered = buyers.filter((b) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      `${b.first_name} ${b.last_name}`.toLowerCase().includes(q) ||
      (b.company || '').toLowerCase().includes(q) ||
      (b.entity_name || '').toLowerCase().includes(q) ||
      (b.phone || '').includes(q) ||
      (b.target_zips || []).some((z) => z.includes(q))
    );
  });

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Buyer Intelligence Engine</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {buyers.length.toLocaleString()} active buyers · IBIE-scored &amp; segmented
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleRescore} loading={rescoring}>
            <RefreshCw className="h-4 w-4 mr-1.5" />
            Re-Score All
          </Button>
          <Button size="sm" onClick={() => setImportOpen(true)}>
            <Upload className="h-4 w-4 mr-1.5" />
            Import CSV
          </Button>
        </div>
      </div>

      {/* KPI Strip */}
      <KpiStrip buyers={buyers} />

      {/* Tabs */}
      <div className="flex border-b border-gray-200 gap-1">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
              tab === id
                ? 'border-[#E8720C] text-[#E8720C]'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab: Leaderboard ──────────────────────────────────────────── */}
      {tab === 'leaderboard' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex gap-2 flex-wrap items-center">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search buyers…"
                className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-[#1B3A5C]"
              />
            </div>
            {[
              { label: 'All Tiers', key: 'filterTier', val: filterTier, set: setFilterTier, opts: ['A','B','C','D'].map((t) => ({ value: t, label: `Tier ${t}` })) },
              { label: 'All Types', key: 'filterType', val: filterType, set: setFilterType, opts: ['flipper','landlord','institutional','builder'].map((t) => ({ value: t, label: t.charAt(0).toUpperCase() + t.slice(1) })) },
            ].map(({ label, val, set, opts }) => (
              <select
                key={label}
                value={val}
                onChange={(e) => { set(e.target.value); }}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1B3A5C]"
              >
                <option value="">{label}</option>
                {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ))}
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" checked={cashOnly} onChange={(e) => setCashOnly(e.target.checked)} className="w-4 h-4 rounded" />
              Cash only
            </label>
            <Button variant="outline" size="sm" onClick={loadBuyers}>Apply</Button>
          </div>

          {/* Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    {['Rank','Buyer / Entity','IBIE Score','Type','Market','Buys 12mo','Avg Price','Cash','Tags','Last Purchase',''].map((h) => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {loading ? (
                    <tr><td colSpan={11} className="px-4 py-12 text-center text-gray-400">Loading buyers…</td></tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="px-4 py-16 text-center">
                        <p className="text-gray-400 font-medium">No buyers found</p>
                        <p className="text-xs text-gray-300 mt-1">Import county records or add buyers manually to get started</p>
                      </td>
                    </tr>
                  ) : filtered.map((b, i) => (
                    <tr
                      key={b.id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => setActiveBuyer(b)}
                    >
                      <td className="px-4 py-3 text-gray-400 font-mono text-xs">#{i + 1}</td>
                      <td className="px-4 py-3">
                        <p className="font-semibold text-gray-900">{b.first_name} {b.last_name}</p>
                        {b.company && <p className="text-xs text-gray-400">{b.company}</p>}
                      </td>
                      <td className="px-4 py-3">
                        <BuyerScoreBadge score={b.ibie_score} tier={b.ibie_tier} />
                      </td>
                      <td className="px-4 py-3">
                        {b.buyer_type_ibie ? (
                          <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded capitalize">
                            {b.buyer_type_ibie}
                          </span>
                        ) : <span className="text-gray-300 text-xs">—</span>}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">{b.market || '—'}</td>
                      <td className="px-4 py-3 text-center font-semibold text-gray-700">{b.total_purchases_12mo ?? 0}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-gray-600 text-xs">
                        {b.avg_purchase_price ? formatCurrency(b.avg_purchase_price) : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {b.cash_buyer
                          ? <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-semibold">CASH</span>
                          : <span className="text-gray-300 text-xs">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-1 flex-wrap max-w-36">
                          {(b.tags || []).slice(0, 2).map((tag) => (
                            <span key={tag} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                              {tag.replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                        {formatDate(b.last_purchase_date)}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          className="text-xs text-[#1B3A5C] hover:underline"
                          onClick={(e) => { e.stopPropagation(); setActiveBuyer(b); }}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Import ───────────────────────────────────────────────── */}
      {tab === 'import' && (
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
            <h2 className="font-semibold text-gray-800">Import Buyer Data</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                { title: 'County Deed Records', desc: 'Download from your county appraisal district website. Most counties offer free CSV exports of deed transfer records.', badge: 'Free', color: 'bg-green-50 border-green-200' },
                { title: 'PropStream Cash Buyers', desc: 'In PropStream: Leads → Cash Buyers → Filter by zip/county → Export CSV. Columns are auto-detected.', badge: 'PropStream', color: 'bg-blue-50 border-blue-200' },
                { title: 'Title Company / Manual List', desc: 'Any CSV with buyer name, address, price, and date columns will work. Column names are matched automatically.', badge: 'Any CSV', color: 'bg-orange-50 border-orange-200' },
              ].map((src) => (
                <div key={src.title} className={cn('rounded-xl p-4 border', src.color)}>
                  <div className="flex items-start justify-between mb-2">
                    <p className="font-semibold text-sm text-gray-800">{src.title}</p>
                    <span className="text-xs px-2 py-0.5 bg-white rounded-full border border-gray-200 text-gray-600">{src.badge}</span>
                  </div>
                  <p className="text-xs text-gray-600 leading-relaxed">{src.desc}</p>
                </div>
              ))}
            </div>
            <div className="border-2 border-dashed border-gray-300 rounded-xl p-10 flex flex-col items-center gap-3">
              <Upload className="h-10 w-10 text-gray-400" />
              <p className="font-medium text-gray-700">Drop your CSV here or</p>
              <Button onClick={() => setImportOpen(true)}>
                <Upload className="h-4 w-4 mr-2" />
                Open Import Wizard
              </Button>
            </div>
          </div>

          {/* Scoring explanation */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <h2 className="font-semibold text-gray-800">How IBIE Scoring Works</h2>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              {[
                { factor: 'Purchase Frequency', weight: '30%', desc: 'Deals in last 12 months' },
                { factor: 'Recency', weight: '25%', desc: 'Last purchase date (≤30d = max)' },
                { factor: 'Cash Buyer', weight: '20%', desc: '+100 if majority cash transactions' },
                { factor: 'Volume', weight: '15%', desc: 'All-time deal count (cap 20)' },
                { factor: 'Price Alignment', weight: '10%', desc: 'Avg price vs. your deal range' },
              ].map((f) => (
                <div key={f.factor} className="bg-gray-50 rounded-lg p-3 text-center">
                  <p className="text-lg font-bold text-[#E8720C]">{f.weight}</p>
                  <p className="text-xs font-semibold text-gray-700 mt-1">{f.factor}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{f.desc}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-3 mt-2">
              {[
                { tier: 'A', range: '≥ 75', color: 'bg-green-100 text-green-700', desc: 'Top buyers — contact immediately' },
                { tier: 'B', range: '50–74', color: 'bg-blue-100 text-blue-700', desc: 'Active buyers — blast all deals' },
                { tier: 'C', range: '25–49', color: 'bg-amber-100 text-amber-700', desc: 'Moderate — include in blasts' },
                { tier: 'D', range: '< 25', color: 'bg-red-100 text-red-700', desc: 'Low — suppress or re-qualify' },
              ].map((t) => (
                <div key={t.tier} className="p-3 rounded-lg border border-gray-200">
                  <span className={cn('text-sm font-bold px-2 py-0.5 rounded', t.color)}>Tier {t.tier} ({t.range})</span>
                  <p className="text-xs text-gray-500 mt-2">{t.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Deal Match ───────────────────────────────────────────── */}
      {tab === 'match' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <h2 className="font-semibold text-gray-800 flex items-center gap-2">
              <Zap className="h-5 w-5 text-[#E8720C]" /> Match Buyers to Deal
            </h2>
            <DealMatchingPanel
              onDealChange={() => {
                setMatchSelectedIds([]);
                setMatchDeal({});
              }}
              onSelectBuyers={(ids, deal) => {
                setMatchSelectedIds(ids);
                setMatchDeal(deal);
                toast.success(`${ids.length} buyers selected for outreach`);
              }}
            />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <h2 className="font-semibold text-gray-800 flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-[#1B3A5C]" /> Send Outreach
            </h2>
            {matchSelectedIds.length === 0 ? (
              <div className="flex flex-col items-center py-10 gap-3 text-center">
                <MessageSquare className="h-10 w-10 text-gray-300" />
                <p className="text-gray-400 text-sm">Select buyers from the matching panel to send SMS or email</p>
              </div>
            ) : (
              <OutreachLauncher
                key={JSON.stringify([matchDeal, matchSelectedIds])}
                buyerIds={matchSelectedIds}
                deal={matchDeal}
                onSent={() => {
                  setMatchSelectedIds([]);
                  setTab('outreach');
                  loadOutreachLog();
                }}
              />
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Outreach Log ─────────────────────────────────────────── */}
      {tab === 'outreach' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  {['Buyer','Channel','Status','Message','Sent','Reply'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {outreachLog.length === 0 ? (
                  <tr><td colSpan={6} className="px-4 py-12 text-center text-gray-400">No outreach sent yet</td></tr>
                ) : outreachLog.map((row) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {row.buyers?.first_name} {row.buyers?.last_name}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn('text-xs px-2 py-0.5 rounded font-medium uppercase',
                        row.channel === 'sms' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700'
                      )}>
                        {row.channel}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn('text-xs px-2 py-0.5 rounded',
                        row.status === 'sent' || row.status === 'delivered' ? 'bg-green-100 text-green-700' :
                        row.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
                      )}>
                        {row.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 max-w-64 truncate text-xs">{row.body}</td>
                    <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{formatDate(row.created_at)}</td>
                    <td className="px-4 py-3">
                      {row.replied_at
                        ? <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">Replied</span>
                        : <span className="text-xs text-gray-300">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Import modal */}
      <BuyerImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => { setTimeout(loadBuyers, 3000); }}
      />

      {/* Buyer profile drawer */}
      <BuyerProfileDrawer
        buyer={activeBuyer}
        open={!!activeBuyer}
        onClose={() => setActiveBuyer(null)}
        onUpdated={loadBuyers}
      />
    </div>
  );
}
