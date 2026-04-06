import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { cn, formatDate } from '@/lib/utils';
import { Phone, MessageSquare, Clock } from 'lucide-react';

interface FbLead {
  id: string;
  received_at: string;
  name: string | null;
  phone: string | null;
  property_address: string | null;
  situations: string[] | null;
  timeline: string | null;
  segment_tag: string | null;
  twilio_sms_sent: boolean;
  twilio_sms_time: string | null;
  contacted: boolean;
  appointment_set: boolean;
}

const SEGMENT_STYLES: Record<string, { bg: string; text: string }> = {
  'HOT-URGENT':      { bg: 'bg-red-100', text: 'text-red-700' },
  'HOT-ESTATE':      { bg: 'bg-red-100', text: 'text-red-700' },
  'HOT-LEGAL':       { bg: 'bg-red-100', text: 'text-red-700' },
  'HOT-TAX':         { bg: 'bg-red-100', text: 'text-red-700' },
  'WARM-LANDLORD':   { bg: 'bg-orange-100', text: 'text-orange-700' },
  'WARM-RELOCATION': { bg: 'bg-orange-100', text: 'text-orange-700' },
  'COLD-NURTURE':    { bg: 'bg-gray-100', text: 'text-gray-600' },
};

export function LeadIntakeRouter() {
  const { data: leads = [], isLoading } = useQuery<FbLead[]>({
    queryKey: ['fb_leads_recent'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('fb_leads')
        .select('*')
        .order('received_at', { ascending: false })
        .limit(50);
      if (error) throw error;
      return data || [];
    },
    staleTime: 30000,
    refetchInterval: 30000,
  });

  const hotLeads = leads.filter(l => l.segment_tag?.startsWith('HOT'));
  const warmLeads = leads.filter(l => l.segment_tag?.startsWith('WARM'));
  const coldLeads = leads.filter(l => l.segment_tag?.startsWith('COLD'));

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-semibold text-gray-900">Lead Intake Router</h2>
        <p className="text-xs text-gray-500">Real-time feed of Facebook leads with segment routing and Twilio SMS status</p>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-3 gap-4">
        <SummaryCard label="HOT Leads" count={hotLeads.length} color="red" />
        <SummaryCard label="WARM Leads" count={warmLeads.length} color="orange" />
        <SummaryCard label="COLD / Nurture" count={coldLeads.length} color="gray" />
      </div>

      {/* Lead feed */}
      {leads.length === 0 ? (
        <div className="text-center py-10 text-gray-500 text-sm border border-dashed border-gray-200 rounded-xl">
          No Facebook leads yet. Leads will appear here within seconds of form submission.
        </div>
      ) : (
        <div className="space-y-2">
          {leads.map(lead => {
            const segStyle = SEGMENT_STYLES[lead.segment_tag || ''] || { bg: 'bg-gray-100', text: 'text-gray-600' };
            const minutesAgo = Math.floor((Date.now() - new Date(lead.received_at).getTime()) / 60000);

            return (
              <div key={lead.id} className="flex items-center gap-4 p-4 bg-white border rounded-xl hover:shadow-sm transition-shadow">
                {/* Segment badge */}
                <span className={cn('text-xs font-semibold px-2 py-1 rounded-lg shrink-0 whitespace-nowrap', segStyle.bg, segStyle.text)}>
                  {lead.segment_tag || 'Unrouted'}
                </span>

                {/* Lead info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">
                    {lead.name || 'Unknown'} — {lead.property_address || 'No address'}
                  </p>
                  <div className="flex items-center gap-3 mt-0.5">
                    {lead.situations && lead.situations.length > 0 && (
                      <span className="text-xs text-gray-500">{lead.situations.join(', ')}</span>
                    )}
                    {lead.timeline && (
                      <span className="text-xs text-gray-400">· {lead.timeline}</span>
                    )}
                  </div>
                </div>

                {/* Contact preference */}
                <div className="flex items-center gap-2 shrink-0">
                  {lead.phone && <Phone className="h-3.5 w-3.5 text-gray-400" />}
                  <span className="text-xs text-gray-500">{lead.phone || '—'}</span>
                </div>

                {/* SMS status */}
                <div className="shrink-0">
                  {lead.twilio_sms_sent ? (
                    <div className="flex items-center gap-1 text-xs text-green-600">
                      <MessageSquare className="h-3.5 w-3.5" />
                      SMS sent
                    </div>
                  ) : (
                    <div className="flex items-center gap-1 text-xs text-amber-500">
                      <Clock className="h-3.5 w-3.5" />
                      Pending SMS
                    </div>
                  )}
                </div>

                {/* Status dots */}
                <div className="flex items-center gap-1.5 shrink-0">
                  <StatusDot active={lead.contacted} label="Contacted" />
                  <StatusDot active={lead.appointment_set} label="Appt" />
                </div>

                {/* Time */}
                <span className="text-xs text-gray-400 shrink-0">
                  {minutesAgo < 60
                    ? `${minutesAgo}m ago`
                    : minutesAgo < 1440
                    ? `${Math.floor(minutesAgo / 60)}h ago`
                    : formatDate(lead.received_at)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, count, color }: { label: string; count: number; color: 'red' | 'orange' | 'gray' }) {
  const colors = {
    red: 'bg-red-50 border-red-200 text-red-700',
    orange: 'bg-orange-50 border-orange-200 text-orange-700',
    gray: 'bg-gray-50 border-gray-200 text-gray-600',
  };
  return (
    <div className={cn('border rounded-xl p-4 text-center', colors[color])}>
      <p className="text-2xl font-bold">{count}</p>
      <p className="text-xs font-medium mt-0.5">{label}</p>
    </div>
  );
}

function StatusDot({ active, label }: { active: boolean; label: string }) {
  return (
    <div title={label} className={cn('h-2 w-2 rounded-full', active ? 'bg-green-400' : 'bg-gray-200')} />
  );
}
