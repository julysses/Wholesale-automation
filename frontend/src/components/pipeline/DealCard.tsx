import type { Deal } from '@/types';
import { formatCurrency, daysUntil, getStageLabel } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { Calendar, DollarSign, User } from 'lucide-react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface DealCardProps {
  deal: Deal;
  onClick: () => void;
}

export function DealCard({ deal, onClick }: DealCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: deal.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const days = daysUntil(deal.closing_date);
  const isUrgent = days !== null && days <= 7;
  const isPast = days !== null && days < 0;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        'bg-white rounded-lg border shadow-sm p-3 cursor-grab active:cursor-grabbing',
        'hover:shadow-md transition-shadow',
        isDragging && 'shadow-xl ring-2 ring-[#1B3A5C]'
      )}
      onClick={onClick}
    >
      {/* Address */}
      <p className="font-semibold text-gray-900 text-sm leading-tight truncate" title={deal.lead?.property_address || deal.deal_name}>
        {deal.lead?.property_address || deal.deal_name || 'Unnamed Deal'}
      </p>
      <p className="text-xs text-gray-400 mt-0.5 truncate">
        {deal.lead?.city}{deal.lead?.zip_code ? `, ${deal.lead.zip_code}` : ''}
      </p>

      {/* Financials */}
      <div className="flex items-center gap-3 mt-2">
        {deal.contract_price && (
          <div className="flex items-center gap-1 text-xs text-gray-600">
            <DollarSign className="h-3 w-3" />
            <span>{formatCurrency(deal.contract_price)}</span>
          </div>
        )}
        {deal.assignment_fee && (
          <div className="text-xs font-medium text-green-600 bg-green-50 px-1.5 py-0.5 rounded">
            +{formatCurrency(deal.assignment_fee)}
          </div>
        )}
      </div>

      {/* Closing date */}
      {deal.closing_date && (
        <div className={cn(
          'flex items-center gap-1 mt-2 text-xs font-medium',
          isPast ? 'text-red-700' : isUrgent ? 'text-red-600' : 'text-gray-500'
        )}>
          <Calendar className="h-3 w-3" />
          {isPast
            ? `Closed ${Math.abs(days!)}d ago`
            : days === 0
            ? 'Closes today!'
            : `Closes in ${days}d`}
        </div>
      )}

      {/* Buyer */}
      {deal.buyer && (
        <div className="flex items-center gap-1 mt-1 text-xs text-blue-600">
          <User className="h-3 w-3" />
          <span>{deal.buyer.first_name} {deal.buyer.last_name}</span>
        </div>
      )}
    </div>
  );
}
