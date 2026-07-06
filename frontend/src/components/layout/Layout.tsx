import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { StepBanner } from '@/components/StepBanner';
import { AutoScoreStatusBar } from '@/components/AutoScoreStatusBar';
import { useUIStore } from '@/stores/useUIStore';
import { cn } from '@/lib/utils';
import { Toaster } from 'sonner';

export function Layout() {
  const { sidebarCollapsed } = useUIStore();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F2F4F6]">
      <Sidebar />
      {/* ?add=1 tells the Leads page to open its Add Lead modal on arrival */}
      <TopBar onAddLead={() => navigate('/leads?add=1')} />
      <main
        className={cn(
          'pt-16 min-h-screen transition-all duration-300',
          sidebarCollapsed ? 'ml-16' : 'ml-60'
        )}
      >
        <StepBanner />
        <div className="p-6">
          <Outlet />
        </div>
      </main>
      <Toaster position="top-right" richColors />
      <AutoScoreStatusBar />
    </div>
  );
}
