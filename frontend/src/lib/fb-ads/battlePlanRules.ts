/**
 * Battle Plan Rules — all enforcement constants and validation logic.
 * Single source of truth for the approved Facebook Ads strategy.
 */

// ── Campaign Settings Rules ────────────────────────────────────────────────────
export const CAMPAIGN_RULES = {
  OBJECTIVE: 'LEAD_GENERATION' as const,
  SPECIAL_AD_CATEGORY: true,
  MIN_DAILY_BUDGET: 20,
  MAX_DAILY_BUDGET: 100,
  DEFAULT_DAILY_BUDGET: 25,
  AB_TEST_DEFAULT: true,
} as const;

// ── Audience Segments ─────────────────────────────────────────────────────────
export const SEGMENTS = [
  'pre-foreclosure',
  'probate',
  'divorce',
  'tax-delinquent',
  'landlord-burnout',
  'vacant-code-violation',
  'senior-downsizing',
  'high-equity',
] as const;
export type Segment = typeof SEGMENTS[number];

export const SEGMENT_LABELS: Record<Segment, string> = {
  'pre-foreclosure': 'Pre-Foreclosure',
  'probate': 'Probate / Estate',
  'divorce': 'Divorce',
  'tax-delinquent': 'Tax Delinquent',
  'landlord-burnout': 'Landlord Burnout',
  'vacant-code-violation': 'Vacant / Code Violation',
  'senior-downsizing': 'Senior / Downsizing',
  'high-equity': 'High Equity / Long Tenure',
};

export const AUDIENCE_TYPES = [
  'Pre-Foreclosure',
  'Probate',
  'Tax Delinquent',
  'Divorce',
  'Absentee Owner',
  'Code Violation',
  'Vacant',
  'High Equity',
  'Landlord Burnout',
  'Closed Deals',
] as const;

// Maps CSV audience type labels to the corresponding Segment key
export const AUDIENCE_TYPE_TO_SEGMENT: Record<string, Segment> = {
  'Pre-Foreclosure':  'pre-foreclosure',
  'Probate':          'probate',
  'Divorce':          'divorce',
  'Tax Delinquent':   'tax-delinquent',
  'Landlord Burnout': 'landlord-burnout',
  'Code Violation':   'vacant-code-violation',
  'Vacant':           'vacant-code-violation',
  'High Equity':      'high-equity',
  'Absentee Owner':   'pre-foreclosure',
  'Closed Deals':     'high-equity',
};

export const AUDIENCE_PRIORITY: Record<string, 'red' | 'orange' | 'yellow'> = {
  'Pre-Foreclosure': 'red',
  'Probate': 'red',
  'Divorce': 'red',
  'Tax Delinquent': 'red',
  'Absentee Owner': 'orange',
  'Landlord Burnout': 'orange',
  'Code Violation': 'orange',
  'Vacant': 'orange',
  'High Equity': 'yellow',
  'Closed Deals': 'yellow',
};

export const MIN_AUDIENCE_RECORDS = 100;
export const LOOKALIKE_THRESHOLD = 50; // leads before lookalike is viable
export const LOOKALIKE_BUDGET_SHIFT_PCT = 60; // % to shift to lookalike at threshold

// ── DFW Counties ──────────────────────────────────────────────────────────────
export const DFW_COUNTIES = ['Dallas', 'Tarrant', 'Denton', 'Collin'] as const;
export type DFWCounty = typeof DFW_COUNTIES[number];

// ── Tier 1 Distress Signals ───────────────────────────────────────────────────
export const TIER1_SIGNALS = [
  { id: 'relationship_status', label: 'Recently changed relationship status (divorced/separated)', defaultOn: true },
  { id: 'recently_bereaved', label: 'Recently bereaved', defaultOn: true },
  { id: 'likely_to_move', label: 'Likely to move', defaultOn: true },
  { id: 'debt_relief', label: 'Debt relief / credit counseling', defaultOn: true },
  { id: 'bankruptcy', label: 'Bankruptcy / financial hardship', defaultOn: true },
  { id: 'foreclosure_assistance', label: 'Foreclosure assistance', defaultOn: true },
  { id: 'family_law', label: 'Family law / divorce attorneys', defaultOn: true },
  { id: 'probate_estate', label: 'Probate / estate planning', defaultOn: true },
  { id: 'legal_aid', label: 'Legal aid services', defaultOn: true },
] as const;

export const TIER2_SIGNALS = [
  { id: 'recently_moved', label: 'Recently moved (Life Event)', defaultOn: false },
  { id: 'newly_engaged', label: 'Newly engaged', defaultOn: false },
  { id: 'senior_living', label: 'Senior living / assisted living', defaultOn: false },
  { id: 'aarp', label: 'AARP / retirement communities', defaultOn: false },
  { id: 'downsizing', label: 'Downsizing / minimalism', defaultOn: false },
  { id: 'moving_companies', label: 'Moving companies / relocation', defaultOn: false },
  { id: 'job_loss', label: 'Job loss / unemployment resources', defaultOn: false },
  { id: 'medical_debt', label: 'Medical debt / health insurance gaps', defaultOn: false },
  { id: 'changed_employer', label: 'Recently changed employer', defaultOn: false },
] as const;

export const TIER3_SIGNALS = [
  { id: 'property_mgmt', label: 'Property management / landlord associations', defaultOn: false },
  { id: 'eviction_process', label: 'Eviction process interest', defaultOn: false },
  { id: 'rei_tired', label: 'Real estate investing (tired landlord overlap)', defaultOn: false },
  { id: 'home_repair', label: 'Home repair / maintenance overload', defaultOn: false },
  { id: 'dfw_prop_mgmt', label: 'Local DFW property management pages', defaultOn: false },
] as const;

// ── Segment Default Headlines ─────────────────────────────────────────────────
export const SEGMENT_HEADLINES: Record<Segment, string> = {
  'pre-foreclosure':       'Facing Foreclosure? Get a Cash Offer Before the Auction Date.',
  'probate':               'Inherited a Property in DFW? We Make It Simple to Sell.',
  'tax-delinquent':        'Behind on Property Taxes? We Buy As-Is and Cover Closing.',
  'divorce':               'Selling During a Divorce? We Close Fast With No Hassle.',
  'landlord-burnout':      'Done Being a Landlord? We\'ll Buy Your Rental As-Is.',
  'vacant-code-violation': 'Problem Property in DFW? We Buy in Any Condition.',
  'senior-downsizing':     'Ready to Downsize? Skip the Listing. Get a Cash Offer.',
  'high-equity':           'Owned Your Home 10+ Years? Find Out What a Cash Offer Looks Like.',
};

export const SEGMENT_COPY_A: Record<Segment, string> = {
  'pre-foreclosure':       'The auction date is coming. We can close in 7 days and stop the process — no banks, no delays, no credit checks.',
  'probate':               'Settling an estate is stressful enough. We buy inherited DFW homes exactly as-is, handle all paperwork, and close on your timeline.',
  'tax-delinquent':        'Property tax debt doesn\'t have to follow you. We pay all back taxes, cover closing costs, and close in as little as 7 days.',
  'divorce':               'Split the equity fairly and quickly. We close fast so both parties can move forward without months of showings and negotiations.',
  'landlord-burnout':      'Bad tenants, repairs, and stress? We buy rental properties as-is. No eviction required. Walkaway with cash.',
  'vacant-code-violation': 'City notices piling up? We buy problem properties in any condition — violations, liens, and all.',
  'senior-downsizing':     'No open houses. No staging. No commissions. Just a fair cash offer so you can move on your timeline.',
  'high-equity':           'After 10+ years, you\'ve built serious equity. Find out what your home is worth to a local cash buyer — no obligation.',
};

export const SEGMENT_COPY_B: Record<Segment, string> = {
  'pre-foreclosure':       'Stop foreclosure now. We buy houses fast — fair cash offer in 24 hours, close in 7 days.',
  'probate':               'Need to sell an inherited DFW home? Cash offer. Any condition. Any timeline.',
  'tax-delinquent':        'Behind on taxes? We pay them off. Cash offer, fast close, zero hassle.',
  'divorce':               'Fast sale, fair split. No agents, no waiting — just cash in hand.',
  'landlord-burnout':      'Done with tenants? Get a cash offer for your rental today.',
  'vacant-code-violation': 'We buy ugly, damaged, and problem properties in DFW. Any condition, fast close.',
  'senior-downsizing':     'Skip the listing. Get a fair cash offer and close on your schedule.',
  'high-equity':           'Cash buyer looking for established DFW homes. Get your offer in 24 hours.',
};

export const SEGMENT_COPY_C: Record<Segment, string> = {
  'pre-foreclosure':       'If you\'re behind on payments in the DFW area, we can help you avoid foreclosure and walk away with cash. No judgment, just options.',
  'probate':               'Dealing with probate in Dallas-Fort Worth? We specialize in estate sales and work around court timelines. Low stress, fair offer.',
  'tax-delinquent':        'DFW homeowner with delinquent taxes? We\'ve helped dozens of families sell fast, clear their tax debt, and start fresh.',
  'divorce':               'Divorce is hard enough. Selling doesn\'t have to be. We work with both parties in DFW to close fast and fair.',
  'landlord-burnout':      'If you own rental property in DFW and you\'re ready to walk away — we\'ll buy it as-is. No showings, no evictions, just a check.',
  'vacant-code-violation': 'Got a property with violations or liens in DFW? We buy those. All conditions, all situations.',
  'senior-downsizing':     'Moving to a smaller place or closer to family? We make selling your DFW home simple, fast, and stress-free.',
  'high-equity':           'Long-time DFW homeowners: find out what a local cash buyer would pay for your home. No obligation, no pressure.',
};

// ── Placement Rules ───────────────────────────────────────────────────────────
export const PLACEMENT_DEFAULTS = {
  feed: true,
  marketplace: true,
  instagram: true,
  audience_network: false, // LOCKED OFF
};

// ── Demographics ──────────────────────────────────────────────────────────────
export const DEMOGRAPHIC_DEFAULTS = {
  homeowners_only: true,   // LOCKED ON
  income_min: 40000,
  income_max: 100000,
  device: 'All',           // LOCKED
};

// ── KPI Thresholds (battle plan targets) ─────────────────────────────────────
export const KPI_THRESHOLDS = {
  CPL_WARNING: 40,          // CPL > $40 for 5+ days = flag
  FREQUENCY_WARNING: 3.0,   // Frequency > 3.0 = fatigue flag
  CONTACT_RATE_MIN: 40,     // Contact rate % minimum
  LOOKALIKE_TRIGGER: 50,    // Lead count for lookalike recommendation
  ESTIMATED_CPL_COLD: { min: 18, max: 35 },
  ESTIMATED_CPL_RETARGETING: { min: 8, max: 14 },
};

// ── Situation → Segment routing ───────────────────────────────────────────────
export const SITUATION_OPTIONS = [
  'Foreclosure',
  'Probate',
  'Divorce',
  'Behind on Taxes',
  'Tired Landlord',
  'Relocating',
  'Inherited',
  'Other',
] as const;
export type Situation = typeof SITUATION_OPTIONS[number];

// ── Twilio Sequences ──────────────────────────────────────────────────────────
export const TWILIO_SEQUENCES: Record<string, string> = {
  'HOT-URGENT':        'Sequence A (5-min callback)',
  'HOT-ESTATE':        'Sequence B (estate script)',
  'HOT-LEGAL':         'Sequence C (neutral script)',
  'HOT-TAX':           'Sequence D (relief script)',
  'WARM-LANDLORD':     'Sequence E (landlord script)',
  'WARM-RELOCATION':   'Sequence F (timeline script)',
  'COLD-NURTURE':      'Long-drip sequence',
};

// ── Retargeting Cadence ───────────────────────────────────────────────────────
export const RETARGETING_CADENCE = [
  { day: 1,  action: 'Show testimonial / social proof ad', audience: 'All form starters' },
  { day: 3,  action: 'Urgency angle — "Still thinking about it?"', audience: 'Non-completers' },
  { day: 7,  action: 'Segment-specific pain point reminder', audience: 'Form starters by segment' },
  { day: 14, action: 'Offer deadline / FOMO creative', audience: 'HOT/WARM only' },
  { day: 30, action: 'Re-engagement — "Still own that property?"', audience: 'All touched' },
];

// ── Headline validation ───────────────────────────────────────────────────────
export const GENERIC_PHRASES = [
  'we buy houses',
  'we buy homes',
  'cash for houses',
  'sell your house fast',
];

export function validateHeadline(text: string, segment: Segment): { valid: boolean; warnings: string[] } {
  const warnings: string[] = [];
  const lower = text.toLowerCase();
  const words = text.trim().split(/\s+/);

  if (words.length > 10) {
    warnings.push('Headline exceeds 10 words — Meta truncates longer headlines.');
  }
  for (const phrase of GENERIC_PHRASES) {
    if (lower.includes(phrase)) {
      warnings.push(`Generic phrase detected: "${phrase}" — battle plan requires segment-specific copy.`);
    }
  }
  const segmentKeywords: Partial<Record<Segment, string[]>> = {
    'pre-foreclosure': ['foreclosure', 'auction', 'payment'],
    'probate': ['inherited', 'estate', 'probate'],
    'divorce': ['divorce', 'split', 'separation'],
    'tax-delinquent': ['tax', 'delinquent', 'taxes'],
    'landlord-burnout': ['landlord', 'rental', 'tenant'],
  };
  const keys = segmentKeywords[segment] || [];
  if (keys.length > 0 && !keys.some(k => lower.includes(k))) {
    warnings.push('Pain-point reference missing — battle plan requires segment-specific language.');
  }
  return { valid: warnings.length === 0, warnings };
}
