import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { cn, formatDate } from '@/lib/utils';
import { Phone } from 'lucide-react';

// Facebook leads arrive through the signed /webhooks/facebook/lead handler,
// which writes CRM leads tagged inbound_channel='facebook_lead_ad'.
interface FbLeadRow {
  id: string;
  created_at: string;
  owner_first_name: string | null;
  owner_last_name: string | null;
  owner_phone_1: string | null;
  property_address: string | null;
  motivation_tag: string | null;
  priority_tier: string | null;
  status: string | null;
  contact_attempts: number | null;
}

interface FbLead {
  id: string;
  received_at: string;
  name: string | null;
  phone: string | null;
  property_address: string | null;
  situations: string[] | null;
  status: string | null;
  segment_tag: string;
  contacted: boolean;
  appointment_set: boolean;
}

const SEGMENT_BY_TIER: Record<string, string> = { A: 'HOT', B: 'WARM' };

function toFbLead(row: FbLeadRow): FbLead {
  const name = [row.owner_first_name, row.owner_last_name].filter(Boolean).join(' ').trim();
  const status = row.status || 'new';
  return {
    id: row.id,
    received_at: row.created_at,
    name: name || null,
    phone: row.owner_phone_1,
    property_address: row.property_address,
    situations: row.motivation_tag ? [row.motivation_tag] : null,
    status,
    segment_tag: SEGMENT_BY_TIER[row.priority_tier || ''] || 'COLD',
    contacted: (row.contact_attempts || 0) > 0 || !['new', 'qualified_hot', 'qualified_warm', 'qualified_cold'].includes(status),
    appointment_set: status.includes('appointment'),
  };
}

const SEGMENT_STYLES: Record<string, { bg: string; text: string }> = {
  HOT:  { bg: 'bg-red-100', text: 'text-red-700' },
  WARM: { bg: 'bg-orange-100', text: 'text-orange-700' },
  COLD: { bg: 'bg-gray-100', text: 'text-gray-600' },
};

export function LeadIntakeRouter() {
  const { data: leads = [], isLoading } = useQuery<FbLead[]>({
    queryKey: ['fb_leads_recent'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leads')
        .select('id, created_at, owner_first_name, owner_last_name, owner_phone_1, property_address, motivation_tag, priority_tier, status, contact_attempts')
        .eq('inbound_channel', 'facebook_lead_ad')
        .order('created_at', { ascending: false })
        .limit(50);
      if (error) throw error;
      return ((data || []) as FbLeadRow[]).map(toFbLead);
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
        <p className="text-xs text-gray-500">Facebook Lead Ads leads saved to the CRM, by priority</p>
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
                  </div>
                </div>

                {/* Contact preference */}
                <div className="flex items-center gap-2 shrink-0">
                  {lead.phone && <Phone className="h-3.5 w-3.5 text-gray-400" />}
                  <span className="text-xs text-gray-500">{lead.phone || '—'}</span>
                </div>

                {/* CRM status */}
                <span className="text-xs text-gray-500 shrink-0">{(lead.status || 'new').replace(/_/g, ' ')}</span>

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
