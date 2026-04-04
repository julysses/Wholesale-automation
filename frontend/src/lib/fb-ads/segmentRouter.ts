/**
 * Segment Router — maps FB lead form situation answers to WholesaleOS pipeline segments.
 */

import type { Situation } from './battlePlanRules';

export type SegmentTag =
  | 'HOT-URGENT'
  | 'HOT-ESTATE'
  | 'HOT-LEGAL'
  | 'HOT-TAX'
  | 'WARM-LANDLORD'
  | 'WARM-RELOCATION'
  | 'COLD-NURTURE';

export interface SegmentResult {
  tag: SegmentTag;
  priority: 'hot' | 'warm' | 'cold';
  twilioSequence: string;
  displayLabel: string;
  color: string;
}

const TAG_META: Record<SegmentTag, Omit<SegmentResult, 'tag'>> = {
  'HOT-URGENT':      { priority: 'hot',  twilioSequence: 'Sequence A (5-min callback)',  displayLabel: 'HOT — Urgent',     color: '#DC2626' },
  'HOT-ESTATE':      { priority: 'hot',  twilioSequence: 'Sequence B (estate script)',   displayLabel: 'HOT — Estate',     color: '#DC2626' },
  'HOT-LEGAL':       { priority: 'hot',  twilioSequence: 'Sequence C (neutral script)',  displayLabel: 'HOT — Legal',      color: '#DC2626' },
  'HOT-TAX':         { priority: 'hot',  twilioSequence: 'Sequence D (relief script)',   displayLabel: 'HOT — Tax',        color: '#DC2626' },
  'WARM-LANDLORD':   { priority: 'warm', twilioSequence: 'Sequence E (landlord script)', displayLabel: 'WARM — Landlord',  color: '#D97706' },
  'WARM-RELOCATION': { priority: 'warm', twilioSequence: 'Sequence F (timeline script)', displayLabel: 'WARM — Relocation',color: '#D97706' },
  'COLD-NURTURE':    { priority: 'cold', twilioSequence: 'Long-drip sequence',           displayLabel: 'COLD — Nurture',   color: '#6B7280' },
};

export function routeSituations(situations: string[], timeline?: string): SegmentResult {
  const sits = situations.map(s => s.toLowerCase());

  // Priority order — highest urgency first
  if (sits.includes('foreclosure')) {
    return { tag: 'HOT-URGENT', ...TAG_META['HOT-URGENT'] };
  }
  if (sits.includes('behind on taxes')) {
    return { tag: 'HOT-TAX', ...TAG_META['HOT-TAX'] };
  }
  if (sits.includes('probate') || sits.includes('inherited')) {
    return { tag: 'HOT-ESTATE', ...TAG_META['HOT-ESTATE'] };
  }
  if (sits.includes('divorce')) {
    return { tag: 'HOT-LEGAL', ...TAG_META['HOT-LEGAL'] };
  }
  if (sits.includes('tired landlord')) {
    return { tag: 'WARM-LANDLORD', ...TAG_META['WARM-LANDLORD'] };
  }
  if (sits.includes('relocating')) {
    return { tag: 'WARM-RELOCATION', ...TAG_META['WARM-RELOCATION'] };
  }
  // Timeline-based fallback
  if (timeline?.toLowerCase() === 'just exploring') {
    return { tag: 'COLD-NURTURE', ...TAG_META['COLD-NURTURE'] };
  }
  // Default — cold nurture for anything unrecognized
  return { tag: 'COLD-NURTURE', ...TAG_META['COLD-NURTURE'] };
}

export function getSegmentResult(tag: SegmentTag): SegmentResult {
  return { tag, ...TAG_META[tag] };
}

export const ROUTING_MAP: Array<{
  situations: string;
  segment: string;
  twilioSequence: string;
}> = [
  { situations: 'Foreclosure',      segment: 'HOT-URGENT',      twilioSequence: 'Sequence A (5-min callback)' },
  { situations: 'Probate',          segment: 'HOT-ESTATE',       twilioSequence: 'Sequence B (estate script)' },
  { situations: 'Divorce',          segment: 'HOT-LEGAL',        twilioSequence: 'Sequence C (neutral script)' },
  { situations: 'Behind on Taxes',  segment: 'HOT-TAX',          twilioSequence: 'Sequence D (relief script)' },
  { situations: 'Tired Landlord',   segment: 'WARM-LANDLORD',    twilioSequence: 'Sequence E (landlord script)' },
  { situations: 'Relocating',       segment: 'WARM-RELOCATION',  twilioSequence: 'Sequence F (timeline script)' },
  { situations: 'Inherited',        segment: 'HOT-ESTATE',       twilioSequence: 'Sequence B (estate script)' },
  { situations: 'Just Exploring',   segment: 'COLD-NURTURE',     twilioSequence: 'Long-drip sequence' },
];
