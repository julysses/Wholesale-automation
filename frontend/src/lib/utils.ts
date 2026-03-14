import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value?: number | null, decimals = 0): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatNumber(value?: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US').format(value);
}

export function formatDate(date?: string | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatDateTime(date?: string | null): string {
  if (!date) return '—';
  return new Date(date).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function daysUntil(date?: string | null): number | null {
  if (!date) return null;
  const target = new Date(date);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  target.setHours(0, 0, 0, 0);
  return Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

export function daysAgo(date?: string | null): number | null {
  const days = daysUntil(date);
  return days != null ? -days : null;
}

export function getScoreColor(score?: number | null): string {
  if (score == null) return 'text-gray-400';
  if (score >= 13) return 'text-green-600';
  if (score >= 8) return 'text-yellow-600';
  return 'text-red-600';
}

export function getScoreBadgeClass(score?: number | null): string {
  if (score == null) return 'bg-gray-100 text-gray-600';
  if (score >= 13) return 'bg-green-100 text-green-700';
  if (score >= 8) return 'bg-yellow-100 text-yellow-700';
  return 'bg-red-100 text-red-700';
}

export function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    new: 'New',
    contacted: 'Contacted',
    responding: 'Responding',
    qualified_hot: 'Hot',
    qualified_warm: 'Warm',
    qualified_cold: 'Cold',
    offer_made: 'Offer Made',
    under_contract: 'Under Contract',
    dead: 'Dead',
    dnc: 'DNC',
  };
  return labels[status] || status;
}

export function getStatusClass(status: string): string {
  const classes: Record<string, string> = {
    new: 'bg-blue-100 text-blue-700',
    contacted: 'bg-indigo-100 text-indigo-700',
    responding: 'bg-purple-100 text-purple-700',
    qualified_hot: 'bg-red-100 text-red-700',
    qualified_warm: 'bg-orange-100 text-orange-700',
    qualified_cold: 'bg-cyan-100 text-cyan-700',
    offer_made: 'bg-yellow-100 text-yellow-700',
    under_contract: 'bg-green-100 text-green-700',
    dead: 'bg-gray-100 text-gray-600',
    dnc: 'bg-red-900 text-red-100',
  };
  return classes[status] || 'bg-gray-100 text-gray-600';
}

export function getStageLabel(stage: string): string {
  const labels: Record<string, string> = {
    offer_made: 'Offer Made',
    under_contract: 'Under Contract',
    marketing_to_buyers: 'Marketing to Buyers',
    buyer_found: 'Buyer Found',
    assigned: 'Assigned',
    closed: 'Closed',
    cancelled: 'Cancelled',
  };
  return labels[stage] || stage;
}

export function getTierClass(tier: string): string {
  const classes: Record<string, string> = {
    A: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
    B: 'bg-blue-100 text-blue-800 border border-blue-300',
    C: 'bg-gray-100 text-gray-700 border border-gray-300',
  };
  return classes[tier] || 'bg-gray-100 text-gray-700';
}

export function getPriorityClass(priority: string): string {
  const classes: Record<string, string> = {
    high: 'bg-red-100 text-red-700',
    medium: 'bg-yellow-100 text-yellow-700',
    low: 'bg-gray-100 text-gray-600',
  };
  return classes[priority] || 'bg-gray-100 text-gray-600';
}

export function calculateMAO(arv: number, repairs: number, assignmentFee: number): number {
  return arv * 0.7 - repairs - assignmentFee;
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + '...';
}

export function phoneFormat(phone?: string | null): string {
  if (!phone) return '—';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
}
