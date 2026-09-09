import { apiFetch } from '@/lib/api';
/**
 * DealMatchingPanel — match buyers to a deal and launch outreach.
 *
 * Props:
 *   dealId?       — pre-select a specific deal
 *   standalone?   — true = render as full panel, false = embed in page
 *   onSelectBuyers(ids) — callback when user clicks "Send to Selected"
 */

import { useState } from 'react';
import { useDeals } from '@/hooks/useDeals';
import { BuyerScoreBadge } from './BuyerScoreRing';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { cn, formatCurrency } from '@/lib/utils';
import { Zap, CheckSquare, Square, Send, ChevronDown, ChevronUp, MapPin, DollarSign, Home } from 'lucide-react';
import { toast } from 'sonner';

interface MatchResult {
  rank: number;
  buyer_id: string;
  buyer_name: string;
  company: string;
  phone: string;
  email: string;
  ibie_score: number;
  match_score: number;
  zip_score: number;
  price_score: number;
  type_score: number;
  tags: string[];
  match_reasons: string[];
}

interface DealMatchingPanelProps {
  dealId?: string;
  onSelectBuyers?: (ids: string[]) => void;
  compact?: boolean;
}

export function DealMatchingPanel({ dealId: propDealId, onSelectBuyers, compact = false }: DealMatchingPanelProps) {
  const { data: deals = [] } = useDeals();
  const [selectedDealId, setSelectedDealId] = useState(propDealId || '');
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState(false);
  const [totalMatches, setTotalMatches] = useState(0);

  const activeDeal = deals.find((d) => d.id === selectedDealId);
  const displayMatches = showAll ? matches : matches.slice(0, 20);

  const handleMatch = async () => {
    if (!activeDeal) return toast.error('Select a deal first');
    setLoading(true);
    setMatches([]);
    setSelectedIds(new Set());
    try {
      const resp = await apiFetch('/api/buyers/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deal_id:       activeDeal.id,
          zip_code:      activeDeal.lead?.zip_code || '',
          buyer_price:   activeDeal.buyer_price || activeDeal.contract_price || 0,
          property_type: activeDeal.lead?.property_type || '',
          arv:           activeDeal.arv || 0,
          limit:         50,
        }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setMatches(data.matches || []);
      setTotalMatches(data.total_matches || 0);
      toast.success(`${data.total_matches} buyers matched`);
    } catch (err) {
      toast.error(`Matching failed: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelectedIds(new Set(displayMatches.map((m) => m.buyer_id)));
  const clearAll  = () => setSelectedIds(new Set());

  const handleSendSelected = () => {
    if (selectedIds.size === 0) return toast.error('Select at least one buyer');
    onSelectBuyers?.(Array.from(selectedIds));
  };

  return (
    <div className="space-y-4">
      {/* Deal selector + match button */}
      <div className="flex gap-3 items-end flex-wrap">
        <div className="flex-1 min-w-48">
          <Select
            label={compact ? undefined : 'Select Deal'}
            value={selectedDealId}
            onChange={(e) => setSelectedDealId(e.target.value)}
            options={deals
              .filter((d) => !['closed', 'cancelled'].includes(d.stage))
              .map((d) => ({
                value: d.id,
                label: d.lead?.property_address || d.deal_name || d.id,
              }))}
            placeholder="Choose a deal…"
          />
        </div>
        <Button onClick={handleMatch} loading={loading} disabled={!selectedDealId}>
          <Zap className="h-4 w-4 mr-1.5" />
          Find Buyers
        </Button>
      </div>

      {/* Deal summary strip */}
      {activeDeal && (
        <div className="flex gap-4 text-xs text-gray-500 bg-gray-50 rounded-lg px-4 py-2 border border-gray-200">
          {activeDeal.lead?.zip_code && (
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {activeDeal.lead.zip_code}
            </span>
          )}
          {(activeDeal.buyer_price || activeDeal.contract_price) && (
            <span className="flex items-center gap-1">
              <DollarSign className="h-3 w-3" /> {formatCurrency(activeDeal.buyer_price || activeDeal.contract_price || 0)}
            </span>
          )}
          {activeDeal.lead?.property_type && (
            <span className="flex items-center gap-1">
              <Home className="h-3 w-3" /> {activeDeal.lead.property_type}
            </span>
          )}
        </div>
      )}

      {/* Results */}
      {matches.length > 0 && (
        <div className="space-y-3">
          {/* Toolbar */}
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-gray-700">
              {totalMatches} matched buyers
              {selectedIds.size > 0 && (
                <span className="ml-2 text-[#E8720C]">({selectedIds.size} selected)</span>
              )}
            </p>
            <div className="flex gap-2">
              <button onClick={selectAll} className="text-xs text-[#1B3A5C] hover:underline">Select all</button>
              <span className="text-gray-300">|</span>
              <button onClick={clearAll} className="text-xs text-gray-500 hover:underline">Clear</button>
              {selectedIds.size > 0 && onSelectBuyers && (
                <Button size="sm" onClick={handleSendSelected}>
                  <Send className="h-3.5 w-3.5 mr-1.5" />
                  Blast {selectedIds.size}
                </Button>
              )}
            </div>
          </div>

          {/* Buyer match list */}
          <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
            {displayMatches.map((m) => {
              const checked = selectedIds.has(m.buyer_id);
              return (
                <div
                  key={m.buyer_id}
                  className={cn(
                    'flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                    checked
                      ? 'bg-orange-50 border-[#E8720C]'
                      : 'bg-white border-gray-200 hover:border-gray-300'
                  )}
                  onClick={() => toggleSelect(m.buyer_id)}
                >
                  {/* Checkbox */}
                  <div className="pt-0.5">
                    {checked
                      ? <CheckSquare className="h-4 w-4 text-[#E8720C]" />
                      : <Square className="h-4 w-4 text-gray-300" />}
                  </div>

                  {/* Rank */}
                  <span className="text-sm font-bold text-[#1B3A5C] w-6 shrink-0 pt-0.5">
                    #{m.rank}
                  </span>

                  {/* Buyer info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-sm text-gray-900">{m.buyer_name}</p>
                      {m.company && <span className="text-xs text-gray-400">{m.company}</span>}
                      <BuyerScoreBadge score={m.ibie_score} />
                    </div>
                    {m.match_reasons.length > 0 && (
                      <p className="text-xs text-gray-500 mt-0.5">{m.match_reasons.join(' · ')}</p>
                    )}
                    {m.tags.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {m.tags.slice(0, 3).map((tag) => (
                          <span key={tag} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                            {tag.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Match score bar */}
                  <div className="text-right shrink-0">
                    <p className="text-xs font-bold text-gray-700">{Math.round(m.match_score)}% fit</p>
                    <div className="w-16 h-1.5 bg-gray-200 rounded-full mt-1">
                      <div
                        className="h-full bg-[#E8720C] rounded-full"
                        style={{ width: `${m.match_score}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Show more / less */}
          {matches.length > 20 && (
            <button
              onClick={() => setShowAll((v) => !v)}
              className="flex items-center gap-1 text-xs text-[#1B3A5C] hover:underline mx-auto"
            >
              {showAll ? <><ChevronUp className="h-3 w-3" /> Show fewer</> : <><ChevronDown className="h-3 w-3" /> Show all {matches.length}</>}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
