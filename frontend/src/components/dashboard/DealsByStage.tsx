import { useDeals } from '@/hooks/useDeals';
import { formatCurrency, getStageLabel } from '@/lib/utils';
import { cn } from '@/lib/utils';

const stageConfig = [
  { stage: 'offer_made', color: 'bg-blue-500', label: 'Offer Made' },
  { stage: 'under_contract', color: 'bg-orange-500', label: 'Under Contract' },
  { stage: 'marketing_to_buyers', color: 'bg-purple-500', label: 'Marketing' },
  { stage: 'buyer_found', color: 'bg-yellow-500', label: 'Buyer Found' },
  { stage: 'assigned', color: 'bg-teal-500', label: 'Assigned' },
  { stage: 'closed', color: 'bg-green-500', label: 'Closed' },
];

export function DealsByStage() {
  const { data: deals } = useDeals();

  const stageData = stageConfig.map(({ stage, color, label }) => {
    const stageDeals = (deals ?? []).filter((d) => d.stage === stage);
    const totalFee = stageDeals.reduce((sum, d) => sum + (d.assignment_fee || 0), 0);
    return { stage, color, label, count: stageDeals.length, totalFee };
  });

  const totalDeals = stageData.reduce((sum, s) => sum + s.count, 0);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-gray-900">Deals by Stage</h3>
        <span className="text-sm text-gray-500">{totalDeals} active</span>
      </div>
      <div className="space-y-3">
        {stageData.map(({ stage, color, label, count, totalFee }) => (
          <div key={stage} className="flex items-center gap-3">
            <div className={cn('h-2.5 w-2.5 rounded-full shrink-0', color)} />
            <span className="text-sm text-gray-700 w-36 shrink-0">{label}</span>
            <div className="flex-1 bg-gray-100 rounded-full h-2">
              <div
                className={cn('h-2 rounded-full', color)}
                style={{ width: totalDeals ? `${(count / Math.max(totalDeals, 1)) * 100}%` : '0%' }}
              />
            </div>
            <span className="text-sm font-medium text-gray-900 w-6 text-center">{count}</span>
            {totalFee > 0 && (
              <span className="text-xs text-gray-400 w-20 text-right">{formatCurrency(totalFee)}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
