/**
 * StackBadge — displays a lead's distress stack name with color coding.
 *
 * Stacks (descending priority):
 *   Ultimate Distress      → deep red
 *   Absentee + Vacant + Tax → red-orange
 *   Utility Shutoff + Vacant → orange
 *   Probate + Vacant        → amber
 *   Code Violation + Vacant → amber
 *   Vacant + Tax Delinquent → yellow
 *   Absentee + Tax Delinquent → yellow
 *   Absentee + Vacant       → yellow-green
 *   Single Signal           → gray (no badge)
 */

interface StackBadgeProps {
  stackName?: string | null;
  stackBonus?: number;
  className?: string;
}

type StackStyle = {
  bg: string;
  text: string;
  border: string;
  dot: string;
};

const STACK_STYLES: Record<string, StackStyle> = {
  'Ultimate Distress': {
    bg: 'bg-red-100',
    text: 'text-red-800',
    border: 'border-red-300',
    dot: 'bg-red-500',
  },
  'Absentee + Vacant + Tax': {
    bg: 'bg-orange-100',
    text: 'text-orange-800',
    border: 'border-orange-300',
    dot: 'bg-orange-500',
  },
  'Utility Shutoff + Vacant': {
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    dot: 'bg-orange-400',
  },
  'Probate + Vacant': {
    bg: 'bg-amber-100',
    text: 'text-amber-800',
    border: 'border-amber-300',
    dot: 'bg-amber-500',
  },
  'Code Violation + Vacant': {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    dot: 'bg-amber-400',
  },
  'Vacant + Tax Delinquent': {
    bg: 'bg-yellow-100',
    text: 'text-yellow-800',
    border: 'border-yellow-300',
    dot: 'bg-yellow-500',
  },
  'Absentee + Tax Delinquent': {
    bg: 'bg-yellow-50',
    text: 'text-yellow-700',
    border: 'border-yellow-200',
    dot: 'bg-yellow-400',
  },
  'Absentee + Vacant': {
    bg: 'bg-lime-50',
    text: 'text-lime-700',
    border: 'border-lime-200',
    dot: 'bg-lime-500',
  },
};

const DEFAULT_STYLE: StackStyle = {
  bg: 'bg-gray-50',
  text: 'text-gray-500',
  border: 'border-gray-200',
  dot: 'bg-gray-400',
};

export function StackBadge({ stackName, stackBonus, className = '' }: StackBadgeProps) {
  if (!stackName || stackName === 'Single Signal') return null;

  const style = STACK_STYLES[stackName] ?? DEFAULT_STYLE;

  return (
    <span
      title={stackBonus ? `Stack bonus: +${stackBonus} pts` : stackName}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${style.bg} ${style.text} ${style.border} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${style.dot}`} />
      {stackName}
      {stackBonus ? (
        <span className="opacity-60 font-normal ml-0.5">+{stackBonus}</span>
      ) : null}
    </span>
  );
}
