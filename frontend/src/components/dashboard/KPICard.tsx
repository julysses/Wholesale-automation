import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: number;
  icon: React.ReactNode;
  color?: 'blue' | 'orange' | 'green' | 'purple';
}

const colorMap = {
  blue: 'bg-blue-50 text-blue-600',
  orange: 'bg-orange-50 text-[#E8720C]',
  green: 'bg-green-50 text-green-600',
  purple: 'bg-purple-50 text-purple-600',
};

export function KPICard({ title, value, subtitle, change, icon, color = 'blue' }: KPICardProps) {
  const isPositive = change !== undefined && change > 0;
  const isNegative = change !== undefined && change < 0;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-gray-500 font-medium">{title}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          {subtitle && (
            <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>
          )}
          {change !== undefined && (
            <div className={cn(
              'flex items-center gap-1 mt-1 text-xs font-medium',
              isPositive ? 'text-green-600' : isNegative ? 'text-red-600' : 'text-gray-400'
            )}>
              {isPositive ? <TrendingUp className="h-3 w-3" /> :
               isNegative ? <TrendingDown className="h-3 w-3" /> :
               <Minus className="h-3 w-3" />}
              <span>
                {isPositive ? '+' : ''}{change} vs last week
              </span>
            </div>
          )}
        </div>
        <div className={cn('p-3 rounded-lg', colorMap[color])}>
          {icon}
        </div>
      </div>
    </div>
  );
}
