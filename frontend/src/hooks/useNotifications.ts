/**
 * useNotifications — fetches + subscribes to real-time in-app notifications.
 *
 * Covers:
 *   - New pending user signup alerts (admin only)
 *   - HOT lead / APPOINTMENT_SET alerts (auto-fired by webhook handler)
 *   - Pipeline step completions (skip trace, tier routing, etc.)
 *   - Access approved/denied confirmations (non-admin users)
 */
import { useEffect, useId, useState, useCallback, useRef } from 'react';
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
  error: string | null;
  refresh: () => Promise<void>;
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

function withLeadLink(notification: AppNotification): AppNotification {
  // Older alerts saved a generic list link even when they identify a lead.
  if (notification.action_url === '/leads' && notification.lead_id &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(notification.lead_id)) {
    return { ...notification, action_url: `/leads?lead=${notification.lead_id.toLowerCase()}` };
  }
  return notification;
}

export function useNotifications(): UseNotificationsResult {
  const id = useId();
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seen = useRef(new Set<string>());
  const initialized = useRef(false);
  const revision = useRef(0);

  const announce = useCallback((n: AppNotification) => {
    if (seen.current.has(n.id)) return;
    seen.current.add(n.id);
    if (n.read) return;
    const failure = n.type === 'system' && n.metadata?.integration_failure === true;
    const sms = n.type === 'pipeline_step' && ['twilio', 'retell'].includes(String(n.metadata?.provider));
    if (!TOAST_TYPES.has(n.type) && !failure && !sms) return;
    const show = n.type === 'access_denied' || failure ? toast.error : toast.success;
    show(`${TOAST_ICONS[n.type] ?? '🔔'} ${n.title}`, {
      id: `notification-${n.id}`,
      description: n.body,
      duration: sms || n.type === 'hot_lead' ? 10000 : 6000,
      action: n.action_url
        ? { label: n.action_label ?? 'View', onClick: () => window.location.href = n.action_url! }
        : undefined,
    });
  }, []);

  const fetch = useCallback(async () => {
    const request = ++revision.current;
    try {
      const { data, error: readError } = await supabase.from('app_notifications')
        .select('*').order('created_at', { ascending: false }).limit(50);
      if (request !== revision.current) return;
      if (readError) throw readError;
      const rows = (data ?? []).map(withLeadLink);
      for (const row of rows) {
        if (initialized.current) announce(row);
        else seen.current.add(row.id);
      }
      initialized.current = true;
      setNotifications(rows);
      setError(null);
    } catch {
      if (request === revision.current) setError('Notifications could not refresh. Showing the last saved list.');
    } finally {
      if (request === revision.current) setLoading(false);
    }
  }, [announce]);

  useEffect(() => {
    const requests = revision;
    fetch();

    // Subscribe to INSERT events for real-time notifications
    const channel = supabase
      .channel(`app_notifications-${id}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'app_notifications' },
        (payload) => {
          const n = withLeadLink(payload.new as AppNotification);
          // A delayed snapshot must not erase a newer realtime receipt.
          ++revision.current;
          setNotifications((prev) => [n, ...prev.filter(row => row.id !== n.id)]
            .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 50));
          announce(n);
          void fetch();
        }
      )
      .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'app_notifications' }, () => { void fetch(); })
      .subscribe((status) => { if (status === 'SUBSCRIBED') void fetch(); });

    const refreshVisible = () => { if (document.visibilityState !== 'hidden') void fetch(); };
    const interval = window.setInterval(refreshVisible, 30000);
    window.addEventListener('focus', refreshVisible);
    window.addEventListener('online', refreshVisible);
    document.addEventListener('visibilitychange', refreshVisible);
    return () => {
      ++requests.current;
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshVisible);
      window.removeEventListener('online', refreshVisible);
      document.removeEventListener('visibilitychange', refreshVisible);
      supabase.removeChannel(channel);
    };
  }, [fetch, announce, id]);

  const markRead = useCallback(async (id: string) => {
    const { error: writeError } = await supabase
      .from('app_notifications')
      .update({ read: true, read_at: new Date().toISOString() })
      .eq('id', id);
    if (writeError) { setError('Could not mark this notification as read. Please retry.'); return; }
    ++revision.current;
    setNotifications((prev) =>
      prev.map((n) => n.id === id ? { ...n, read: true } : n)
    );
  }, []);

  const markAllRead = useCallback(async () => {
    const ids = notifications.filter((n) => !n.read).map((n) => n.id);
    if (!ids.length) return;
    const { error: writeError } = await supabase
      .from('app_notifications')
      .update({ read: true, read_at: new Date().toISOString() })
      .in('id', ids);
    if (writeError) { setError('Could not mark notifications as read. Please retry.'); return; }
    ++revision.current;
    setNotifications((prev) => prev.map((n) => ids.includes(n.id) ? { ...n, read: true } : n));
  }, [notifications]);

  return {
    notifications,
    unreadCount: notifications.filter((n) => !n.read).length,
    loading,
    error,
    refresh: fetch,
    markRead,
    markAllRead,
  };
}
