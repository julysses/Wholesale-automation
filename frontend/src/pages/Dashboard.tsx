import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { queryAll } from '@/lib/queryAll';
import { localDateKey } from '@/lib/utils';
import type { Deal } from '@/types';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { KPICard } from '@/components/dashboard/KPICard';
import { PipelineChart } from '@/components/dashboard/PipelineChart';
import { ActivityFeed } from '@/components/dashboard/ActivityFeed';
import { DealsByStage } from '@/components/dashboard/DealsByStage';
import { FunnelPanel } from '@/components/dashboard/FunnelPanel';
import { PrecisionTargetingPanel } from '@/components/dashboard/PrecisionTargetingPanel';
import { StrategyComparisonPanel } from '@/components/dashboard/StrategyComparisonPanel';
import { DevelopmentPortfolioPanel } from '@/components/dashboard/DevelopmentPortfolioPanel';
import { WorkflowGuide } from '@/components/WorkflowGuide';
import { useHotLeads } from '@/hooks/useLeads';
import { useUpcomingClosings } from '@/hooks/useDeals';
import { useTodayTasks } from '@/hooks/useTasks';
import { formatCurrency, daysUntil, getScoreBadgeClass, getPriorityClass } from '@/lib/utils';
import { Users, FileText, DollarSign, TrendingUp } from 'lucide-react';
import { Link as RouterLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

export function Dashboard() {
  // Scroll to the panel named in the URL hash (e.g. /#strategy from the
  // workflow guide's "Choose on Dashboard" CTA)
  const location = useLocation();
  useEffect(() => {
    if (!location.hash) return;
    const el = document.getElementById(location.hash.slice(1));
    if (el) {
      // slight delay so panels below the fold have rendered
      setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  }, [location.hash]);

  // KPI data
  const { data: kpiData, error: kpiError, refetch: retryKpis } = useQuery({
    queryKey: ['kpi'],
    queryFn: async () => {
      const [leadsRes, dealsRes] = await Promise.all([
        supabase.from('leads').select('id', { count: 'exact', head: true }).not('status', 'in', '(dead,dnc,under_contract)'),
        queryAll<Pick<Deal, 'id' | 'stage' | 'assignment_fee' | 'closing_date' | 'actual_close_date' | 'contract_price'>>((from, to) => supabase.from('deals').select('id, stage, assignment_fee, closing_date, actual_close_date, contract_price').order('id').range(from, to)),
      ]);

      if (leadsRes.error) throw leadsRes.error;
      const deals = dealsRes;
      const activeLeads = leadsRes.count ?? 0;

      const underContract = deals.filter(d =>
        !['closed', 'cancelled'].includes(d.stage)
      );
      const underContractValue = underContract.reduce((sum, deal) => sum + (deal.contract_price || 0), 0);

      const now = new Date();
      const monthStart = localDateKey(new Date(now.getFullYear(), now.getMonth(), 1));
      const closedThisMonth = deals.filter(deal =>
        deal.stage === 'closed' && Boolean(deal.actual_close_date && deal.actual_close_date >= monthStart && deal.actual_close_date <= localDateKey(now))
      );
      const closedFees = closedThisMonth.reduce((sum, deal) => sum + (deal.assignment_fee || 0), 0);

      const pipelineValue = underContract.reduce((sum, deal) => sum + (deal.assignment_fee || 0), 0);

      return {
        activeLeads,
        underContract: underContract.length,
        underContractValue,
        closedThisMonth: closedThisMonth.length,
        closedFees,
        pipelineValue,
      };
    },
    staleTime: 60000,
  });

  const { data: hotLeads } = useHotLeads();
  const { data: upcomingClosings } = useUpcomingClosings();
  const { data: todayTasks } = useTodayTasks();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-0.5">Your wholesale pipeline at a glance</p>
      </div>

      {/* Getting Started Guide */}
      <WorkflowGuide />

      {kpiError && <div role="alert" className="rounded-lg bg-red-50 p-3 text-red-700">Dashboard totals could not be loaded. <button className="underline" onClick={() => retryKpis()}>Retry</button></div>}
      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KPICard
          title="Active Leads"
          value={kpiData?.activeLeads ?? '—'}
          icon={<Users className="h-5 w-5" />}
          color="blue"
        />
        <KPICard
          title="Under Contract"
          value={kpiData?.underContract ?? '—'}
          subtitle={kpiData?.underContractValue ? formatCurrency(kpiData.underContractValue) : undefined}
          icon={<FileText className="h-5 w-5" />}
          color="orange"
        />
        <KPICard
          title="Closed This Month"
          value={kpiData?.closedThisMonth ?? '—'}
          subtitle={kpiData?.closedFees ? formatCurrency(kpiData.closedFees) : undefined}
          icon={<DollarSign className="h-5 w-5" />}
          color="green"
        />
        <KPICard
          title="Pipeline Value"
          value={kpiData?.pipelineValue ? formatCurrency(kpiData.pipelineValue) : '—'}
          icon={<TrendingUp className="h-5 w-5" />}
          color="purple"
        />
      </div>

      {/* Wholesale-to-development portfolio bridge */}
      <DevelopmentPortfolioPanel />

      {/* Main content */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Left: Charts */}
        <div className="xl:col-span-2 space-y-6">
          <PipelineChart />
          <ActivityFeed />
        </div>

        {/* Right: Sidebar panels */}
        <div className="space-y-6">
          {/* Today's Tasks */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-gray-900">Today's Tasks</h3>
              <RouterLink to="/tasks" className="text-xs text-[#2E6DA4] hover:underline">View all</RouterLink>
            </div>
            {todayTasks && todayTasks.length > 0 ? (
              <div className="space-y-2">
                {todayTasks.slice(0, 5).map((task) => (
                  <div key={task.id} className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50">
                    <span className={cn(
                      'inline-flex px-1.5 py-0.5 rounded text-xs font-medium mt-0.5',
                      getPriorityClass(task.priority)
                    )}>
                      {task.priority[0].toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm text-gray-800 font-medium truncate">{task.title}</p>
                      {task.lead && (
                        <p className="text-xs text-gray-400 truncate">{task.lead.property_address}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-4">No tasks due today</p>
            )}
          </div>

          {/* Hot Leads */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-gray-900">Hot Leads</h3>
              <RouterLink to="/leads?status=qualified_hot" className="text-xs text-[#2E6DA4] hover:underline">View all</RouterLink>
            </div>
            {hotLeads && hotLeads.length > 0 ? (
              <div className="space-y-2">
                {hotLeads.map((lead) => (
                  <div key={lead.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-bold',
                      getScoreBadgeClass(lead.total_score)
                    )}>
                      {lead.total_score}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">{lead.property_address}</p>
                      <p className="text-xs text-gray-400 truncate">
                        {lead.owner_first_name} {lead.owner_last_name} · {lead.city}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-4">No hot leads yet</p>
            )}
          </div>

          {/* Upcoming Closings */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-gray-900">Upcoming Closings</h3>
              <RouterLink to="/pipeline" className="text-xs text-[#2E6DA4] hover:underline">View all</RouterLink>
            </div>
            {upcomingClosings && upcomingClosings.length > 0 ? (
              <div className="space-y-2">
                {upcomingClosings.map((deal) => {
                  const days = daysUntil(deal.closing_date);
                  return (
                    <div key={deal.id} className="p-2 rounded-lg hover:bg-gray-50">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {deal.lead?.property_address || deal.deal_name}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={cn(
                          'text-xs font-medium',
                          days !== null && days <= 7 ? 'text-red-600' : 'text-gray-500'
                        )}>
                          {days !== null ? (days === 0 ? 'Today' : `Closes in ${days}d`) : '—'}
                        </span>
                        {deal.assignment_fee && (
                          <span className="text-xs text-gray-400">
                            · Fee: {formatCurrency(deal.assignment_fee)}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-4">No closings in next 14 days</p>
            )}
          </div>

          {/* Acquisition Funnel */}
          <div id="funnel" className="scroll-mt-4">
            <FunnelPanel />
          </div>

          {/* Precision Targeting */}
          <div id="precision" className="scroll-mt-4">
            <PrecisionTargetingPanel />
          </div>

          {/* Strategy Comparison */}
          <div id="strategy" className="scroll-mt-4">
            <StrategyComparisonPanel />
          </div>

          {/* Deals by Stage */}
          <DealsByStage />
        </div>
      </div>
    </div>
  );
}
