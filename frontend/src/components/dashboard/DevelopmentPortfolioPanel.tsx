import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Building2, Landmark, WalletCards } from 'lucide-react';
import { Link } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { calculateProject, portfolioEquityNeed, recommendedExit, type DevelopmentWorkspace } from '@/lib/developmentEngine';

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

export function DevelopmentPortfolioPanel() {
  const { data: workspace } = useQuery({
    queryKey: ['development-dashboard-summary'],
    queryFn: async () => {
      const { data, error } = await supabase.from('development_workspaces').select('workspace').maybeSingle();
      if (error) {
        // The module is still usable locally before the migration is deployed.
        if (error.code === '42P01' || error.code === 'PGRST205') return null;
        throw error;
      }
      return data?.workspace as DevelopmentWorkspace | null;
    },
    staleTime: 60_000,
    retry: false,
  });

  if (!workspace?.projects?.length) {
    return <div className="rounded-xl border border-red-100 bg-gradient-to-r from-red-50 to-white p-5">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex gap-3"><div className="rounded-lg bg-[#9D1C20] p-2 text-white"><Building2 className="h-5 w-5" /></div>
          <div><h2 className="font-semibold text-gray-900">Hilltop Development</h2><p className="text-sm text-gray-600">Underwrite a wholesale lead as a spec build or build-to-rent opportunity.</p></div>
        </div>
        <Link to="/development" className="inline-flex items-center gap-2 text-sm font-semibold text-[#9D1C20]">Open command center <ArrowRight className="h-4 w-4" /></Link>
      </div>
    </div>;
  }

  const active = workspace.projects.filter(project => project.included && !['Closed', 'Stabilized', 'Pass'].includes(project.stage));
  const specCount = active.filter(project => project.mode === 'Spec').length;
  const btrCount = active.filter(project => project.mode === 'BTR').length;
  const equityNeed = portfolioEquityNeed(workspace);
  const passing = active.filter(project => {
    const metrics = calculateProject(project, workspace.settings);
    return metrics.salePass || metrics.rentalPass;
  }).length;

  return <div className="rounded-xl border border-red-100 bg-white shadow-sm">
    <div className="flex flex-col justify-between gap-3 border-b border-red-50 px-5 py-4 sm:flex-row sm:items-center">
      <div><h2 className="font-semibold text-gray-900">Hilltop Development Portfolio</h2><p className="text-sm text-gray-500">Owned-project capacity and capital alongside the wholesale pipeline.</p></div>
      <Link to="/development" className="inline-flex items-center gap-2 text-sm font-semibold text-[#9D1C20]">Open command center <ArrowRight className="h-4 w-4" /></Link>
    </div>
    <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
      <Summary icon={<Building2 className="h-5 w-5" />} label="Active projects" value={`${active.length}`} note={`${passing} clear at least one exit`} />
      <Summary icon={<Building2 className="h-5 w-5" />} label="Spec builds" value={`${specCount}`} note={`${workspace.settings.maxSpecs} project cap`} />
      <Summary icon={<Landmark className="h-5 w-5" />} label="Build to rent" value={`${btrCount}`} note="Debt sized by LTV, LTC and DSCR" />
      <Summary icon={<WalletCards className="h-5 w-5" />} label="Future equity need" value={currency.format(equityNeed)} note={`${currency.format(workspace.settings.liquidity - workspace.settings.monthlyOverhead * workspace.settings.reserveMonths - equityNeed)} unallocated headroom`} />
    </div>
    {active.length > 0 && <div className="border-t border-gray-100 px-5 py-3 text-xs text-gray-500">
      Selected policy: {workspace.settings.posture}. Latest active recommendation: {recommendedExit(active[0], workspace.settings)}.
    </div>}
  </div>;
}

function Summary({ icon, label, value, note }: { icon: React.ReactNode; label: string; value: string; note: string }) {
  return <div className="flex gap-3"><div className="mt-0.5 text-[#9D1C20]">{icon}</div><div><div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div><div className="mt-0.5 text-xl font-bold text-gray-900">{value}</div><div className="text-xs text-gray-500">{note}</div></div></div>;
}
