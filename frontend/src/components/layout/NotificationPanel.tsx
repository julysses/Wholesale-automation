/**
 * NotificationPanel — slide-in panel showing in-app notifications.
 *
 * Features:
 *   - Real-time updates via Supabase subscription (see useNotifications)
 *   - Unread badge on bell icon
 *   - Mark individual / all as read
 *   - Pipeline step handoffs as rich notification cards
 *   - Deep-links to lead / pipeline pages
 */
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotifications, type AppNotification } from '@/hooks/useNotifications';
import { cn } from '@/lib/utils';
import {
  Bell, X, CheckCheck, Flame, Calendar, UserPlus,
  CheckCircle, XCircle, Phone, MessageSquare, Info, ChevronRight
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

// ── Notification icon by type ─────────────────────────────────────────────────
function NotifIcon({ type }: { type: string }) {
  const cls = 'h-4 w-4';
  switch (type) {
    case 'hot_lead':          return <Flame className={cn(cls, 'text-red-500')} />;
    case 'appointment_set':   return <Calendar className={cn(cls, 'text-blue-600')} />;
    case 'new_user_pending':  return <UserPlus className={cn(cls, 'text-yellow-500')} />;
    case 'access_approved':   return <CheckCircle className={cn(cls, 'text-green-500')} />;
    case 'access_denied':     return <XCircle className={cn(cls, 'text-red-500')} />;
    case 'skip_trace_complete': return <Phone className={cn(cls, 'text-teal-500')} />;
    case 'pipeline_step':     return <MessageSquare className={cn(cls, 'text-purple-500')} />;
    default:                  return <Info className={cn(cls, 'text-gray-400')} />;
  }
}

// ── Border accent color by type ───────────────────────────────────────────────
function notifBorderClass(type: string) {
  switch (type) {
    case 'hot_lead':         return 'border-l-red-400';
    case 'appointment_set':  return 'border-l-blue-400';
    case 'new_user_pending': return 'border-l-yellow-400';
    case 'access_approved':  return 'border-l-green-400';
    case 'access_denied':    return 'border-l-red-400';
    default:                 return 'border-l-gray-200';
  }
}

// ── Single notification card ──────────────────────────────────────────────────
function NotifCard({
  notif, onRead, onNavigate,
}: {
  notif: AppNotification;
  onRead: (id: string) => void;
  onNavigate: (url: string) => void;
}) {
  return (
    <div
      className={cn(
        'relative border-l-4 bg-white rounded-r-xl p-3 shadow-sm cursor-pointer hover:bg-gray-50 transition-colors',
        notifBorderClass(notif.type),
        !notif.read && 'ring-1 ring-inset ring-blue-100'
      )}
      onClick={() => {
        onRead(notif.id);
        if (notif.action_url) onNavigate(notif.action_url);
      }}
    >
      {!notif.read && (
        <span className="absolute top-3 right-3 h-2 w-2 rounded-full bg-[#E8720C]" />
      )}
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 shrink-0"><NotifIcon type={notif.type} /></div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-gray-900 leading-tight">{notif.title}</p>
          <p className="text-xs text-gray-600 mt-0.5 leading-relaxed line-clamp-2">{notif.body}</p>
          <p className="text-xs text-gray-400 mt-1.5">
            {formatDistanceToNow(new Date(notif.created_at), { addSuffix: true })}
          </p>
        </div>
        {notif.action_url && (
          <ChevronRight className="h-4 w-4 text-gray-400 shrink-0 mt-2" />
        )}
      </div>
    </div>
  );
}

// ── Main panel + bell button ──────────────────────────────────────────────────
export function NotificationPanel() {
  const [open, setOpen] = useState(false);
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const panelRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleNavigate = (url: string) => {
    setOpen(false);
    navigate(url);
  };

  return (
    <div ref={panelRef} className="relative">
      {/* Bell button */}
      <button
        onClick={() => setOpen(!open)}
        className="relative p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold bg-[#E8720C] text-white rounded-full px-1 leading-none">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Panel */}
      {open && (
        <div className="absolute right-0 top-12 z-50 w-96 bg-white border border-gray-200 rounded-2xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900">
              Notifications
              {unreadCount > 0 && (
                <span className="ml-2 text-xs bg-[#E8720C] text-white rounded-full px-2 py-0.5">
                  {unreadCount} new
                </span>
              )}
            </h3>
            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
                  title="Mark all as read"
                >
                  <CheckCheck className="h-4 w-4" /> All read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="p-1 hover:bg-gray-100 rounded">
                <X className="h-4 w-4 text-gray-400" />
              </button>
            </div>
          </div>

          {/* Notification list */}
          <div className="overflow-y-auto max-h-[480px]">
            {notifications.length === 0 ? (
              <div className="py-12 text-center text-gray-400">
                <Bell className="h-8 w-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No notifications yet</p>
              </div>
            ) : (
              <div className="p-3 space-y-2">
                {notifications.map((n) => (
                  <NotifCard
                    key={n.id}
                    notif={n}
                    onRead={markRead}
                    onNavigate={handleNavigate}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
