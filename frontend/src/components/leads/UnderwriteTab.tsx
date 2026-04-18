import { useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp, Home, TrendingUp, Building2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import {
  usePropertyEnrichment,
  useArvResult,
  useLeadComps,
  useRentalYield,
  useRefreshUnderwrite,
} from '@/hooks/useUnderwrite';
import type { Lead } from '@/types';

// ── Formatting helpers ─────────────────────────────────────────────────────────
function fmtDollars(n?: number | null): string {
  if (n == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
}

function fmtPct(n?: number | null): string {
  if (n == null) return '—';
  return `${n.toFixed(1)}%`;
}

function fmtDate(s?: string | null): string {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ── Confidence badge ───────────────────────────────────────────────────────────
function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;
  const map: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' }> = {
    high:   { label: 'HIGH',   variant: 'success' },
    medium: { label: 'MEDIUM', variant: 'warning' },
    low:    { label: 'LOW',    variant: 'danger'  },
  };
  const cfg = map[confidence] ?? { label: confidence.toUpperCase(), variant: 'gray' as const };
  return <Badge variant={cfg.variant}>{cfg.label} CONFIDENCE</Badge>;
}

// ── Max Offer Calculator ───────────────────────────────────────────────────────
function MaxOfferCalc({ arvMid }: { arvMid?: number }) {
  const [repairs, setRepairs] = useState<string>('');

  const repairNum  = parseFloat(repairs.replace(/,/g, '')) || 0;
  const maxOffer   = arvMid != null ? Math.max(0, arvMid * 0.70 - repairNum) : null;

  return (
    <div className="bg-[#1B3A5C]/5 rounded-lg p-4 space-y-3">
      <p className="text-sm font-semibold text-[#1B3A5C]">Max Offer Calculator (70% Rule)</p>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-xs text-gray-500 mb-1">ARV Mid</p>
          <p className="text-base font-bold text-gray-900">{fmtDollars(arvMid)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Repair Estimate</p>
          <input
            type="text"
            value={repairs}
            onChange={(e) => setRepairs(e.target.value)}
            placeholder="$0"
            className="w-full border border-gray-300 rounded px-2 py-1 text-sm text-center focus:outline-none focus:ring-1 focus:ring-[#1B3A5C]"
          />
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Max Offer</p>
          <p className={cn('text-base font-bold', maxOffer != null ? 'text-[#E8720C]' : 'text-gray-400')}>
            {fmtDollars(maxOffer)}
          </p>
        </div>
      </div>
      {arvMid != null && (
        <p className="text-xs text-gray-400">
          = ARV {fmtDollars(arvMid)} × 70% − repairs {fmtDollars(repairNum)}
        </p>
      )}
    </div>
  );
}

// ── Similarity score bar ───────────────────────────────────────────────────────
function ScoreBar({ score }: { score?: number }) {
  if (score == null) return <span className="text-gray-400">—</span>;
  const pct   = Math.min(100, Math.max(0, score));
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-400';
  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
        <div className={cn('h-1.5 rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-600 w-7 text-right">{Math.round(pct)}</span>
    </div>
  );
}

// ── Source badge ───────────────────────────────────────────────────────────────
function SourceBadge({ source }: { source?: string }) {
  const map: Record<string, string> = {
    zillow:           'bg-blue-100 text-blue-700',
    redfin:           'bg-red-100 text-red-700',
    realtor:          'bg-orange-100 text-orange-700',
    zillow_expanded:  'bg-blue-50 text-blue-500',
    redfin_expanded:  'bg-red-50 text-red-500',
  };
  const cls = map[source ?? ''] ?? 'bg-gray-100 text-gray-600';
  return (
    <span className={cn('px-1.5 py-0.5 rounded text-xs font-medium capitalize', cls)}>
      {source?.replace('_expanded', '*') ?? '—'}
    </span>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
interface UnderwriteTabProps {
  lead: Lead;
}

export function UnderwriteTab({ lead }: UnderwriteTabProps) {
  const [notesOpen, setNotesOpen]     = useState(false);
  const [compSort, setCompSort]       = useState<'similarity_score' | 'sale_price' | 'sale_date'>('similarity_score');
  const [compSortAsc, setCompSortAsc] = useState(false);

  const { data: enrichment, isLoading: enrichLoading } = usePropertyEnrichment(lead.id);
  const { data: arv,        isLoading: arvLoading     } = useArvResult(lead.id);
  const { data: comps = [], isLoading: compsLoading   } = useLeadComps(lead.id);
  const { data: rental,     isLoading: rentalLoading  } = useRentalYield(lead.id);
  const refresh = useRefreshUnderwrite(lead.id);

  const anyLoading = enrichLoading || arvLoading || compsLoading || rentalLoading;

  // Sort comps client-side
  const sortedComps = [...comps].sort((a, b) => {
    const av = (a as Record<string, unknown>)[compSort] ?? 0;
    const bv = (b as Record<string, unknown>)[compSort] ?? 0;
    const cmp = typeof av === 'string'
      ? av.localeCompare(bv as string)
      : (av as number) - (bv as number);
    return compSortAsc ? cmp : -cmp;
  });

  function toggleSort(col: typeof compSort) {
    if (compSort === col) setCompSortAsc((v) => !v);
    else { setCompSort(col); setCompSortAsc(false); }
  }

  const noData = !enrichLoading && !arvLoading && !enrichment && !arv;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {anyLoading ? 'Loading enrichment data…' : noData ? 'No enrichment data yet' : `Last enriched ${fmtDate(enrichment?.fetched_at)}`}
        </p>
        <Button
          size="sm"
          variant="outline"
          onClick={() => refresh.mutate({ address: lead.property_address })}
          loading={refresh.isPending}
          className="gap-1.5"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {/* Property Enrichment */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Home className="h-4 w-4 text-[#1B3A5C]" />
            Property Details
          </CardTitle>
        </CardHeader>
        <CardContent>
          {enrichLoading ? (
            <div className="grid grid-cols-4 gap-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded" />
              ))}
            </div>
          ) : enrichment ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3">
              {[
                ['Beds',          enrichment.beds?.toString() ?? '—'],
                ['Baths',         enrichment.baths?.toString() ?? '—'],
                ['Sqft',          enrichment.sqft ? enrichment.sqft.toLocaleString() : '—'],
                ['Year Built',    enrichment.year_built?.toString() ?? '—'],
                ['Zestimate',     fmtDollars(enrichment.zestimate)],
                ['Last Sale',     fmtDollars(enrichment.last_sale_price)],
                ['Last Sale Date',fmtDate(enrichment.last_sale_date)],
                ['Tax Assessment',fmtDollars(enrichment.tax_assessment)],
              ].map(([label, val]) => (
                <div key={label}>
                  <p className="text-xs text-gray-500">{label}</p>
                  <p className="text-sm font-semibold text-gray-900">{val}</p>
                </div>
              ))}
              {enrichment.data_source && (
                <div className="col-span-2 sm:col-span-4">
                  <SourceBadge source={enrichment.data_source} />
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No property data — click Refresh to enrich.</p>
          )}
        </CardContent>
      </Card>

      {/* ARV Result */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-[#E8720C]" />
              ARV Analysis
            </CardTitle>
            {arv && <ConfidenceBadge confidence={arv.confidence} />}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {arvLoading ? (
            <div className="grid grid-cols-3 gap-4">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 rounded" />)}
            </div>
          ) : arv ? (
            <>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="bg-orange-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">ARV Low</p>
                  <p className="text-lg font-bold text-orange-700">{fmtDollars(arv.arv_low)}</p>
                </div>
                <div className="bg-[#1B3A5C] rounded-lg p-3">
                  <p className="text-xs text-blue-200 mb-1">ARV Mid</p>
                  <p className="text-lg font-bold text-white">{fmtDollars(arv.arv_mid)}</p>
                </div>
                <div className="bg-green-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">ARV High</p>
                  <p className="text-lg font-bold text-green-700">{fmtDollars(arv.arv_high)}</p>
                </div>
              </div>

              <div className="flex items-center gap-4 text-sm text-gray-600">
                <span>Avg PPSF: <strong className="text-gray-900">${arv.avg_ppsf?.toFixed(0) ?? '—'}/sqft</strong></span>
                <span>Comps used: <strong className="text-gray-900">{arv.comp_count ?? '—'}</strong></span>
              </div>

              <MaxOfferCalc arvMid={arv.arv_mid} />

              {arv.methodology && (
                <div>
                  <button
                    onClick={() => setNotesOpen((v) => !v)}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
                  >
                    {notesOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    Methodology Notes
                  </button>
                  {notesOpen && (
                    <p className="mt-2 text-xs text-gray-600 bg-gray-50 rounded p-3 leading-relaxed">
                      {arv.methodology}
                    </p>
                  )}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-400">No ARV data — click Refresh to compute.</p>
          )}
        </CardContent>
      </Card>

      {/* Comp Table */}
      <Card>
        <CardHeader>
          <CardTitle>Comparable Sales ({comps.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {compsLoading ? (
            <div className="p-5 space-y-2">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-8 rounded" />)}
            </div>
          ) : sortedComps.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    <th className="px-3 py-2 text-left font-medium text-gray-500">Address</th>
                    <th
                      className="px-3 py-2 text-right font-medium text-gray-500 cursor-pointer hover:text-gray-800"
                      onClick={() => toggleSort('sale_price')}
                    >
                      Price {compSort === 'sale_price' ? (compSortAsc ? '↑' : '↓') : ''}
                    </th>
                    <th
                      className="px-3 py-2 text-right font-medium text-gray-500 cursor-pointer hover:text-gray-800"
                      onClick={() => toggleSort('sale_date')}
                    >
                      Date {compSort === 'sale_date' ? (compSortAsc ? '↑' : '↓') : ''}
                    </th>
                    <th className="px-3 py-2 text-right font-medium text-gray-500">Sqft</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-500">$/sqft</th>
                    <th
                      className="px-3 py-2 text-center font-medium text-gray-500 cursor-pointer hover:text-gray-800 min-w-[110px]"
                      onClick={() => toggleSort('similarity_score')}
                    >
                      Score {compSort === 'similarity_score' ? (compSortAsc ? '↑' : '↓') : ''}
                    </th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {sortedComps.map((c) => (
                    <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-3 py-2 text-gray-800 max-w-[180px] truncate">{c.address}</td>
                      <td className="px-3 py-2 text-right font-medium text-gray-900">
                        {fmtDollars(c.sale_price)}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-600">{fmtDate(c.sale_date)}</td>
                      <td className="px-3 py-2 text-right text-gray-600">
                        {c.sqft ? c.sqft.toLocaleString() : '—'}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-600">
                        {c.price_per_sqft ? `$${Math.round(c.price_per_sqft)}` : '—'}
                      </td>
                      <td className="px-3 py-2">
                        <ScoreBar score={c.similarity_score} />
                      </td>
                      <td className="px-3 py-2 text-center">
                        <SourceBadge source={c.source} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="px-5 py-4 text-sm text-gray-400">No comps found.</p>
          )}
        </CardContent>
      </Card>

      {/* Rental Yield */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-indigo-600" />
              Rental Yield
            </CardTitle>
            {rental && rental.gross_yield_ltr != null && rental.ltr_monthly_est != null &&
             rental.gross_yield_ltr >= 7.0 && rental.ltr_monthly_est >= 1800 && (
              <Badge variant="success" className="font-bold">BTR ELIGIBLE</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {rentalLoading ? (
            <div className="grid grid-cols-3 gap-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 rounded" />)}
            </div>
          ) : rental ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-3">
              <div>
                <p className="text-xs text-gray-500">LTR Monthly</p>
                <p className="text-sm font-bold text-gray-900">{fmtDollars(rental.ltr_monthly_est)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">STR Monthly (est.)</p>
                <p className="text-sm font-bold text-gray-900">{fmtDollars(rental.str_monthly_est)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Gross Yield LTR</p>
                <p className={cn('text-sm font-bold', (rental.gross_yield_ltr ?? 0) >= 7 ? 'text-green-600' : 'text-gray-900')}>
                  {fmtPct(rental.gross_yield_ltr)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Gross Yield STR</p>
                <p className="text-sm font-bold text-gray-900">{fmtPct(rental.gross_yield_str)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">STR ADR</p>
                <p className="text-sm text-gray-900">{fmtDollars(rental.str_adr)}/night</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">STR Occupancy</p>
                <p className="text-sm text-gray-900">
                  {rental.str_occupancy != null ? `${Math.round(rental.str_occupancy * 100)}%` : '—'}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400">No rental data — click Refresh to compute.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
