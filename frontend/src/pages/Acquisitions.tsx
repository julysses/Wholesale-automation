import { apiFetch } from '@/lib/api';
/**
 * Acquisitions Dashboard
 *
 * Displays HOT leads, WARM leads, appointment schedule, seller sentiment,
 * offer recommendations, call transcripts, and call recordings.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { formatCurrency, formatDate } from '@/lib/utils';
import { classificationColor, dispositionLabel } from '@/lib/retellAdapter';
import { StrategyComparisonPanel } from '@/components/dashboard/StrategyComparisonPanel';
import type { CallClassification, CallDisposition } from '@/lib/retellAdapter';
import { cn } from '@/lib/utils';
import {
  Flame, TrendingUp, CalendarCheck, Phone, Mic,
  ChevronDown, ChevronUp, AlertTriangle, Clock,
  DollarSign, Home, User, MessageSquare, ExternalLink, Send,
  BarChart2, Hammer, Lightbulb, ShieldCheck, ArrowRight, Plus, Loader2, Download,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

// ── Types ─────────────────────────────────────────────────────────────────────

interface QualResult {
  id: string;
  call_id: string;
  lead_id: string | null;
  timeline: string;
  condition: string;
  occupancy: string;
  asking_price: number | null;
  mortgage_balance: number | null;
  sentiment: string;
  qualification_score: number;
  classification: CallClassification;
  offer_range_low: number | null;
  offer_range_high: number | null;
  summary: string;
  key_quotes: string[];
  score_breakdown: Record<string, number> | null;
  created_at: string;
}

interface AcquisitionLead {
  id: string;
  property_address: string;
  city: string;
  state: string;
  zip_code: string;
  owner_first_name: string | null;
  owner_last_name: string | null;
  seller_score: number | null;
  estimated_arv: number | null;
  mao: number | null;
  stack_name: string | null;
  // Joined from ai_call_records + qualification_results
  latest_call_id?: string;
  disposition?: CallDisposition;
  qual?: QualResult;
  recording_url?: string | null;
  transcript?: string | null;
  call_duration?: number | null;
  called_at?: string | null;
}

interface Appointment {
  id: string;
  lead_id: string;
  scheduled_at: string;
  appointment_type: string;
  status: string;
  notes: string | null;
  lead?: { property_address: string; owner_first_name: string | null; owner_last_name: string | null };
}

interface DealAnalysis {
  id: string;
  lead_id: string | null;
  arv_low: number | null;
  arv_mid: number | null;
  arv_high: number | null;
  arv_confidence: string | null;
  repair_tier: string | null;
  repair_tier_label: string | null;
  repair_cost_low: number | null;
  repair_cost_high: number | null;
  mao: number | null;
  as_is_value: number | null;
  offer_range_low: number | null;
  offer_range_high: number | null;
  projected_assignment_fee: number | null;
  exit_strategy: string | null;
  is_viable: boolean;
  weak_deal_reasons: string[] | null;
  summary: string | null;
  analyzed_at: string;
  // Joined
  property_address?: string;
  owner_name?: string;
}

interface OfferRec {
  id: string;
  lead_id: string | null;
  opening_offer: number | null;
  target_offer: number | null;
  ceiling_offer: number | null;
  pain_points: string[] | null;
  motivation_level: string | null;
  primary_exit: string | null;
  exit_rationale: string | null;
  opening_script: string | null;
  closing_notes: string | null;
  objection_handlers: Array<{ objection: string; response: string }> | null;
  generated_at: string;
  // Joined
  property_address?: string;
  owner_name?: string;
}

// ── Hooks ─────────────────────────────────────────────────────────────────────

function useAcquisitionLeads(classification: CallClassification) {
  return useQuery<AcquisitionLead[]>({
    queryKey: ['acquisition_leads', classification],
    queryFn: async () => {
      // Get qualification results for this classification, newest first
      const { data: quals, error } = await supabase
        .from('qualification_results')
        .select('*')
        .eq('classification', classification)
        .order('created_at', { ascending: false })
        .limit(50);

      if (error || !quals?.length) return [];

      // Gather unique lead_ids
      const leadIds = [...new Set(quals.map((q) => q.lead_id).filter(Boolean))];
      if (!leadIds.length) return [];

      const { data: leads } = await supabase
        .from('leads')
        .select('id, property_address, city, state, zip_code, owner_first_name, owner_last_name, seller_score, estimated_arv, mao, stack_name')
        .in('id', leadIds);

      // Get latest call record per lead
      const { data: calls } = await supabase
        .from('ai_call_records')
        .select('lead_id, call_id, disposition, recording_url, duration_sec, created_at')
        .in('lead_id', leadIds)
        .order('created_at', { ascending: false });

      // Get transcripts
      const callIds = (calls ?? []).map((c) => c.call_id);
      const { data: transcripts } = callIds.length
        ? await supabase
            .from('call_transcripts')
            .select('call_id, raw_transcript')
            .in('call_id', callIds)
        : { data: [] };

      const transcriptMap = Object.fromEntries(
        (transcripts ?? []).map((t) => [t.call_id, t.raw_transcript])
      );

      // Latest call per lead
      type CallRow = { lead_id: string; call_id: string; disposition: string; recording_url: string | null; duration_sec: number | null; created_at: string };
      const latestCall = Object.fromEntries(
        (calls ?? []).reduce<[string, CallRow][]>((acc, c) => {
          if (!acc.find(([id]) => id === c.lead_id)) {
            acc.push([c.lead_id, c as CallRow]);
          }
          return acc;
        }, [])
      );

      // Latest qual per lead
      const latestQual = Object.fromEntries(
        quals.reduce<[string, QualResult][]>((acc, q) => {
          if (q.lead_id && !acc.find(([id]) => id === q.lead_id)) {
            acc.push([q.lead_id, q]);
          }
          return acc;
        }, [])
      );

      return (leads ?? []).map((lead) => {
        const call = latestCall[lead.id];
        const qual = latestQual[lead.id];
        return {
          ...lead,
          latest_call_id: call?.call_id,
          disposition: call?.disposition as CallDisposition,
          qual,
          recording_url: call?.recording_url,
          transcript: call ? transcriptMap[call.call_id] : null,
          call_duration: call?.duration_sec,
          called_at: call?.created_at,
        };
      }).sort((a, b) =>
        (b.qual?.qualification_score ?? 0) - (a.qual?.qualification_score ?? 0)
      );
    },
    staleTime: 30000,
    refetchInterval: 60000,
  });
}

function useDealAnalyses() {
  return useQuery<DealAnalysis[]>({
    queryKey: ['deal_analyses'],
    queryFn: async () => {
      const { data: analyses } = await supabase
        .from('deal_analyses')
        .select('*')
        .eq('is_viable', true)
        .order('analyzed_at', { ascending: false })
        .limit(30);
      if (!analyses?.length) return [];

      const leadIds = [...new Set(analyses.map((a) => a.lead_id).filter(Boolean))];
      const { data: leads } = leadIds.length
        ? await supabase
            .from('leads')
            .select('id, property_address, owner_first_name, owner_last_name')
            .in('id', leadIds)
        : { data: [] };

      const leadMap = Object.fromEntries((leads ?? []).map((l) => [l.id, l]));
      return analyses.map((a) => {
        const l = leadMap[a.lead_id ?? ''];
        return {
          ...a,
          property_address: l?.property_address,
          owner_name: l ? `${l.owner_first_name ?? ''} ${l.owner_last_name ?? ''}`.trim() : undefined,
        };
      });
    },
    staleTime: 60000,
  });
}

function useOfferRecs() {
  return useQuery<OfferRec[]>({
    queryKey: ['offer_recommendations'],
    queryFn: async () => {
      const { data: recs } = await supabase
        .from('offer_recommendations')
        .select('*')
        .order('generated_at', { ascending: false })
        .limit(20);
      if (!recs?.length) return [];

      const leadIds = [...new Set(recs.map((r) => r.lead_id).filter(Boolean))];
      const { data: leads } = leadIds.length
        ? await supabase
            .from('leads')
            .select('id, property_address, owner_first_name, owner_last_name')
            .in('id', leadIds)
        : { data: [] };

      const leadMap = Object.fromEntries((leads ?? []).map((l) => [l.id, l]));
      return recs.map((r) => {
        const l = leadMap[r.lead_id ?? ''];
        return {
          ...r,
          property_address: l?.property_address,
          owner_name: l ? `${l.owner_first_name ?? ''} ${l.owner_last_name ?? ''}`.trim() : undefined,
        };
      });
    },
    staleTime: 60000,
  });
}

function useAppointments() {
  return useQuery<Appointment[]>({
    queryKey: ['upcoming_appointments'],
    queryFn: async () => {
      const { data } = await supabase
        .from('appointments')
        .select('*, lead:lead_id(property_address, owner_first_name, owner_last_name)')
        .in('status', ['scheduled', 'confirmed'])
        .gte('scheduled_at', new Date().toISOString())
        .order('scheduled_at', { ascending: true })
        .limit(20);
      return (data ?? []) as Appointment[];
    },
    staleTime: 60000,
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SentimentBadge({ sentiment }: { sentiment: string }) {
  const map: Record<string, { label: string; class: string }> = {
    motivated:     { label: 'Motivated',     class: 'bg-green-100 text-green-800 border-green-200' },
    neutral:       { label: 'Neutral',       class: 'bg-gray-100 text-gray-600 border-gray-200' },
    hesitant:      { label: 'Hesitant',      class: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
    not_interested:{ label: 'Not Interested',class: 'bg-red-100 text-red-700 border-red-200' },
  };
  const s = map[sentiment] ?? { label: sentiment, class: 'bg-gray-100 text-gray-500 border-gray-200' };
  return (
    <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium border', s.class)}>
      {s.label}
    </span>
  );
}

function TranscriptViewer({ transcript }: { transcript: string }) {
  const [open, setOpen] = useState(false);
  const lines = transcript.split('\n').filter(Boolean);
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium"
      >
        <MessageSquare className="h-3.5 w-3.5" />
        {open ? 'Hide transcript' : 'View transcript'}
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>
      {open && (
        <div className="mt-2 max-h-64 overflow-y-auto bg-gray-50 rounded-lg p-3 space-y-1.5 border border-gray-200">
          {lines.map((line, i) => {
            const isAgent = /^agent:/i.test(line);
            const content = line.replace(/^(agent|seller|user|owner):\s*/i, '');
            return (
              <div key={i} className={cn('flex gap-2 text-xs', isAgent ? 'text-blue-700' : 'text-gray-700')}>
                <span className={cn('shrink-0 font-semibold w-10', isAgent ? 'text-blue-500' : 'text-gray-500')}>
                  {isAgent ? 'AI' : 'You'}
                </span>
                <span>{content}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function LeadCard({ lead, onSchedule }: { lead: AcquisitionLead; onSchedule?: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const qual = lead.qual;
  const colors = qual ? classificationColor(qual.classification) : classificationColor('COLD');
  const ownerName = [lead.owner_first_name, lead.owner_last_name].filter(Boolean).join(' ') || 'Unknown';

  return (
    <div className={cn(
      'border rounded-xl p-4 hover:shadow-md transition-shadow',
      qual?.classification === 'HOT'
        ? 'border-red-200 bg-red-50/30'
        : 'border-gray-200 bg-white',
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {qual && (
              <span className={cn(
                'px-2 py-0.5 rounded-full text-xs font-bold border',
                colors.bg, colors.text, colors.border,
              )}>
                {qual.classification} {qual.qualification_score}
              </span>
            )}
            {lead.stack_name && lead.stack_name !== 'Single Signal' && (
              <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full border border-orange-200">
                {lead.stack_name}
              </span>
            )}
            {lead.seller_score && (
              <span className="text-xs text-gray-500">Seller score: {lead.seller_score}</span>
            )}
          </div>
          <p className="font-semibold text-gray-900 mt-1 truncate">{lead.property_address}</p>
          <p className="text-xs text-gray-500">{lead.city}, {lead.state} {lead.zip_code}</p>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 rounded hover:bg-gray-100 text-gray-400 shrink-0"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {/* Quick stats */}
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-600">
        <span className="flex items-center gap-1"><User className="h-3.5 w-3.5 text-gray-400" />{ownerName}</span>
        {qual?.timeline && (
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5 text-gray-400" />
            {qual.timeline.replace(/_/g, ' ')}
          </span>
        )}
        {qual?.occupancy && (
          <span className="flex items-center gap-1">
            <Home className="h-3.5 w-3.5 text-gray-400" />
            {qual.occupancy.replace(/_/g, ' ')}
          </span>
        )}
        {qual?.sentiment && <SentimentBadge sentiment={qual.sentiment} />}
      </div>

      {/* Offer range / asking price */}
      {(qual?.offer_range_low || qual?.asking_price) && (
        <div className="mt-2 flex gap-4 text-xs">
          {qual.asking_price && (
            <div>
              <span className="text-gray-400">Asking</span>
              <span className="ml-1 font-semibold text-gray-700">{formatCurrency(qual.asking_price)}</span>
            </div>
          )}
          {qual.offer_range_low && qual.offer_range_high && (
            <div>
              <span className="text-gray-400">Offer range</span>
              <span className="ml-1 font-semibold text-green-700">
                {formatCurrency(qual.offer_range_low)} – {formatCurrency(qual.offer_range_high)}
              </span>
            </div>
          )}
          {lead.estimated_arv && (
            <div>
              <span className="text-gray-400">ARV</span>
              <span className="ml-1 font-semibold text-blue-700">{formatCurrency(lead.estimated_arv)}</span>
            </div>
          )}
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="mt-3 pt-3 border-t border-gray-200 space-y-2">
          {/* Summary */}
          {qual?.summary && (
            <p className="text-xs text-gray-600 italic">"{qual.summary}"</p>
          )}

          {/* Key quotes */}
          {qual?.key_quotes && qual.key_quotes.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Key quotes</p>
              {qual.key_quotes.slice(0, 3).map((q, i) => (
                <p key={i} className="text-xs text-gray-600 pl-2 border-l-2 border-orange-200 mb-1">
                  "{q}"
                </p>
              ))}
            </div>
          )}

          {/* Score breakdown */}
          {qual?.score_breakdown && Object.keys(qual.score_breakdown).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Score breakdown</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(qual.score_breakdown ?? {}).map(([key, pts]) => (
                  <span key={key} className={cn(
                    'text-xs px-1.5 py-0.5 rounded border font-medium',
                    (pts as number) > 0
                      ? 'bg-green-50 text-green-700 border-green-200'
                      : 'bg-red-50 text-red-700 border-red-200',
                  )}>
                    {key.replace(/_/g, ' ')} {(pts as number) > 0 ? `+${pts}` : pts}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Recording + call meta */}
          <div className="flex items-center gap-3 text-xs text-gray-500">
            {lead.called_at && (
              <span className="flex items-center gap-1">
                <Phone className="h-3.5 w-3.5" />
                {formatDistanceToNow(new Date(lead.called_at), { addSuffix: true })}
              </span>
            )}
            {lead.call_duration && (
              <span>{Math.round(lead.call_duration / 60)}m {lead.call_duration % 60}s</span>
            )}
            {lead.recording_url && (
              <a
                href={lead.recording_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-blue-600 hover:text-blue-800"
              >
                <Mic className="h-3.5 w-3.5" />
                Recording
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          {/* Transcript viewer */}
          {lead.transcript && <TranscriptViewer transcript={lead.transcript} />}

          {onSchedule && (
            <div className="pt-3 border-t border-gray-100 flex justify-end">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSchedule(lead.id);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 text-white text-[11px] font-bold rounded-lg hover:bg-teal-700 transition-colors shadow-sm"
              >
                <CalendarCheck className="h-3.5 w-3.5" />
                Schedule Appointment
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RepairTierBadge({ tier }: { tier: string }) {
  const styles: Record<string, string> = {
    light:    'bg-green-100 text-green-700 border-green-200',
    moderate: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    heavy:    'bg-orange-100 text-orange-700 border-orange-200',
    full_gut: 'bg-red-100 text-red-700 border-red-200',
  };
  const labels: Record<string, string> = {
    light: 'Light', moderate: 'Moderate', heavy: 'Heavy', full_gut: 'Full Gut',
  };
  return (
    <span className={cn(
      'text-xs px-2 py-0.5 rounded-full border font-semibold',
      styles[tier] ?? 'bg-gray-100 text-gray-500 border-gray-200',
    )}>
      <Hammer className="h-3 w-3 inline mr-0.5" />
      {labels[tier] ?? tier} Renovation
    </span>
  );
}

function ExitStrategyBadge({ strategy }: { strategy: string }) {
  const map: Record<string, { label: string; style: string }> = {
    wholesale_assignment: { label: 'Wholesale',  style: 'bg-blue-100 text-blue-700 border-blue-200' },
    novation_agreement:   { label: 'Novation',   style: 'bg-purple-100 text-purple-700 border-purple-200' },
    wholetail:            { label: 'Wholetail',  style: 'bg-teal-100 text-teal-700 border-teal-200' },
    investor_resale:      { label: 'Inv. Resale',style: 'bg-indigo-100 text-indigo-700 border-indigo-200' },
    too_risky:            { label: 'Too Risky',  style: 'bg-red-100 text-red-700 border-red-200' },
  };
  const { label, style } = map[strategy] ?? { label: strategy, style: 'bg-gray-100 text-gray-500 border-gray-200' };
  return (
    <span className={cn('text-xs px-2 py-0.5 rounded-full border font-semibold', style)}>
      {label}
    </span>
  );
}

function DealAnalysisCard({ deal }: { deal: DealAnalysis }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {deal.exit_strategy && <ExitStrategyBadge strategy={deal.exit_strategy} />}
            {deal.repair_tier && <RepairTierBadge tier={deal.repair_tier} />}
            {deal.arv_confidence && (
              <span className="text-xs text-gray-400">ARV confidence: {deal.arv_confidence}</span>
            )}
          </div>
          <p className="font-semibold text-gray-900 mt-1 truncate">{deal.property_address ?? 'Unknown'}</p>
          {deal.owner_name && <p className="text-xs text-gray-500">{deal.owner_name}</p>}
        </div>
        <button onClick={() => setOpen(!open)} className="p-1 rounded hover:bg-gray-100 text-gray-400 shrink-0">
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {/* Key numbers */}
      <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        {[
          { label: 'ARV',       value: deal.arv_low   ? formatCurrency(deal.arv_low)   : '—', color: 'text-blue-700' },
          { label: 'Repairs',   value: deal.repair_cost_high ? formatCurrency(deal.repair_cost_high) : '—', color: 'text-orange-600' },
          { label: 'MAO',       value: deal.mao       ? formatCurrency(deal.mao)       : '—', color: 'text-gray-800' },
          { label: 'Proj. Fee', value: deal.projected_assignment_fee ? formatCurrency(deal.projected_assignment_fee) : '—', color: 'text-green-700' },
        ].map((s) => (
          <div key={s.label} className="bg-gray-50 rounded-lg p-2 border border-gray-100">
            <p className="text-gray-400">{s.label}</p>
            <p className={cn('font-bold', s.color)}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Offer range */}
      {deal.offer_range_low && deal.offer_range_high && (
        <div className="mt-2 text-xs">
          <span className="text-gray-400">Offer range: </span>
          <span className="font-semibold text-green-700">
            {formatCurrency(deal.offer_range_low)} – {formatCurrency(deal.offer_range_high)}
          </span>
        </div>
      )}

      {/* Expanded */}
      {open && (
        <div className="mt-3 pt-3 border-t border-gray-100 space-y-2">
          {deal.summary && <p className="text-xs text-gray-600 italic">{deal.summary}</p>}
          {deal.weak_deal_reasons && deal.weak_deal_reasons.length > 0 && (
            <div className="flex items-start gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
              <div className="text-xs text-amber-700 space-y-0.5">
                {deal.weak_deal_reasons.map((r, i) => <p key={i}>{r}</p>)}
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 text-xs">
            {deal.arv_mid && <div><span className="text-gray-400">ARV mid: </span><span className="font-medium">{formatCurrency(deal.arv_mid)}</span></div>}
            {deal.as_is_value && <div><span className="text-gray-400">As-is: </span><span className="font-medium">{formatCurrency(deal.as_is_value)}</span></div>}
            {deal.repair_cost_low && deal.repair_cost_high && (
              <div><span className="text-gray-400">Repair range: </span><span className="font-medium">{formatCurrency(deal.repair_cost_low)} – {formatCurrency(deal.repair_cost_high)}</span></div>
            )}
          </div>
          <p className="text-xs text-gray-400">
            Analyzed {formatDistanceToNow(new Date(deal.analyzed_at), { addSuffix: true })}
          </p>
        </div>
      )}
    </div>
  );
}

function OfferRecCard({ rec }: { rec: OfferRec }) {
  const [open, setOpen] = useState(false);
  const motivationColors: Record<string, string> = {
    urgent: 'text-red-700', high: 'text-orange-600', medium: 'text-yellow-600', low: 'text-gray-500',
  };
  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {rec.motivation_level && (
              <span className={cn(
                'text-xs font-semibold capitalize px-2 py-0.5 rounded-full border',
                rec.motivation_level === 'urgent'
                  ? 'bg-red-100 border-red-200 text-red-700'
                  : rec.motivation_level === 'high'
                  ? 'bg-orange-100 border-orange-200 text-orange-700'
                  : 'bg-gray-100 border-gray-200 text-gray-600',
              )}>
                {rec.motivation_level} motivation
              </span>
            )}
            {rec.primary_exit && <ExitStrategyBadge strategy={rec.primary_exit} />}
          </div>
          <p className="font-semibold text-gray-900 mt-1 truncate">{rec.property_address ?? 'Unknown'}</p>
          {rec.owner_name && <p className="text-xs text-gray-500">{rec.owner_name}</p>}
        </div>
        <button onClick={() => setOpen(!open)} className="p-1 rounded hover:bg-gray-100 text-gray-400 shrink-0">
          {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {/* Offer trio */}
      <div className="mt-3 flex gap-3 text-xs">
        {[
          { label: 'Open with', value: rec.opening_offer, color: 'text-gray-700' },
          { label: 'Target',    value: rec.target_offer,  color: 'text-blue-700' },
          { label: 'Ceiling',   value: rec.ceiling_offer, color: 'text-red-700' },
        ].map((o) => (
          <div key={o.label} className="flex-1 bg-gray-50 rounded-lg p-2 border border-gray-100 text-center">
            <p className="text-gray-400">{o.label}</p>
            <p className={cn('font-bold', o.color)}>{o.value ? formatCurrency(o.value) : '—'}</p>
          </div>
        ))}
      </div>

      {/* Pain points */}
      {rec.pain_points && rec.pain_points.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {rec.pain_points.slice(0, 3).map((p, i) => (
            <span key={i} className="text-xs bg-amber-50 text-amber-700 border border-amber-100 px-2 py-0.5 rounded-full">
              {p}
            </span>
          ))}
        </div>
      )}

      {/* Expanded */}
      {open && (
        <div className="mt-3 pt-3 border-t border-gray-100 space-y-3">
          {rec.opening_script && (
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1 flex items-center gap-1">
                <Lightbulb className="h-3.5 w-3.5" /> Opening script
              </p>
              <p className="text-xs text-gray-700 bg-blue-50 border border-blue-100 rounded-lg p-2.5 italic">
                "{rec.opening_script}"
              </p>
            </div>
          )}
          {rec.exit_rationale && (
            <p className="text-xs text-gray-500">
              <span className="font-semibold">Exit rationale:</span> {rec.exit_rationale}
            </p>
          )}
          {rec.objection_handlers && rec.objection_handlers.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1 flex items-center gap-1">
                <ShieldCheck className="h-3.5 w-3.5" /> Objection handlers
              </p>
              <div className="space-y-2">
                {rec.objection_handlers.slice(0, 3).map((oh, i) => (
                  <div key={i} className="text-xs space-y-0.5">
                    <p className="font-medium text-gray-700 flex items-center gap-1">
                      <ArrowRight className="h-3 w-3 text-gray-400" />
                      "{oh.objection}"
                    </p>
                    <p className="text-gray-500 pl-4">{oh.response}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {rec.closing_notes && (
            <p className="text-xs text-gray-500 border-t border-gray-100 pt-2">
              <span className="font-semibold">Closing note:</span> {rec.closing_notes}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── CSV helpers ───────────────────────────────────────────────────────────────

function downloadCSV(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const keys = Object.keys(rows[0]);
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [keys.join(','), ...rows.map((r) => keys.map((k) => escape(r[k])).join(','))].join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function leadsToCSVRows(leads: AcquisitionLead[]) {
  return leads.map((l) => ({
    property_address: l.property_address,
    city: l.city,
    state: l.state,
    zip_code: l.zip_code,
    owner_name: [l.owner_first_name, l.owner_last_name].filter(Boolean).join(' '),
    stack_name: l.stack_name ?? '',
    seller_score: l.seller_score ?? '',
    classification: l.qual?.classification ?? '',
    qualification_score: l.qual?.qualification_score ?? '',
    sentiment: l.qual?.sentiment ?? '',
    asking_price: l.qual?.asking_price ?? '',
    offer_range_low: l.qual?.offer_range_low ?? '',
    offer_range_high: l.qual?.offer_range_high ?? '',
    estimated_arv: l.estimated_arv ?? '',
    mao: l.mao ?? '',
    called_at: l.called_at ?? '',
  }));
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = 'hot' | 'warm' | 'deal_analysis' | 'negotiation' | 'appointments';

export function Acquisitions() {
  const [tab, setTab] = useState<Tab>('hot');
  const [bulkSmsLoading, setBulkSmsLoading] = useState(false);
  const [showApptModal, setShowApptModal] = useState(false);
  const [selectedLeadForAppt, setSelectedLeadForAppt] = useState<string | null>(null);
  const [newAppt, setNewAppt] = useState({ date: '', time: '', type: 'phone', notes: '' });
  const [submittingAppt, setSubmittingAppt] = useState(false);

  const { data: hotLeads = [], isLoading: hotLoading }    = useAcquisitionLeads('HOT');
  const { data: warmLeads = [], isLoading: warmLoading, refetch: refetchWarm }  = useAcquisitionLeads('WARM');
  const { data: deals = [], isLoading: dealsLoading }     = useDealAnalyses();
  const { data: offerRecs = [], isLoading: recsLoading }  = useOfferRecs();
  const { data: appointments = [], refetch: refetchAppts }                       = useAppointments();

  const handleBulkSMS = async () => {
    if (!confirm(`Are you sure you want to send a follow-up SMS to all ${warmLeads.length} warm leads?`)) return;
    setBulkSmsLoading(true);
    try {
      const resp = await apiFetch('/api/marketing/bulk-sms-warm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (resp.ok) {
        alert('Bulk SMS sequence initiated successfully.');
      } else {
        alert('Failed to initiate bulk SMS.');
      }
    } catch (err) {
      alert('Error: ' + err);
    } finally {
      setBulkSmsLoading(false);
    }
  };

  const handleScheduleAppt = async () => {
    if (!selectedLeadForAppt || !newAppt.date || !newAppt.time) return;
    setSubmittingAppt(true);
    try {
      const scheduledAt = new Date(`${newAppt.date}T${newAppt.time}`);
      const resp = await apiFetch('/api/appointments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lead_id: selectedLeadForAppt,
          scheduled_at: scheduledAt.toISOString(),
          appointment_type: newAppt.type,
          notes: newAppt.notes,
        }),
      });
      if (resp.ok) {
        setShowApptModal(false);
        setNewAppt({ date: '', time: '', type: 'phone', notes: '' });
        setSelectedLeadForAppt(null);
        refetchAppts();
      } else {
        alert('Failed to schedule appointment.');
      }
    } catch (err) {
      alert('Error: ' + err);
    } finally {
      setSubmittingAppt(false);
    }
  };

  const tabs: { key: Tab; label: string; icon: React.ElementType; count?: number; color: string }[] = [
    { key: 'hot',          label: 'HOT Leads',      icon: Flame,        count: hotLeads.length,    color: 'text-red-600' },
    { key: 'warm',         label: 'WARM Leads',     icon: TrendingUp,   count: warmLeads.length,   color: 'text-orange-600' },
    { key: 'deal_analysis',label: 'Deal Analysis',  icon: BarChart2,    count: deals.length,       color: 'text-blue-600' },
    { key: 'negotiation',  label: 'Negotiation',    icon: Lightbulb,    count: offerRecs.length,   color: 'text-purple-600' },
    { key: 'appointments', label: 'Appointments',   icon: CalendarCheck, count: appointments.length, color: 'text-teal-600' },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Acquisitions</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          AI-qualified sellers — HOT leads, WARM leads, and scheduled appointments
        </p>
      </div>

      {/* Strategy comparison (collapsible) */}
      <StrategyComparisonPanel />

      {/* Summary row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        {[
          { label: 'HOT Leads',     value: hotLeads.length,     icon: Flame,        bg: 'bg-red-50',    text: 'text-red-700', border: 'border-red-100' },
          { label: 'WARM Leads',    value: warmLeads.length,    icon: TrendingUp,   bg: 'bg-orange-50', text: 'text-orange-700', border: 'border-orange-100' },
          { label: 'Appointments',  value: appointments.length, icon: CalendarCheck,bg: 'bg-blue-50',   text: 'text-blue-700', border: 'border-blue-100' },
          {
            label: 'Avg HOT Score',
            value: hotLeads.length
              ? Math.round(hotLeads.reduce((s, l) => s + (l.qual?.qualification_score ?? 0), 0) / hotLeads.length)
              : '—',
            icon: DollarSign,
            bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-100',
          },
        ].map((s) => (
          <div key={s.label} className={cn(
            'rounded-xl border p-4 flex items-center gap-3',
            s.bg, s.border,
          )}>
            <s.icon className={cn('h-5 w-5 shrink-0', s.text)} />
            <div>
              <p className={cn('text-xl font-bold', s.text)}>{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs — scrollable on mobile */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-1 overflow-x-auto scrollbar-none -mb-px">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap shrink-0',
                tab === t.key
                  ? `border-current ${t.color}`
                  : 'border-transparent text-gray-500 hover:text-gray-700',
              )}
            >
              <t.icon className="h-4 w-4" />
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.label.split(' ')[0]}</span>
              {t.count !== undefined && t.count > 0 && (
                <span className={cn(
                  'text-xs rounded-full px-1.5 py-0.5 font-bold',
                  tab === t.key ? 'bg-current/10' : 'bg-gray-100 text-gray-500',
                )}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {tab === 'hot' && (
        <div className="space-y-3">
          {!hotLoading && hotLeads.length > 0 && (
            <div className="flex justify-end">
              <button
                onClick={() => {
                  const date = new Date().toISOString().slice(0, 10);
                  downloadCSV(`acquisitions-hot-${date}.csv`, leadsToCSVRows(hotLeads));
                }}
                className="flex items-center gap-2 px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                Download CSV
              </button>
            </div>
          )}
          {hotLoading && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
              ))}
            </div>
          )}
          {!hotLoading && hotLeads.length === 0 && (
            <div className="text-center py-16">
              <Flame className="h-12 w-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No HOT leads yet</p>
              <p className="text-sm text-gray-400 mt-1">
                HOT leads appear here when AI calls score ≥ 80
              </p>
            </div>
          )}
          {hotLeads.map((lead) => (
            <LeadCard
              key={lead.id}
              lead={lead}
              onSchedule={(id) => {
                setSelectedLeadForAppt(id);
                setShowApptModal(true);
              }}
            />
          ))}
        </div>
      )}

      {tab === 'warm' && (
        <div className="space-y-3">
          {!warmLoading && warmLeads.length > 0 && (
            <div className="flex justify-end gap-2 mb-2 flex-wrap">
              <button
                onClick={() => {
                  const date = new Date().toISOString().slice(0, 10);
                  downloadCSV(`acquisitions-warm-${date}.csv`, leadsToCSVRows(warmLeads));
                }}
                className="flex items-center gap-2 px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                Download CSV
              </button>
              <button
                onClick={handleBulkSMS}
                disabled={bulkSmsLoading}
                className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors text-sm font-medium shadow-sm disabled:opacity-50"
              >
                {bulkSmsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Bulk SMS All Warm Leads
              </button>
            </div>
          )}
          {warmLoading && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
              ))}
            </div>
          )}
          {!warmLoading && warmLeads.length === 0 && (
            <div className="text-center py-16">
              <TrendingUp className="h-12 w-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No WARM leads yet</p>
              <p className="text-sm text-gray-400 mt-1">
                WARM leads (score 50–79) are auto-enrolled in SMS sequences
              </p>
            </div>
          )}
          {warmLeads.map((lead) => (
            <LeadCard
              key={lead.id}
              lead={lead}
              onSchedule={(id) => {
                setSelectedLeadForAppt(id);
                setShowApptModal(true);
              }}
            />
          ))}
        </div>
      )}

      {tab === 'deal_analysis' && (
        <div className="space-y-3">
          {dealsLoading && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <div key={i} className="h-32 bg-gray-100 rounded-xl animate-pulse" />)}
            </div>
          )}
          {!dealsLoading && deals.length === 0 && (
            <div className="text-center py-16">
              <BarChart2 className="h-12 w-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No deal analyses yet</p>
              <p className="text-sm text-gray-400 mt-1">
                Deal analyses are generated automatically for HOT and WARM leads after qualification
              </p>
            </div>
          )}
          {deals.map((deal) => <DealAnalysisCard key={deal.id} deal={deal} />)}
        </div>
      )}

      {tab === 'negotiation' && (
        <div className="space-y-3">
          {recsLoading && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <div key={i} className="h-28 bg-gray-100 rounded-xl animate-pulse" />)}
            </div>
          )}
          {!recsLoading && offerRecs.length === 0 && (
            <div className="text-center py-16">
              <Lightbulb className="h-12 w-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No negotiation briefs yet</p>
              <p className="text-sm text-gray-400 mt-1">
                Negotiation briefs are generated for HOT leads with opening offers,
                objection handlers, and exit strategy recommendations
              </p>
            </div>
          )}
          {offerRecs.map((rec) => <OfferRecCard key={rec.id} rec={rec} />)}
        </div>
      )}

      {tab === 'appointments' && (
        <div className="space-y-3">
          {appointments.length === 0 && (
            <div className="text-center py-16">
              <CalendarCheck className="h-12 w-12 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No upcoming appointments</p>
              <p className="text-sm text-gray-400 mt-1">
                Appointments are created automatically when sellers agree to speak further
              </p>
            </div>
          )}
          {appointments.map((appt) => {
            const owner = [appt.lead?.owner_first_name, appt.lead?.owner_last_name].filter(Boolean).join(' ') || 'Unknown';
            const address = appt.lead?.property_address ?? 'Unknown address';
            const isToday = new Date(appt.scheduled_at).toDateString() === new Date().toDateString();
            return (
              <div key={appt.id} className={cn(
                'flex items-center gap-4 p-4 rounded-xl border bg-white hover:shadow-sm transition-shadow',
                isToday ? 'border-blue-200 bg-blue-50/30' : 'border-gray-200',
              )}>
                <div className={cn(
                  'p-2.5 rounded-lg shrink-0',
                  isToday ? 'bg-blue-100' : 'bg-gray-100',
                )}>
                  <CalendarCheck className={cn('h-5 w-5', isToday ? 'text-blue-600' : 'text-gray-500')} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-medium text-gray-900 truncate">{address}</p>
                    {isToday && (
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium border border-blue-200">
                        Today
                      </span>
                    )}
                    <span className={cn(
                      'text-xs px-2 py-0.5 rounded-full border font-medium capitalize',
                      appt.status === 'confirmed'
                        ? 'bg-green-50 text-green-700 border-green-200'
                        : 'bg-yellow-50 text-yellow-700 border-yellow-200',
                    )}>
                      {appt.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
                    <span className="flex items-center gap-1"><User className="h-3.5 w-3.5" />{owner}</span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" />
                      {new Date(appt.scheduled_at).toLocaleString('en-US', {
                        weekday: 'short', month: 'short', day: 'numeric',
                        hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
                      })}
                    </span>
                    <span className="capitalize">{appt.appointment_type.replace(/_/g, ' ')}</span>
                  </div>
                  {appt.notes && (
                    <p className="text-xs text-gray-400 mt-0.5 truncate">{appt.notes}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Appointment Modal */}
      {showApptModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6 animate-in fade-in zoom-in duration-200">
            <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
              <CalendarCheck className="h-5 w-5 text-teal-600" />
              Schedule Appointment
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-500 mb-1 capitalize">Property</label>
                <div className="text-sm font-medium text-gray-900 bg-gray-50 px-3 py-2 rounded-lg border">
                  {[...hotLeads, ...warmLeads].find(l => l.id === selectedLeadForAppt)?.property_address || 'Selected Lead'}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Date</label>
                  <input
                    type="date"
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    value={newAppt.date}
                    onChange={(e) => setNewAppt(p => ({ ...p, date: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-500 mb-1">Time</label>
                  <input
                    type="time"
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    value={newAppt.time}
                    onChange={(e) => setNewAppt(p => ({ ...p, time: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-500 mb-1">Type</label>
                <select
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                  value={newAppt.type}
                  onChange={(e) => setNewAppt(p => ({ ...p, type: e.target.value }))}
                >
                  <option value="phone">Phone Call</option>
                  <option value="video">Virtual Walkthrough (Video)</option>
                  <option value="in_person">In-Person Inspection</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-500 mb-1">Notes (Optional)</label>
                <textarea
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 outline-none resize-none"
                  rows={3}
                  placeholder="e.g., Seller wants to show the new roof..."
                  value={newAppt.notes}
                  onChange={(e) => setNewAppt(p => ({ ...p, notes: e.target.value }))}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => {
                    setShowApptModal(false);
                    setSelectedLeadForAppt(null);
                  }}
                  className="flex-1 px-4 py-2 border rounded-lg text-sm font-medium hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleScheduleAppt}
                  disabled={submittingAppt || !newAppt.date || !newAppt.time}
                  className="flex-1 px-4 py-2 bg-teal-600 text-white rounded-lg text-sm font-bold hover:bg-teal-700 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {submittingAppt ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarCheck className="h-4 w-4" />}
                  Confirm
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Blueprint funnel reminder */}
      <div className="mt-6 p-4 rounded-xl bg-gray-50 border border-gray-200">
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-xs text-gray-600">
            <span className="font-semibold">Blueprint target:</span> 30,000 AI calls →
            4,000 conversations → 500 interested → 150 warm → 40 appointments → 6 contracts/mo
            · Avg fee $10,000 · Goal: $60,000/mo
          </div>
        </div>
      </div>
    </div>
  );
}
