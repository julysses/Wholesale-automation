import { useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { StepBanner } from '@/components/StepBanner';
import { AutoScoreStatusBar } from '@/components/AutoScoreStatusBar';
import { useUIStore } from '@/stores/useUIStore';
import { useResumeAutoScore } from '@/hooks/useResumeAutoScore';
import { cn } from '@/lib/utils';
import { Toaster } from 'sonner';

export function Layout() {
  const { sidebarCollapsed } = useUIStore();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const navigate = useNavigate();
  useResumeAutoScore();

  return (
    <div className="min-h-screen bg-[#F2F4F6]">
      <Sidebar mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />
      {/* ?add=1 tells the Leads page to open its Add Lead modal on arrival */}
      <TopBar onAddLead={() => navigate('/leads?add=1')}
        mobileNavOpen={mobileNavOpen} onMobileNavToggle={() => setMobileNavOpen(open => !open)} />
      <main
        className={cn(
          'pt-16 min-h-screen min-w-0 transition-all duration-300',
          sidebarCollapsed ? 'md:ml-16' : 'md:ml-60'
        )}
      >
        <StepBanner />
        <div className="min-w-0 p-4 md:p-6">
          <Outlet />
        </div>
      </main>
      <Toaster position="top-right" richColors />
      <AutoScoreStatusBar />
    </div>
  );
}
