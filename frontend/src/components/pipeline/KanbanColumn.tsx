import type { Deal } from '@/types';
import { DealCard } from './DealCard';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/utils';

interface KanbanColumnProps {
  id: string;
  title: string;
  deals: Deal[];
  color: string;
  onDealClick: (deal: Deal) => void;
}

export function KanbanColumn({ id, title, deals, color, onDealClick }: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id });

  const totalFee = deals.reduce((sum, d) => sum + (d.assignment_fee || 0), 0);
  const totalContract = deals.reduce((sum, d) => sum + (d.contract_price || 0), 0);

  return (
    <div className="flex flex-col w-72 shrink-0">
      {/* Column header */}
      <div className={cn('px-3 py-2 rounded-t-xl border-t-4', `border-${color}`, 'bg-white border-x border-gray-200')}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
            <span className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full font-medium">
              {deals.length}
            </span>
          </div>
        </div>
        {deals.length > 0 && (
          <div className="flex gap-3 mt-1">
            {totalContract > 0 && (
              <p className="text-xs text-gray-400">
                Contract: <span className="font-medium text-gray-600">{formatCurrency(totalContract)}</span>
              </p>
            )}
            {totalFee > 0 && (
              <p className="text-xs text-gray-400">
                Fees: <span className="font-medium text-green-600">{formatCurrency(totalFee)}</span>
              </p>
            )}
          </div>
        )}
      </div>

      {/* Deals list */}
      <div
        ref={setNodeRef}
        className={cn(
          'flex-1 min-h-32 p-2 space-y-2 border-x border-b border-gray-200 rounded-b-xl bg-gray-50',
          'overflow-y-auto max-h-[calc(100vh-280px)]',
          isOver && 'bg-blue-50 border-blue-300'
        )}
      >
        <SortableContext items={deals.map((d) => d.id)} strategy={verticalListSortingStrategy}>
          {deals.map((deal) => (
            <DealCard key={deal.id} deal={deal} onClick={() => onDealClick(deal)} />
          ))}
        </SortableContext>
        {deals.length === 0 && (
          <div className={cn(
            'h-20 flex items-center justify-center text-xs text-gray-300 border-2 border-dashed rounded-lg',
            isOver ? 'border-blue-300 text-blue-400' : 'border-gray-200'
          )}>
            {isOver ? 'Drop here' : 'No deals'}
          </div>
        )}
      </div>
    </div>
  );
}
