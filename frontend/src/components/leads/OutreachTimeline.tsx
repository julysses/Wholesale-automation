import { useOutreachActivity } from '@/hooks/useLeads';
import { formatDateTime } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { MessageSquare, Phone, Mail, Home, User } from 'lucide-react';

interface OutreachTimelineProps {
  leadId: string;
}

const channelConfig: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  sms:         { icon: <MessageSquare className="h-3.5 w-3.5" />, color: 'bg-blue-100 text-blue-600',    label: 'SMS' },
  call:        { icon: <Phone className="h-3.5 w-3.5" />,         color: 'bg-green-100 text-green-600',  label: 'Call' },
  email:       { icon: <Mail className="h-3.5 w-3.5" />,          color: 'bg-purple-100 text-purple-600',label: 'Email' },
  voicemail:   { icon: <Phone className="h-3.5 w-3.5" />,         color: 'bg-yellow-100 text-yellow-600',label: 'Voicemail' },
  direct_mail: { icon: <Home className="h-3.5 w-3.5" />,          color: 'bg-orange-100 text-orange-600',label: 'Mail' },
  in_person:   { icon: <User className="h-3.5 w-3.5" />,          color: 'bg-pink-100 text-pink-600',    label: 'In Person' },
};

export function OutreachTimeline({ leadId }: OutreachTimelineProps) {
  const { data: activities, isLoading } = useOutreachActivity(leadId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-3 animate-pulse">
            <div className="h-7 w-7 rounded-full bg-gray-200 shrink-0" />
            <div className="flex-1 space-y-1 pt-1">
              <div className="h-3 bg-gray-200 rounded w-1/2" />
              <div className="h-3 bg-gray-200 rounded w-3/4" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!activities || activities.length === 0) {
    return (
      <div className="text-center py-6 text-gray-400">
        <MessageSquare className="h-7 w-7 mx-auto mb-2 opacity-30" />
        <p className="text-sm">No contact activity yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 max-h-64 overflow-y-auto pr-1">
      {(activities as any[]).map((activity) => {
        const config = channelConfig[activity.channel] ?? channelConfig['sms'];
        const isInbound = activity.direction === 'inbound';
        return (
          <div key={activity.id} className={cn('flex gap-3', isInbound ? 'flex-row-reverse' : 'flex-row')}>
            <div className={cn('h-7 w-7 rounded-full flex items-center justify-center shrink-0', config.color)}>
              {config.icon}
            </div>
            <div className={cn(
              'flex-1 max-w-xs rounded-xl px-3 py-2 text-sm',
              isInbound ? 'bg-blue-50 rounded-tr-none' : 'bg-gray-100 rounded-tl-none'
            )}>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-xs font-semibold text-gray-600">{config.label}</span>
                {activity.status && <span className="text-xs text-gray-400 capitalize">{activity.status}</span>}
              </div>
              {activity.message && <p className="text-gray-700 text-xs">{activity.message}</p>}
              {activity.response && <p className="text-blue-700 text-xs mt-1 italic">Reply: {activity.response}</p>}
              <p className="text-xs text-gray-400 mt-1">{formatDateTime(activity.created_at)}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
