export interface Lead {
  id: string;
  created_at: string;
  updated_at: string;
  property_address: string;
  city: string;
  state: string;
  zip_code?: string;
  property_type?: string;
  bedrooms?: number;
  bathrooms?: number;
  sqft?: number;
  year_built?: number;
  owner_first_name?: string;
  owner_last_name?: string;
  owner_phone_1?: string;
  owner_phone_2?: string;
  owner_phone_3?: string;
  owner_email?: string;
  owner_mailing_address?: string;
  source?: string;
  motivation_tag?: string;
  status: string;
  score_motivation?: number;
  score_timeline?: number;
  score_equity?: number;
  score_condition?: number;
  score_flexibility?: number;
  total_score?: number;
  estimated_arv?: number;
  estimated_repairs?: number;
  loan_balance?: number;
  estimated_equity_pct?: number;
  mao?: number;
  offer_price?: number;
  asking_price?: number;
  last_contact_date?: string;
  next_follow_up_date?: string;
  contact_attempts: number;
  sms_sequence_active: boolean;
  email_sequence_active: boolean;
  dnc: boolean;
  seller_notes?: string;
  internal_notes?: string;
  ai_qualification_summary?: string;
  assigned_to?: string;
  // Skip trace & blueprint scoring (migration 002 + 004)
  seller_score?: number;
  priority_tier?: 'A' | 'B' | 'C' | 'D';
  stack_name?: string;
  stack_bonus?: number;
  precision_tier?: 1 | 2 | 3;
  priority_rank?: number;
  skip_traced_at?: string;
  skip_trace_provider?: string;
  absentee_owner?: boolean;
  out_of_state_owner?: boolean;
  pre_foreclosure?: boolean;
  tax_delinquent_flag?: boolean;
  vacant?: boolean;
  years_owned?: number;
  apn?: string;
  county?: string;
  phones?: Array<{ number: string; type: string; confidence: number; status: string }>;
  emails_enriched?: Array<{ email: string; confidence: number }>;
  // Vendor refs
  dialer_contact_id?: string;
  dialer_campaign_id?: string;
  launch_control_id?: string;
  podio_item_id?: string;
  resimpli_lead_id?: string;
  // RealtyAPI enrichment (migration 011)
  deal_score?: number;
  tags?: string[];
  motivation_score?: number;
  priority?: boolean;
  list_price?: number;
}

export interface Deal {
  id: string;
  created_at: string;
  updated_at: string;
  lead_id: string;
  deal_name?: string;
  stage: string;
  contract_price?: number;
  arv?: number;
  repair_estimate?: number;
  assignment_fee?: number;
  buyer_price?: number;
  earnest_money?: number;
  contract_date?: string;
  inspection_deadline?: string;
  closing_date?: string;
  actual_close_date?: string;
  seller_name?: string;
  buyer_id?: string;
  title_company?: string;
  title_contact?: string;
  title_phone?: string;
  psa_doc_url?: string;
  assignment_doc_url?: string;
  notes?: string;
  assigned_to?: string;
  // Joined data
  lead?: Lead;
  buyer?: Buyer;
}

export interface Buyer {
  id: string;
  created_at: string;
  updated_at: string;
  first_name: string;
  last_name: string;
  company?: string;
  email?: string;
  phone?: string;
  source?: string;
  target_zips?: string[];
  min_price?: number;
  max_price?: number;
  property_types?: string[];
  min_beds?: number;
  min_baths?: number;
  max_repairs?: number;
  strategy?: string[];
  close_speed_days?: number;
  tier: string;
  deals_closed: number;
  pof_verified: boolean;
  pof_amount?: number;
  active: boolean;
  email_opt_in: boolean;
  sms_opt_in: boolean;
  notes?: string;
  last_contact_date?: string;
}

export interface Task {
  id: string;
  created_at: string;
  due_date?: string;
  completed_at?: string;
  title: string;
  description?: string;
  priority: string;
  status: string;
  type?: string;
  lead_id?: string;
  deal_id?: string;
  buyer_id?: string;
  assigned_to?: string;
  lead?: Lead;
  deal?: Deal;
}

export interface OutreachActivity {
  id: string;
  created_at: string;
  lead_id: string;
  channel: string;
  direction: string;
  status?: string;
  message?: string;
  response?: string;
  duration_seconds?: number;
  performed_by?: string;
}

export interface Comp {
  id: string;
  created_at: string;
  lead_id: string;
  address: string;
  city?: string;
  zip_code?: string;
  sale_price?: number;
  sale_date?: string;
  sqft?: number;
  bedrooms?: number;
  bathrooms?: number;
  price_per_sqft?: number;
  condition?: string;
  distance_miles?: number;
  source?: string;
  notes?: string;
  // RealtyAPI enrichment (migration 011)
  similarity_score?: number;
  raw_payload?: Record<string, unknown>;
  fetched_at?: string;
}

export interface AIAgentLog {
  id: string;
  created_at: string;
  agent_type: string;
  lead_id?: string;
  deal_id?: string;
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  tokens_used?: number;
  duration_ms?: number;
}

// UI Types
export type LeadStatus =
  // Intake
  | 'new'
  | 'normalized'
  | 'skip_traced'
  | 'scored'
  // Dialer flow
  | 'ready_for_dialer'
  | 'in_dialer_campaign'
  | 'contacted'
  // Call outcomes
  | 'no_answer'
  | 'voicemail'
  | 'wrong_number'
  | 'not_interested'
  | 'callback'
  | 'responding'
  // Qualified
  | 'warm'
  | 'hot'
  | 'appointment_set'
  // Legacy aliases (kept for backward compat)
  | 'qualified_hot'
  | 'qualified_warm'
  | 'qualified_cold'
  // Deal flow
  | 'crm_synced'
  | 'offer_made'
  | 'under_contract'
  // SMS / nurture
  | 'sms_nurture'
  | 'acq_review'
  // Terminal
  | 'contracted'
  | 'dead'
  | 'recycle'
  | 'dnc';

export type DealStage =
  | 'offer_made'
  | 'under_contract'
  | 'marketing_to_buyers'
  | 'buyer_found'
  | 'assigned'
  | 'closed'
  | 'cancelled';

export type TaskPriority = 'high' | 'medium' | 'low';
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

export interface KPIData {
  activeLeads: number;
  activeLeadsChange: number;
  underContract: number;
  underContractValue: number;
  closedThisMonth: number;
  closedFees: number;
  pipelineValue: number;
}

export interface QualificationResult {
  score_motivation: number;
  score_timeline: number;
  score_equity: number;
  score_condition: number;
  score_flexibility: number;
  total_score: number;
  tier: 'HOT' | 'WARM' | 'COLD';
  qualification_summary: string;
  recommended_next_action: string;
  key_risks: string[];
}

export interface OfferOption {
  name: string;
  offer_price: number;
  close_timeline: string;
  selling_points: string[];
  pitch: string;
}

export interface OfferResult {
  options: OfferOption[];
  objections: Array<{
    objection: string;
    script: string;
  }>;
}

export interface OutreachVariation {
  channel: string;
  subject?: string;
  body: string;
  estimated_response_rate_notes: string;
}

export interface BuyerMatch {
  buyer: Buyer;
  fit_score: number;
  fit_reason: string;
  personalization_tip: string;
}

export interface BuyerMatchResult {
  ranked_buyers: BuyerMatch[];
  blast_email_subject: string;
  blast_email_body: string;
  blast_sms: string;
}

// ─── Land Wholesaling Module ──────────────────────────────────────────────────

export type LandZoning = 'single_family' | 'multifamily' | 'commercial' | 'agricultural' | 'mixed' | 'unknown';
export type LandWaterSource = 'city' | 'well' | 'none' | 'unknown';
export type LandSewage = 'city_sewer' | 'septic' | 'none' | 'unknown';
export type LandStatus = 'new' | 'vetting' | 'vetted' | 'comped' | 'offer_made' | 'under_contract' | 'dead';
export type LandBuyerType = 'builder' | 'land_banker' | 'trailer_park' | 'mineral_rights';

export interface LandLead {
  id: string;
  created_at: string;
  updated_at: string;
  lead_id?: string;
  xleads_id?: string;
  source: string;
  owner_name: string;
  owner_phone_1?: string;
  owner_phone_2?: string;
  owner_mailing_address?: string;
  owner_email?: string;
  property_address: string;
  city: string;
  state: string;
  zip_code?: string;
  county?: string;
  apn?: string;
  lot_size_acres?: number;
  lot_size_sqft?: number;
  zoning?: LandZoning;
  zoning_raw?: string;
  water_source: LandWaterSource;
  sewage: LandSewage;
  septic_last_pump_date?: string;
  power_available?: boolean;
  power_hookup_possible?: boolean;
  is_buildable?: boolean;
  buildability_issues?: string[];
  flood_zone?: string;
  infill_lot: boolean;
  infill_confirmed_at?: string;
  tav?: number;
  asking_price?: number;
  offer_price?: number;
  mao?: number;
  status: LandStatus;
  vetting_passed?: boolean;
  assigned_to?: string;
  internal_notes?: string;
  seller_notes?: string;
  contact_attempts: number;
  last_contact_date?: string;
  dnc: boolean;
  sms_sequence_active: boolean;
  dialer_campaign_id?: string;
  // Joined
  vetting?: LandVetting;
  comps?: LandComps;
}

export interface LandVetting {
  id: string;
  created_at: string;
  land_lead_id: string;
  vetted_by?: string;
  completed_at?: string;
  // Must 1
  lot_size_confirmed?: boolean;
  lot_size_record?: number;
  lot_size_actual?: number;
  lot_size_notes?: string;
  // Must 2
  zoning_confirmed?: boolean;
  zoning_type?: LandZoning;
  zoning_notes?: string;
  // Must 3
  seller_motivation?: string;
  motivation_score?: number;
  motivation_tag?: string;
  // Must 4
  water_confirmed?: boolean;
  water_source?: LandWaterSource;
  water_notes?: string;
  // Must 5
  sewage_confirmed?: boolean;
  sewage_type?: LandSewage;
  septic_pump_date?: string;
  sewage_notes?: string;
  // Must 6
  power_confirmed?: boolean;
  power_type?: string;
  power_notes?: string;
  // Must 7
  buildability_confirmed?: boolean;
  can_build?: boolean;
  buildability_issues?: string[];
  buildability_notes?: string;
  // Result
  passed?: boolean;
  fail_reasons?: string[];
  recommendation?: string;
}

// ── Lead Generation Engine ─────────────────────────────────────────────────────

export interface AdCampaign {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  platform: 'facebook' | 'instagram' | 'google' | 'tiktok';
  status: 'active' | 'paused' | 'completed' | 'draft';
  campaign_objective?: string;
  external_campaign_id?: string;
  daily_budget?: number;
  total_spend: number;
  impressions: number;
  clicks: number;
  leads_count: number;
  cpl?: number;
  avg_lead_quality_score?: number;
  target_zip_codes?: string[];
  target_audience_notes?: string;
  start_date?: string;
  end_date?: string;
  settings?: Record<string, unknown>;
}

export interface AdCreative {
  id: string;
  created_at: string;
  updated_at: string;
  campaign_id: string;
  name: string;
  headline?: string;
  primary_text?: string;
  cta_text?: string;
  pain_point_angle?: string;
  image_url?: string;
  external_ad_id?: string;
  status: 'active' | 'paused' | 'winner' | 'archived';
  impressions: number;
  clicks: number;
  leads_count: number;
  total_spend: number;
  cpl?: number;
  avg_lead_quality_score?: number;
  is_winner: boolean;
}

export interface FormQuestion {
  id: string;
  step: number;
  type: 'radio' | 'text' | 'tel' | 'email' | 'number' | 'checkbox';
  field_name: string;
  label: string;
  placeholder?: string;
  required: boolean;
  options?: { value: string; label: string; score_hint?: number }[];
}

export interface LeadFormConfig {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  slug: string;
  campaign_id?: string;
  headline: string;
  subheadline?: string;
  brand_color: string;
  logo_url?: string;
  thank_you_message?: string;
  send_confirmation_sms: boolean;
  send_confirmation_email: boolean;
  active: boolean;
  questions: FormQuestion[];
  redirect_url?: string;
}

export interface LeadFormSubmission {
  id: string;
  created_at: string;
  form_id: string;
  lead_id?: string;
  ip_address?: string;
  user_agent?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  raw_answers: Record<string, unknown>;
  computed_motivation_tag?: string;
  computed_timeline?: string;
  computed_condition?: string;
  processing_status: 'pending' | 'processed' | 'failed';
}

export interface LandComps {
  id: string;
  created_at: string;
  land_lead_id: string;
  direct_comp_avg?: number;
  direct_comp_count?: number;
  direct_comp_low?: number;
  direct_comp_high?: number;
  direct_comp_details?: Array<{ address: string; price: number; sqft: number; date: string; distance_mi: number }>;
  avg_house_arv?: number;
  arv_15pct_value?: number;
  house_comp_count?: number;
  tav?: number;
  tav_source?: string;
  recommended_offer_low?: number;
  recommended_offer_high?: number;
  comp_notes?: string;
}

export interface LandBuyer extends Buyer {
  land_buyer_type?: LandBuyerType;
  target_acres_min?: number;
  target_acres_max?: number;
  preferred_zoning?: LandZoning[];
  buys_land: boolean;
  buys_infill: boolean;
}

export interface DealAnalysis {
  arv: number;
  repairs: number;
  assignmentFee: number;
  mao: number;
  scenarios: {
    atMao: number;
    fiveBelow: number;
    tenBelow: number;
  };
  recommendation?: string;
}

// ─── Investor Buyer Intelligence Engine (IBIE) ────────────────────────────────

export type IBIETier = 'A' | 'B' | 'C' | 'D';
export type IBIEBuyerType = 'flipper' | 'landlord' | 'institutional' | 'builder';

/** Extended buyer row from buyer_leaderboard view (includes IBIE fields) */
export interface IBIEBuyer extends Buyer {
  entity_name?: string;
  market?: string;
  ibie_score: number;
  ibie_tier: IBIETier;
  buyer_type_ibie?: IBIEBuyerType;
  ai_classified_at?: string;
  cash_buyer: boolean;
  repeat_buyer: boolean;
  total_purchases_12mo: number;
  properties_owned: number;
  avg_purchase_price?: number;
  last_purchase_date?: string;
  lender_used?: string;
  tags: string[];
  engagement_delta: number;
  outreach_ignore_count: number;
  last_scored_at?: string;
  score_version: number;
  transaction_count?: number;
  most_recent_purchase?: string;
}

/** Single property purchase record (from county records) */
export interface BuyerTransaction {
  id: string;
  created_at: string;
  buyer_id: string;
  property_address: string;
  city?: string;
  state: string;
  zip_code?: string;
  county?: string;
  purchase_price?: number;
  purchase_date?: string;
  cash_transaction: boolean;
  lender_name?: string;
  loan_amount?: number;
  property_type?: string;
  sqft?: number;
  bedrooms?: number;
  bathrooms?: number;
  year_built?: number;
  resale_date?: string;
  resale_price?: number;
  flip_detected: boolean;
  apn?: string;
  grantor?: string;
  grantee?: string;
  source: string;
}

/** Detailed deal targeting preferences for a buyer */
export interface BuyerPreference {
  id: string;
  buyer_id: string;
  min_price?: number;
  max_price?: number;
  preferred_property_types: string[];
  preferred_condition: string;
  preferred_zips: string[];
  preferred_counties: string[];
  target_roi?: number;
  max_days_to_close?: number;
  requires_seller_finance: boolean;
  requires_subject_to: boolean;
  pays_above_market: boolean;
  contact_method: string;
  notes?: string;
}

/** Result of matching a buyer to a deal */
export interface DealMatch {
  id: string;
  deal_id: string;
  buyer_id: string;
  zip_score: number;
  price_score: number;
  type_score: number;
  ibie_score: number;
  match_score: number;
  rank: number;
  sms_sent_at?: string;
  email_sent_at?: string;
  responded_at?: string;
  response_type?: string;
  buyer?: IBIEBuyer;
}

/** Outreach sent to a buyer (SMS or email) */
export interface BuyerOutreach {
  id: string;
  created_at: string;
  buyer_id: string;
  deal_id?: string;
  channel: 'sms' | 'email';
  direction: string;
  status: string;
  subject?: string;
  body: string;
  to_address: string;
  provider?: string;
  opened_at?: string;
  replied_at?: string;
  reply_body?: string;
  buyer?: Pick<IBIEBuyer, 'first_name' | 'last_name'>;
}

/** CSV import log row */
export interface BuyerImportLog {
  id: string;
  created_at: string;
  source: string;
  filename?: string;
  market?: string;
  rows_total: number;
  rows_imported: number;
  buyers_created: number;
  buyers_updated: number;
  transactions_created: number;
  rows_skipped: number;
  errors: Array<{ row: number; error: string }>;
  status: 'pending' | 'processing' | 'complete' | 'failed';
  completed_at?: string;
}

// ── RealtyAPI Integration Types (migration 011) ───────────────────────────────

export interface PropertyEnrichment {
  id: string;
  lead_id: string;
  address: string;
  beds?: number;
  baths?: number;
  sqft?: number;
  year_built?: number;
  lot_size_sqft?: number;
  last_sale_price?: number;
  last_sale_date?: string;
  zestimate?: number;
  tax_assessment?: number;
  property_type?: string;
  zpid?: string;
  data_source?: string;
  raw_payload?: Record<string, unknown>;
  fetched_at: string;
}

export interface ArvResult {
  id: string;
  lead_id: string;
  arv_low?: number;
  arv_mid?: number;
  arv_high?: number;
  avg_ppsf?: number;
  comp_count?: number;
  confidence?: 'high' | 'medium' | 'low';
  methodology?: string;
  computed_at: string;
}

export interface RentalYield {
  id: string;
  lead_id: string;
  ltr_monthly_est?: number;
  str_monthly_est?: number;
  str_occupancy?: number;
  str_adr?: number;
  gross_yield_ltr?: number;
  gross_yield_str?: number;
  fetched_at: string;
}

export interface MarketPulse {
  id: string;
  zip_code: string;
  median_list_price?: number;
  median_ppsf?: number;
  avg_dom?: number;
  list_to_sale_ratio?: number;
  price_cut_pct?: number;
  market_temp?: 'hot' | 'warm' | 'neutral' | 'cool';
  fetched_at: string;
}
