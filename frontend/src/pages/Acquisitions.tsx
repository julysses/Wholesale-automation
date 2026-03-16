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
import type { CallClassification, CallDisposition } from '@/lib/retellAdapter';
import { cn } from '@/lib/utils';
import {
  Flame, TrendingUp, CalendarCheck, Phone, Mic,
  ChevronDown, ChevronUp, AlertTriangle, Clock,
  DollarSign, Home, User, MessageSquare, ExternalLink,
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
  call_duration?: number;
  called_at?: string;
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
      const latestCall = Object.fromEntries(
        (calls ?? []).reduce<[string, typeof calls[0]][]>((acc, c) => {
          if (!acc.find(([id]) => id === c.lead_id)) {
            acc.push([c.lead_id, c]);
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

function LeadCard({ lead }: { lead: AcquisitionLead }) {
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
                {Object.entries(qual.score_breakdown).map(([key, pts]) => (
                  <span key={key} className={cn(
                    'text-xs px-1.5 py-0.5 rounded border font-medium',
                    pts > 0
                      ? 'bg-green-50 text-green-700 border-green-200'
                      : 'bg-red-50 text-red-700 border-red-200',
                  )}>
                    {key.replace(/_/g, ' ')} {pts > 0 ? `+${pts}` : pts}
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
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = 'hot' | 'warm' | 'appointments';

export function Acquisitions() {
  const [tab, setTab] = useState<Tab>('hot');

  const { data: hotLeads = [], isLoading: hotLoading }  = useAcquisitionLeads('HOT');
  const { data: warmLeads = [], isLoading: warmLoading } = useAcquisitionLeads('WARM');
  const { data: appointments = [] }                      = useAppointments();

  const tabs: { key: Tab; label: string; icon: React.ElementType; count?: number; color: string }[] = [
    { key: 'hot',          label: 'HOT Leads',    icon: Flame,        count: hotLeads.length,    color: 'text-red-600' },
    { key: 'warm',         label: 'WARM Leads',   icon: TrendingUp,   count: warmLeads.length,   color: 'text-orange-600' },
    { key: 'appointments', label: 'Appointments', icon: CalendarCheck, count: appointments.length, color: 'text-blue-600' },
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

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
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

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                tab === t.key
                  ? `border-current ${t.color}`
                  : 'border-transparent text-gray-500 hover:text-gray-700',
              )}
            >
              <t.icon className="h-4 w-4" />
              {t.label}
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
          {hotLeads.map((lead) => <LeadCard key={lead.id} lead={lead} />)}
        </div>
      )}

      {tab === 'warm' && (
        <div className="space-y-3">
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
          {warmLeads.map((lead) => <LeadCard key={lead.id} lead={lead} />)}
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
