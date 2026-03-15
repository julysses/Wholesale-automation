/**
 * useNotifications — fetches + subscribes to real-time in-app notifications.
 *
 * Covers:
 *   - New pending user signup alerts (admin only)
 *   - HOT lead / APPOINTMENT_SET alerts (auto-fired by webhook handler)
 *   - Pipeline step completions (skip trace, tier routing, etc.)
 *   - Access approved/denied confirmations (non-admin users)
 */
import { useEffect, useState, useCallback } from 'react';
import { toast } from 'sonner';
import { supabase } from '@/lib/supabase';

export interface AppNotification {
  id: string;
  created_at: string;
  type: string;
  title: string;
  body: string;
  action_url: string | null;
  action_label: string | null;
  lead_id: string | null;
  deal_id: string | null;
  read: boolean;
  read_at: string | null;
  metadata: Record<string, unknown>;
}

interface UseNotificationsResult {
  notifications: AppNotification[];
  unreadCount: number;
  loading: boolean;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

const TOAST_ICONS: Record<string, string> = {
  hot_lead:             '🔥',
  appointment_set:      '📅',
  new_user_pending:     '👤',
  access_approved:      '✅',
  access_denied:        '❌',
  skip_trace_complete:  '📞',
  pipeline_step:        'ℹ️',
  system:               '🔔',
};

// Types that pop as immediate toasts (not just panel items)
const TOAST_TYPES = new Set([
  'hot_lead', 'appointment_set', 'new_user_pending', 'access_approved', 'access_denied',
]);

export function useNotifications(): UseNotificationsResult {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    const { data } = await supabase
      .from('app_notifications')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50);
    setNotifications(data ?? []);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetch();

    // Subscribe to INSERT events for real-time notifications
    const channel = supabase
      .channel('app_notifications')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'app_notifications' },
        (payload) => {
          const n = payload.new as AppNotification;
          setNotifications((prev) => [n, ...prev]);

          // Pop a toast for high-priority types
          if (TOAST_TYPES.has(n.type)) {
            const icon = TOAST_ICONS[n.type] ?? '🔔';
            const toastFn = n.type === 'access_denied' ? toast.error : toast.success;
            toastFn(`${icon} ${n.title}`, {
              description: n.body,
              duration: n.type === 'hot_lead' ? 10000 : 6000,
              action: n.action_url
                ? { label: n.action_label ?? 'View', onClick: () => window.location.href = n.action_url! }
                : undefined,
            });
          }
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [fetch]);

  const markRead = useCallback(async (id: string) => {
    await supabase
      .from('app_notifications')
      .update({ read: true, read_at: new Date().toISOString() })
      .eq('id', id);
    setNotifications((prev) =>
      prev.map((n) => n.id === id ? { ...n, read: true } : n)
    );
  }, []);

  const markAllRead = useCallback(async () => {
    const ids = notifications.filter((n) => !n.read).map((n) => n.id);
    if (!ids.length) return;
    await supabase
      .from('app_notifications')
      .update({ read: true, read_at: new Date().toISOString() })
      .in('id', ids);
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, [notifications]);

  return {
    notifications,
    unreadCount: notifications.filter((n) => !n.read).length,
    loading,
    markRead,
    markAllRead,
  };
}
