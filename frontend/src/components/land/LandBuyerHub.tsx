import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { LandBuyer, LandBuyerType, LandLead } from '@/types';
import { Building2, Landmark, Home, Gem, Star, Phone, Mail, CheckCircle } from 'lucide-react';

// ── Buyer type config ─────────────────────────────────────────────────────────
const BUYER_TYPES: Record<LandBuyerType, {
  label: string;
  icon: React.ElementType;
  color: string;
  bg: string;
  border: string;
  description: string;
  hotButtons: string[];
}> = {
  builder: {
    label: 'Builders',
    icon: Building2,
    color: 'text-blue-700',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    description: 'Residential / commercial developers looking to build. Pay premium for infill lots.',
    hotButtons: ['Infill lot', 'City utilities', 'Single family zoning', 'Quick close'],
  },
  land_banker: {
    label: 'Land Bankers',
    icon: Landmark,
    color: 'text-purple-700',
    bg: 'bg-purple-50',
    border: 'border-purple-200',
    description: 'Long-term investors accumulating raw land for future appreciation or development.',
    hotButtons: ['Large acreage', 'Agricultural zoning', 'Below TAV', 'No utilities needed'],
  },
  trailer_park: {
    label: 'Trailer Park Owners',
    icon: Home,
    color: 'text-orange-700',
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    description: 'MHP investors looking for land to develop or expand mobile home communities.',
    hotButtons: ['Multi-acre', 'No flood zone', 'Access road', 'Affordable market'],
  },
  mineral_rights: {
    label: 'Mineral Rights Buyers',
    icon: Gem,
    color: 'text-green-700',
    bg: 'bg-green-50',
    border: 'border-green-200',
    description: 'Buyers acquiring subsurface rights for oil, gas, or mineral extraction.',
    hotButtons: ['Texas / Oklahoma', 'Producing mineral rights', 'Royalty income', 'Severed rights'],
  },
};

function useLandBuyers() {
  return useQuery({
    queryKey: ['land_buyers'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('buyers')
        .select('*')
        .eq('buys_land', true)
        .eq('active', true)
        .order('deals_closed', { ascending: false });
      if (error) throw error;
      return (data ?? []) as LandBuyer[];
    },
  });
}

function BuyerCard({ buyer, lead }: { buyer: LandBuyer; lead?: LandLead }) {
  const typeConfig = buyer.land_buyer_type ? BUYER_TYPES[buyer.land_buyer_type] : null;
  const Icon = typeConfig?.icon ?? Building2;

  // Infill match highlight
  const infillMatch = lead?.infill_lot && buyer.buys_infill;

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${typeConfig?.border ?? 'border-gray-200'} ${typeConfig?.bg ?? 'bg-white'}`}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-lg ${typeConfig?.bg ?? 'bg-gray-50'}`}>
            <Icon className={`h-4 w-4 ${typeConfig?.color ?? 'text-gray-500'}`} />
          </div>
          <div>
            <p className="text-sm font-bold text-gray-900">
              {buyer.first_name} {buyer.last_name}
              {buyer.company && <span className="text-gray-500 font-normal"> · {buyer.company}</span>}
            </p>
            {typeConfig && (
              <span className={`text-xs font-medium ${typeConfig.color}`}>{typeConfig.label}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {infillMatch && (
            <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-[#E8720C] text-white flex items-center gap-1">
              <Star className="h-3 w-3" /> Infill Match
            </span>
          )}
          {buyer.pof_verified && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 flex items-center gap-1">
              <CheckCircle className="h-3 w-3" /> POF
            </span>
          )}
        </div>
      </div>

      {/* Buy box */}
      <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
        {buyer.target_acres_min != null && (
          <div><span className="text-gray-400">Acres:</span> {buyer.target_acres_min}–{buyer.target_acres_max ?? '∞'}</div>
        )}
        {buyer.min_price != null && (
          <div><span className="text-gray-400">Budget:</span> ${(buyer.min_price/1000).toFixed(0)}k–${buyer.max_price ? (buyer.max_price/1000).toFixed(0)+'k' : '∞'}</div>
        )}
        {buyer.preferred_zoning && buyer.preferred_zoning.length > 0 && (
          <div className="col-span-2">
            <span className="text-gray-400">Zoning: </span>
            {buyer.preferred_zoning.map(z => z.replace('_', ' ')).join(', ')}
          </div>
        )}
        {buyer.target_zips && buyer.target_zips.length > 0 && (
          <div className="col-span-2">
            <span className="text-gray-400">Zip codes: </span>
            {buyer.target_zips.slice(0, 5).join(', ')}{buyer.target_zips.length > 5 ? ` +${buyer.target_zips.length - 5}` : ''}
          </div>
        )}
        <div><span className="text-gray-400">Deals closed:</span> {buyer.deals_closed}</div>
        {buyer.close_speed_days && (
          <div><span className="text-gray-400">Close speed:</span> {buyer.close_speed_days}d</div>
        )}
      </div>

      {/* Contact */}
      <div className="flex items-center gap-3 pt-1 border-t border-white/60">
        {buyer.phone && (
          <a href={`tel:${buyer.phone}`} className={`flex items-center gap-1 text-xs font-medium ${typeConfig?.color ?? 'text-gray-700'} hover:underline`}>
            <Phone className="h-3 w-3" /> {buyer.phone}
          </a>
        )}
        {buyer.email && (
          <a href={`mailto:${buyer.email}`} className={`flex items-center gap-1 text-xs font-medium ${typeConfig?.color ?? 'text-gray-700'} hover:underline`}>
            <Mail className="h-3 w-3" /> {buyer.email}
          </a>
        )}
      </div>
    </div>
  );
}

function BuyerTypeSection({ type, buyers, lead }: { type: LandBuyerType; buyers: LandBuyer[]; lead?: LandLead }) {
  const cfg = BUYER_TYPES[type];
  const Icon = cfg.icon;
  const typeBuyers = buyers.filter(b => b.land_buyer_type === type);

  return (
    <div className="space-y-3">
      {/* Section header */}
      <div className={`flex items-start gap-3 p-3 rounded-xl border ${cfg.border} ${cfg.bg}`}>
        <div className="p-2 rounded-lg bg-white/60">
          <Icon className={`h-5 w-5 ${cfg.color}`} />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <p className={`text-sm font-bold ${cfg.color}`}>{cfg.label}</p>
            <span className="text-xs font-medium bg-white/60 px-2 py-0.5 rounded-full text-gray-600">
              {typeBuyers.length} buyer{typeBuyers.length !== 1 ? 's' : ''}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{cfg.description}</p>
          <div className="flex flex-wrap gap-1 mt-2">
            {cfg.hotButtons.map(btn => (
              <span key={btn} className={`text-xs px-2 py-0.5 rounded-full font-medium bg-white/70 ${cfg.color}`}>{btn}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Buyer cards */}
      {typeBuyers.length > 0 ? (
        <div className="grid grid-cols-1 gap-3">
          {typeBuyers.map(b => <BuyerCard key={b.id} buyer={b} lead={lead} />)}
        </div>
      ) : (
        <p className="text-xs text-gray-400 italic pl-2">No {cfg.label.toLowerCase()} in your buyer list yet.</p>
      )}
    </div>
  );
}

interface Props {
  lead?: LandLead;
}

export function LandBuyerHub({ lead }: Props) {
  const { data: buyers = [], isLoading } = useLandBuyers();

  const infillBuyers = buyers.filter(b => b.buys_infill);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-bold text-[#1B3A5C]">Land Buyer Hub</h3>
        <p className="text-xs text-gray-500 mt-0.5">
          {buyers.length} active land buyers across 4 categories
        </p>
      </div>

      {/* Infill lot callout */}
      {lead?.infill_lot && (
        <div className="bg-[#E8720C]/10 border border-[#E8720C]/30 rounded-xl p-4 flex items-start gap-3">
          <Star className="h-5 w-5 text-[#E8720C] shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-bold text-[#E8720C]">Infill Lot Flagged — Premium Opportunity</p>
            <p className="text-xs text-gray-600 mt-0.5">
              This is a House-Land-House configuration. Builders pay a premium for infill lots.
              {infillBuyers.length > 0 && ` You have ${infillBuyers.length} buyer${infillBuyers.length > 1 ? 's' : ''} who specifically buy infill.`}
            </p>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-gray-400">
          <div className="h-5 w-5 border-2 border-gray-300 border-t-[#1B3A5C] rounded-full animate-spin mr-2" />
          Loading buyers…
        </div>
      ) : (
        <div className="space-y-8">
          {(Object.keys(BUYER_TYPES) as LandBuyerType[]).map(type => (
            <BuyerTypeSection key={type} type={type} buyers={buyers} lead={lead} />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400 text-center">
        Add land buyers via the Buyers page — set "Buys Land" = true and assign a land buyer type.
      </p>
    </div>
  );
}
