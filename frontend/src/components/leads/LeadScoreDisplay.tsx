import { cn, getScoreBadgeClass } from '@/lib/utils';

interface LeadScoreDisplayProps {
  score?: number | null;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export function LeadScoreDisplay({ score, size = 'md', showLabel = false }: LeadScoreDisplayProps) {
  if (score == null) return <span className="text-gray-400 text-xs">—</span>;

  const label = score >= 13 ? 'HOT' : score >= 8 ? 'WARM' : 'COLD';
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-xs' :
                    size === 'lg' ? 'px-3 py-1.5 text-base font-bold' :
                    'px-2 py-1 text-sm font-semibold';

  return (
    <span className={cn('rounded font-medium inline-flex items-center gap-1', sizeClass, getScoreBadgeClass(score))}>
      {score}
      {showLabel && <span className="opacity-70">· {label}</span>}
    </span>
  );
}
