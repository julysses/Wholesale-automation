import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Bell, Plus, UserCircle } from 'lucide-react';
import { useUIStore } from '@/stores/useUIStore';
import { supabase } from '@/lib/supabase';
import { cn } from '@/lib/utils';

interface TopBarProps {
  onAddLead?: () => void;
}

export function TopBar({ onAddLead }: TopBarProps) {
  const [search, setSearch] = useState('');
  const { sidebarCollapsed } = useUIStore();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (search.trim()) {
      window.location.href = `/leads?search=${encodeURIComponent(search)}`;
    }
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

      <div className="flex items-center gap-2">
        {/* Quick add buttons */}
        {onAddLead && (
          <button
            onClick={onAddLead}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-[#E8720C] rounded-lg hover:bg-[#c5600a] transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add Lead
          </button>
        )}

        {/* Notifications */}
        <button className="relative p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
          <Bell className="h-5 w-5" />
          <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-[#E8720C] rounded-full" />
        </button>

        {/* User */}
        <button
          onClick={async () => { await supabase.auth.signOut(); }}
          className="flex items-center gap-2 p-2 text-gray-600 rounded-lg hover:bg-gray-100"
          title="Sign out"
        >
          <UserCircle className="h-6 w-6" />
        </button>
      </div>
    </header>
  );
}
