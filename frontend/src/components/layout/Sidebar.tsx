import { useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/useUIStore';
import { useProfile } from '@/hooks/useProfile';
import {
  LayoutDashboard, Users, GitBranch, Calculator, UserCheck,
  Bot, CheckSquare, BarChart3, ChevronLeft, ChevronRight,
  Building2, ShieldCheck, Zap, Flame, BookOpen, TreePine, BrainCircuit, Megaphone, Target, Layers, HardHat, X
} from 'lucide-react';

const mainNav = [
  { path: '/',              label: 'Dashboard',      icon: LayoutDashboard },
  { path: '/leads',         label: 'Leads',          icon: Users },
  { path: '/master-list',   label: 'Master List',    icon: Layers },
  { path: '/acquisitions',  label: 'Acquisitions',   icon: Flame },
  { path: '/lead-gen',      label: 'Lead Engine',    icon: Megaphone },
  { path: '/fb-ads',        label: 'FB Ads',         icon: Target },
  { path: '/pipeline',      label: 'Pipeline',       icon: GitBranch },
  { path: '/analyzer',      label: 'Deal Analyzer',  icon: Calculator },
  { path: '/buyers',        label: 'Buyers',         icon: UserCheck },
  { path: '/buyer-intel',   label: 'Buyer Intel',    icon: BrainCircuit },
  { path: '/ai-agents',     label: 'AI Agents',      icon: Bot },
  { path: '/tasks',         label: 'Tasks',          icon: CheckSquare },
  { path: '/reports',       label: 'Reports',        icon: BarChart3 },
  { path: '/land',          label: 'Vacant Land',    icon: TreePine },
  { path: '/development',   label: 'Development',    icon: HardHat },
  { path: '/manual',        label: 'User Manual',    icon: BookOpen },
];

const adminNav = [
  { path: '/daily-lists', label: 'Daily Lists', icon: Layers },
  { path: '/admin/users',  label: 'Manage Users', icon: ShieldCheck },
  { path: '/setup',        label: 'Setup Wizard', icon: Zap },
];

export function Sidebar({ mobileOpen = false, onMobileClose }: { mobileOpen?: boolean; onMobileClose?: () => void }) {
  const location = useLocation();
  const { sidebarCollapsed, toggleSidebar } = useUIStore();
  const { isAdmin } = useProfile();
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!mobileOpen) return;
    const opener = document.activeElement;
    closeButton.current?.focus();
    return () => { if (opener instanceof HTMLElement) opener.focus(); };
  }, [mobileOpen]);

  const NavLink = ({ path, label, icon: Icon }: { path: string; label: string; icon: React.ElementType }) => {
    const active = location.pathname === path;
    return (
      <Link
        to={path}
        onClick={onMobileClose}
        aria-current={active ? 'page' : undefined}
        title={sidebarCollapsed ? label : undefined}
        className={cn(
          'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
          active
            ? 'bg-[#E8720C] text-white'
            : 'text-white/70 hover:bg-white/10 hover:text-white'
        )}
      >
        <Icon className="h-5 w-5 shrink-0" />
        <span className={sidebarCollapsed ? 'md:hidden' : undefined}>{label}</span>
      </Link>
    );
  };

  return (
    <>
    {mobileOpen && <div className="fixed inset-0 z-20 bg-black/40 md:hidden" onClick={onMobileClose} aria-hidden="true" />}
    <aside id="main-navigation"
      onKeyDown={event => { if (event.key === 'Escape' && mobileOpen) onMobileClose?.(); }}
      className={cn(
        'fixed left-0 top-0 h-full w-60 bg-[#1B3A5C] text-white flex-col transition-all duration-300 z-30 md:flex',
        mobileOpen ? 'flex' : 'hidden',
        sidebarCollapsed && 'md:w-16'
      )}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-white/10">
        <Building2 className="h-8 w-8 text-[#E8720C] shrink-0" />
        <span className={cn('ml-3 text-lg font-bold tracking-tight', sidebarCollapsed && 'md:hidden')}>WholesaleOS</span>
        {mobileOpen && <button ref={closeButton} type="button" aria-label="Close navigation" onClick={onMobileClose}
          className="ml-auto rounded p-2 text-white hover:bg-white/10 md:hidden"><X className="h-5 w-5" /></button>}
      </div>

      {/* Main nav */}
      <nav className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
        {mainNav.map((item) => <NavLink key={item.path} {...item} />)}

        {/* Admin section — only visible to admin users */}
        {isAdmin && (
          <>
            <div className={cn('mt-4 mb-1 px-3', sidebarCollapsed && 'md:hidden')}>
              <span className="text-xs text-white/30 uppercase tracking-widest font-semibold">Admin</span>
            </div>
            {!sidebarCollapsed && <div className="border-t border-white/10 my-1" />}
            {adminNav.map((item) => <NavLink key={item.path} {...item} />)}
          </>
        )}
      </nav>

      {/* Collapse button */}
      <div className="hidden p-2 border-t border-white/10 md:block">
        <button
          onClick={toggleSidebar}
          className="w-full flex items-center justify-center p-2 rounded-lg text-white/60 hover:bg-white/10 hover:text-white transition-colors"
        >
          {sidebarCollapsed ? <ChevronRight className="h-5 w-5" /> : <ChevronLeft className="h-5 w-5" />}
        </button>
      </div>
    </aside>
    </>
  );
}
