import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { formatDateTime } from '@/lib/utils';
import { MessageSquare, Phone, Mail, Home, User } from 'lucide-react';
import { cn } from '@/lib/utils';

const channelIcons: Record<string, React.ReactNode> = {
  sms: <MessageSquare className="h-4 w-4" />,
  call: <Phone className="h-4 w-4" />,
  email: <Mail className="h-4 w-4" />,
  voicemail: <Phone className="h-4 w-4" />,
  direct_mail: <Home className="h-4 w-4" />,
  in_person: <User className="h-4 w-4" />,
};

const channelColors: Record<string, string> = {
  sms: 'bg-blue-100 text-blue-600',
  call: 'bg-green-100 text-green-600',
  email: 'bg-purple-100 text-purple-600',
  voicemail: 'bg-yellow-100 text-yellow-600',
  direct_mail: 'bg-orange-100 text-orange-600',
  in_person: 'bg-pink-100 text-pink-600',
};

export function ActivityFeed() {
  const { data: activities, isLoading } = useQuery({
    queryKey: ['activity-feed'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('outreach_activity')
        .select('*, lead:leads(property_address, owner_first_name, owner_last_name)')
        .order('created_at', { ascending: false })
        .limit(15);
      if (error) throw error;
      return data;
    },
    staleTime: 30000,
  });

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h3 className="text-base font-semibold text-gray-900 mb-4">Recent Activity</h3>
      {isLoading ? (
        <div className="space-y-3">
          {[1,2,3,4,5].map((i) => (
            <div key={i} className="flex gap-3 animate-pulse">
              <div className="h-8 w-8 bg-gray-200 rounded-full" />
              <div className="flex-1 space-y-1">
                <div className="h-4 bg-gray-200 rounded w-3/4" />
                <div className="h-3 bg-gray-200 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : activities && activities.length > 0 ? (
        <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
          {activities.map((a: any) => (
            <div key={a.id} className="flex gap-3">
              <div className={cn(
                'h-8 w-8 rounded-full flex items-center justify-center shrink-0',
                channelColors[a.channel] || 'bg-gray-100 text-gray-600'
              )}>
                {channelIcons[a.channel] || <MessageSquare className="h-4 w-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-900 truncate">
                  <span className="font-medium capitalize">{a.channel}</span>
                  {' '}{a.direction === 'outbound' ? 'to' : 'from'}{' '}
                  <span className="font-medium">
                    {a.lead?.owner_first_name} {a.lead?.owner_last_name}
                  </span>
                </p>
                <p className="text-xs text-gray-400 truncate">
                  {a.lead?.property_address} · {formatDateTime(a.created_at)}
                </p>
                {a.message && (
                  <p className="text-xs text-gray-500 truncate mt-0.5">"{a.message}"</p>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-400">
          <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No activity yet</p>
        </div>
      )}
    </div>
  );
}
