import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Plus, UserCircle, ChevronDown, Settings, LogOut } from 'lucide-react';
import { useUIStore } from '@/stores/useUIStore';
import { useProfile } from '@/hooks/useProfile';
import { supabase } from '@/lib/supabase';
import { cn } from '@/lib/utils';
import { NotificationPanel } from './NotificationPanel';

interface TopBarProps {
  onAddLead?: () => void;
}

export function TopBar({ onAddLead }: TopBarProps) {
  const [search, setSearch] = useState('');
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const { sidebarCollapsed } = useUIStore();
  const { profile, isAdmin } = useProfile();
  const navigate = useNavigate();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (search.trim()) {
      window.location.href = `/leads?search=${encodeURIComponent(search)}`;
    }
  };

  const handleSignOut = async () => {
    setUserMenuOpen(false);
    await supabase.auth.signOut();
  };

  return (
    <header
      className={cn(
        'fixed top-0 right-0 h-16 bg-white border-b border-gray-200 flex items-center px-4 gap-4 z-20 transition-all duration-300',
        sidebarCollapsed ? 'left-16' : 'left-60'
      )}
    >
      {/* Search */}
      <form onSubmit={handleSearch} className="flex-1 max-w-lg">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search leads by address, name, or phone..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:border-[#1B3A5C] focus:ring-1 focus:ring-[#1B3A5C]"
          />
        </div>
      </form>

      <div className="flex items-center gap-1.5">
        {/* Quick add */}
        {onAddLead && (
          <button
            onClick={onAddLead}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-[#E8720C] rounded-lg hover:bg-[#c5600a] transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add Lead
          </button>
        )}

        {/* Notification panel */}
        <NotificationPanel />

        {/* User dropdown */}
        <div className="relative">
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2 pl-2 pr-1 py-1.5 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <div className="h-7 w-7 rounded-full bg-[#1B3A5C] text-white flex items-center justify-center text-xs font-bold">
              {(profile?.full_name ?? profile?.email ?? 'U').charAt(0).toUpperCase()}
            </div>
            {profile && (
              <div className="hidden sm:block text-left">
                <p className="text-xs font-medium text-gray-900 leading-tight">{profile.full_name ?? profile.email}</p>
                <p className="text-xs text-gray-400 leading-tight capitalize">{profile.role}</p>
              </div>
            )}
            <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 top-11 z-30 w-52 bg-white border border-gray-200 rounded-xl shadow-lg py-1.5">
              {/* Profile header */}
              <div className="px-3 py-2 border-b border-gray-100 mb-1">
                <p className="text-xs font-semibold text-gray-900">{profile?.full_name ?? 'User'}</p>
                <p className="text-xs text-gray-400">{profile?.email}</p>
                {isAdmin && (
                  <span className="inline-block mt-1 text-xs bg-[#1B3A5C] text-white px-2 py-0.5 rounded-full">Admin</span>
                )}
              </div>

              {isAdmin && (
                <>
                  <button
                    onClick={() => { setUserMenuOpen(false); navigate('/admin/users'); }}
                    className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <Settings className="h-4 w-4" /> Manage Users
                  </button>
                  <button
                    onClick={() => { setUserMenuOpen(false); navigate('/setup'); }}
                    className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <Settings className="h-4 w-4" /> Setup Wizard
                  </button>
                  <div className="border-t border-gray-100 my-1" />
                </>
              )}

              <button
                onClick={handleSignOut}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                <LogOut className="h-4 w-4" /> Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
