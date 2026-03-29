/**
 * BuyerProfileDrawer — slide-in panel with full buyer detail.
 *
 * Shows:
 *  - IBIE score ring + tier + tags
 *  - Contact info
 *  - Buy box (zips, price range, property types)
 *  - Transaction history table (purchase history from county records)
 *  - Outreach activity log
 *  - Classify button (trigger AI buyer type classification)
 */

import { useEffect, useState } from 'react';
import { BuyerScoreRing } from './BuyerScoreRing';
import { Button } from '@/components/ui/button';
import { cn, formatCurrency, formatDate, phoneFormat } from '@/lib/utils';
import {
  X, Phone, Mail, MapPin, DollarSign, Building2, Tag, Brain,
  TrendingUp, Home, Calendar, Banknote, Clock, CheckCircle2
} from 'lucide-react';
import { toast } from 'sonner';

interface BuyerTransaction {
  id: string;
  property_address: string;
  city: string;
  zip_code: string;
  purchase_price: number | null;
  purchase_date: string | null;
  cash_transaction: boolean;
  lender_name: string;
  property_type: string;
  flip_detected: boolean;
}

interface BuyerProfileDrawerProps {
  buyer: Record<string, any> | null;
  open: boolean;
  onClose: () => void;
  onUpdated?: () => void;
}

const TAG_COLORS: Record<string, string> = {
  cash_buyer:          'bg-green-100 text-green-700',
  repeat_buyer:        'bg-blue-100 text-blue-700',
  portfolio_landlord:  'bg-purple-100 text-purple-700',
  institutional:       'bg-red-100 text-red-700',
  entry_flip:          'bg-orange-100 text-orange-700',
  mid_flip:            'bg-amber-100 text-amber-700',
  small_landlord:      'bg-indigo-100 text-indigo-700',
  high_volume:         'bg-teal-100 text-teal-700',
  dormant:             'bg-gray-100 text-gray-500',
  new_buyer:           'bg-cyan-100 text-cyan-700',
};

export function BuyerProfileDrawer({ buyer, open, onClose, onUpdated }: BuyerProfileDrawerProps) {
  const [transactions, setTransactions] = useState<BuyerTransaction[]>([]);
  const [txLoading, setTxLoading] = useState(false);
  const [classifying, setClassifying] = useState(false);

  useEffect(() => {
    if (open && buyer?.id) {
      loadTransactions(buyer.id);
    }
  }, [open, buyer?.id]);

  const loadTransactions = async (buyerId: string) => {
    setTxLoading(true);
    try {
      const resp = await fetch(`/api/buyers/${buyerId}/transactions`);
      if (resp.ok) {
        const data = await resp.json();
        setTransactions(data.transactions || []);
      }
    } catch {
      // Non-critical
    } finally {
      setTxLoading(false);
    }
  };

  const handleClassify = async () => {
    if (!buyer?.id) return;
    setClassifying(true);
    try {
      await fetch(`/api/buyers/${buyer.id}/classify`, { method: 'POST' });
      toast.success('Classification queued — refresh in a moment');
      onUpdated?.();
    } catch {
      toast.error('Classification failed');
    } finally {
      setClassifying(false);
    }
  };

  if (!buyer) return null;

  const tags: string[] = buyer.tags || [];
  const score: number  = buyer.ibie_score ?? 0;
  const tier: string   = buyer.ibie_tier  ?? 'D';

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div className={cn(
        'fixed right-0 top-0 h-full w-[480px] bg-white shadow-2xl z-50 flex flex-col transition-transform duration-300',
        open ? 'translate-x-0' : 'translate-x-full'
      )}>
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-200 bg-[#1B3A5C]">
          <div className="flex items-center gap-4">
            <BuyerScoreRing score={score} tier={tier} size="md" showTier={false} />
            <div>
              <p className="font-bold text-white text-lg leading-tight">
                {buyer.first_name} {buyer.last_name}
              </p>
              {buyer.company && (
                <p className="text-white/70 text-sm">{buyer.company}</p>
              )}
              {buyer.buyer_type_ibie && (
                <p className="text-white/50 text-xs capitalize mt-0.5">
                  {buyer.buyer_type_ibie.replace(/_/g, ' ')} · {tier} tier
                </p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-white/60 hover:text-white p-1 mt-0.5">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">

          {/* KPI strip */}
          <div className="grid grid-cols-3 divide-x divide-gray-100 border-b border-gray-200">
            <Kpi label="IBIE Score" value={`${Math.round(score)}`} sub={`Tier ${tier}`} color={tier === 'A' ? 'text-green-600' : tier === 'B' ? 'text-blue-600' : 'text-gray-700'} />
            <Kpi label="Purchases 12mo" value={String(buyer.total_purchases_12mo ?? 0)} sub="transactions" />
            <Kpi label="Avg Buy Price" value={buyer.avg_purchase_price ? formatCurrency(buyer.avg_purchase_price) : '—'} sub="avg per deal" />
          </div>

          <div className="p-5 space-y-5">

            {/* Tags */}
            {tags.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
                  <Tag className="h-3 w-3" /> Tags
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((tag) => (
                    <span key={tag} className={cn('text-xs px-2 py-0.5 rounded-full font-medium', TAG_COLORS[tag] || 'bg-gray-100 text-gray-600')}>
                      {tag.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Contact */}
            <Section icon={<Phone className="h-3.5 w-3.5" />} title="Contact">
              <Row label="Phone" value={phoneFormat(buyer.phone || '')} />
              <Row label="Email" value={buyer.email || '—'} />
              {buyer.market && <Row label="Market" value={buyer.market} />}
              {buyer.last_purchase_date && (
                <Row label="Last Purchase" value={formatDate(buyer.last_purchase_date)} />
              )}
            </Section>

            {/* Buy box */}
            <Section icon={<DollarSign className="h-3.5 w-3.5" />} title="Buy Box">
              <Row label="Price Range" value={
                buyer.min_price || buyer.max_price
                  ? `${buyer.min_price ? formatCurrency(buyer.min_price) : 'any'} – ${buyer.max_price ? formatCurrency(buyer.max_price) : 'any'}`
                  : '—'
              } />
              <Row label="Target Zips" value={(buyer.target_zips || []).join(', ') || '—'} />
              <Row label="Property Types" value={(buyer.property_types || []).join(', ') || '—'} />
              <Row label="Close Speed" value={buyer.close_speed_days ? `${buyer.close_speed_days} days` : '—'} />
              <Row label="Cash Buyer" value={buyer.cash_buyer ? '✓ Yes' : 'No'} highlight={buyer.cash_buyer} />
              {buyer.pof_verified && (
                <Row label="POF" value={buyer.pof_amount ? `✓ ${formatCurrency(buyer.pof_amount)}` : '✓ Verified'} highlight />
              )}
            </Section>

            {/* AI classify */}
            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div>
                <p className="text-sm font-medium text-gray-700 flex items-center gap-1.5">
                  <Brain className="h-4 w-4 text-[#1B3A5C]" />
                  AI Classification
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {buyer.buyer_type_ibie
                    ? `${buyer.buyer_type_ibie} · classified ${formatDate(buyer.ai_classified_at)}`
                    : 'Not yet classified'}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={handleClassify} loading={classifying}>
                Classify
              </Button>
            </div>

            {/* Transaction history */}
            <Section icon={<TrendingUp className="h-3.5 w-3.5" />} title={`Purchase History (${transactions.length})`}>
              {txLoading ? (
                <p className="text-xs text-gray-400 py-2">Loading…</p>
              ) : transactions.length === 0 ? (
                <p className="text-xs text-gray-400 py-2">No transactions on record. Import county data to populate.</p>
              ) : (
                <div className="space-y-2 mt-2">
                  {transactions.map((tx) => (
                    <div key={tx.id} className="flex items-start gap-2 p-2 bg-gray-50 rounded text-xs">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-800 truncate">{tx.property_address}</p>
                        <p className="text-gray-500 mt-0.5">
                          {tx.city && `${tx.city}, `}{tx.zip_code}
                          {tx.property_type && ` · ${tx.property_type}`}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="font-semibold text-gray-800">
                          {tx.purchase_price ? formatCurrency(tx.purchase_price) : '—'}
                        </p>
                        <p className="text-gray-400">{formatDate(tx.purchase_date)}</p>
                        <div className="flex gap-1 justify-end mt-0.5">
                          {tx.cash_transaction && (
                            <span className="bg-green-100 text-green-700 px-1 rounded">CASH</span>
                          )}
                          {tx.flip_detected && (
                            <span className="bg-orange-100 text-orange-700 px-1 rounded">FLIP</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>

          </div>
        </div>

        {/* Footer actions */}
        <div className="border-t border-gray-200 p-4 flex gap-2">
          {buyer.phone && (
            <a
              href={`tel:${buyer.phone}`}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <Phone className="h-4 w-4" /> Call
            </a>
          )}
          {buyer.email && (
            <a
              href={`mailto:${buyer.email}`}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <Mail className="h-4 w-4" /> Email
            </a>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[#1B3A5C] text-white text-sm font-medium hover:bg-[#16324f]"
          >
            Close
          </button>
        </div>
      </div>
    </>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
        {icon} {title}
      </p>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Row({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-gray-500 w-28 shrink-0">{label}</span>
      <span className={cn('font-medium', highlight ? 'text-green-600' : 'text-gray-800')}>{value}</span>
    </div>
  );
}

function Kpi({ label, value, sub, color = 'text-gray-900' }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="px-4 py-3 text-center">
      <p className={cn('text-lg font-bold', color)}>{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
      {sub && <p className="text-xs text-gray-400">{sub}</p>}
    </div>
  );
}
