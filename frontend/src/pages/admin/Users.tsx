/**
 * Admin Users page — approve, deny, suspend, and promote users.
 *
 * Visible only to admin users (enforced via RLS + client-side role check).
 */
import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/lib/supabase';
import { useProfile, type UserProfile } from '@/hooks/useProfile';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  CheckCircle, XCircle, Pause, ShieldCheck, Clock,
  RefreshCw, UserCheck, AlertTriangle, Search, Mail
} from 'lucide-react';
import { toast } from 'sonner';

type UserWithProfile = UserProfile & { denied_reason?: string };

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  pending:   { label: 'Pending',   color: 'bg-yellow-100 text-yellow-800 border-yellow-200', icon: <Clock className="h-3.5 w-3.5" /> },
  approved:  { label: 'Approved',  color: 'bg-green-100 text-green-800 border-green-200',   icon: <CheckCircle className="h-3.5 w-3.5" /> },
  denied:    { label: 'Denied',    color: 'bg-red-100 text-red-800 border-red-200',         icon: <XCircle className="h-3.5 w-3.5" /> },
  suspended: { label: 'Suspended', color: 'bg-gray-100 text-gray-600 border-gray-200',      icon: <Pause className="h-3.5 w-3.5" /> },
};

export function AdminUsers() {
  const { isAdmin, loading: profileLoading } = useProfile();
  const navigate = useNavigate();
  const [users, setUsers] = useState<UserWithProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [denyDialogUser, setDenyDialogUser] = useState<UserWithProfile | null>(null);
  const [denyReason, setDenyReason] = useState('');

  useEffect(() => {
    if (!profileLoading && !isAdmin) {
      navigate('/');
    }
  }, [isAdmin, profileLoading, navigate]);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from('profiles')
      .select('*')
      .order('created_at', { ascending: false });
    if (!error) setUsers(data ?? []);
    setLoading(false);
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const setStatus = async (userId: string, status: string, reason?: string) => {
    setActionLoading(userId);
    const { error } = await supabase.rpc('admin_set_user_status', {
      target_user_id: userId,
      new_status: status,
      reason: reason ?? null,
    });
    if (error) {
      toast.error(`Failed: ${error.message}`);
    } else {
      const labels: Record<string, string> = {
        approved: 'User approved — they can now sign in',
        denied: 'User denied',
        suspended: 'User suspended',
      };
      toast.success(labels[status] ?? 'Status updated');
      await fetchUsers();
    }
    setActionLoading(null);
    setDenyDialogUser(null);
    setDenyReason('');
  };

  const setRole = async (userId: string, role: 'admin' | 'user') => {
    setActionLoading(userId + role);
    const { error } = await supabase.rpc('admin_set_user_role', {
      target_user_id: userId,
      new_role: role,
    });
    if (error) toast.error(`Failed: ${error.message}`);
    else {
      toast.success(`Role updated to ${role}`);
      await fetchUsers();
    }
    setActionLoading(null);
  };

  const filtered = users.filter((u) => {
    const matchSearch = !search ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.full_name ?? '').toLowerCase().includes(search.toLowerCase());
    const matchStatus = !statusFilter || u.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const pendingCount = users.filter(u => u.status === 'pending').length;

  if (profileLoading) {
    return <div className="p-8 text-center text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
          <p className="text-sm text-gray-500 mt-0.5">{users.length} total users</p>
        </div>
        <button
          onClick={fetchUsers}
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {/* Pending alert */}
      {pendingCount > 0 && (
        <div className="flex items-center gap-3 bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <AlertTriangle className="h-5 w-5 text-yellow-600 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-yellow-900">
              {pendingCount} user{pendingCount > 1 ? 's' : ''} awaiting approval
            </p>
            <p className="text-xs text-yellow-700">Review and approve or deny below.</p>
          </div>
          <button
            onClick={() => setStatusFilter('pending')}
            className="text-xs font-medium text-yellow-700 border border-yellow-300 rounded px-3 py-1.5 hover:bg-yellow-100"
          >
            Show pending
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-[#1B3A5C]"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-[#1B3A5C]"
        >
          <option value="">All Status</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="denied">Denied</option>
          <option value="suspended">Suspended</option>
        </select>
      </div>

      {/* Users table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading users...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No users found</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                {['User', 'Role', 'Status', 'Joined', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((user) => {
                const statusCfg = STATUS_CONFIG[user.status];
                const isLoading = actionLoading === user.id;
                return (
                  <tr key={user.id} className="hover:bg-gray-50">
                    {/* User */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-[#1B3A5C] text-white flex items-center justify-center text-xs font-bold shrink-0">
                          {(user.full_name ?? user.email).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">{user.full_name ?? '—'}</p>
                          <p className="text-xs text-gray-500 flex items-center gap-1">
                            <Mail className="h-3 w-3" /> {user.email}
                          </p>
                        </div>
                      </div>
                    </td>

                    {/* Role */}
                    <td className="px-4 py-3">
                      <select
                        value={user.role}
                        disabled={isLoading || actionLoading !== null}
                        onChange={(e) => setRole(user.id, e.target.value as 'admin' | 'user')}
                        className="text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:border-[#1B3A5C]"
                      >
                        <option value="user">User</option>
                        <option value="admin">Admin</option>
                      </select>
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3">
                      <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border', statusCfg.color)}>
                        {statusCfg.icon} {statusCfg.label}
                      </span>
                    </td>

                    {/* Joined */}
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                      {new Date(user.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {user.status === 'pending' && (
                          <>
                            <button
                              onClick={() => setStatus(user.id, 'approved')}
                              disabled={isLoading}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-lg hover:bg-green-100 disabled:opacity-50"
                            >
                              <UserCheck className="h-3.5 w-3.5" /> Approve
                            </button>
                            <button
                              onClick={() => setDenyDialogUser(user)}
                              disabled={isLoading}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 disabled:opacity-50"
                            >
                              <XCircle className="h-3.5 w-3.5" /> Deny
                            </button>
                          </>
                        )}
                        {user.status === 'approved' && (
                          <button
                            onClick={() => setStatus(user.id, 'suspended')}
                            disabled={isLoading}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50"
                          >
                            <Pause className="h-3.5 w-3.5" /> Suspend
                          </button>
                        )}
                        {(user.status === 'denied' || user.status === 'suspended') && (
                          <button
                            onClick={() => setStatus(user.id, 'approved')}
                            disabled={isLoading}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-lg hover:bg-green-100 disabled:opacity-50"
                          >
                            <ShieldCheck className="h-3.5 w-3.5" /> Re-approve
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Deny dialog */}
      {denyDialogUser && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-1">Deny Access</h3>
            <p className="text-sm text-gray-500 mb-4">
              Deny access for <strong>{denyDialogUser.full_name ?? denyDialogUser.email}</strong>?
              Optionally provide a reason (sent to the user).
            </p>
            <textarea
              value={denyReason}
              onChange={(e) => setDenyReason(e.target.value)}
              placeholder="Reason (optional)..."
              rows={3}
              className="w-full text-sm border border-gray-300 rounded-xl p-3 focus:outline-none focus:border-[#1B3A5C] resize-none mb-4"
            />
            <div className="flex gap-3">
              <button
                onClick={() => { setDenyDialogUser(null); setDenyReason(''); }}
                className="flex-1 py-2.5 text-sm font-medium border border-gray-300 rounded-xl hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => setStatus(denyDialogUser.id, 'denied', denyReason || undefined)}
                className="flex-1 py-2.5 text-sm font-medium bg-red-600 text-white rounded-xl hover:bg-red-700"
              >
                Deny Access
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
