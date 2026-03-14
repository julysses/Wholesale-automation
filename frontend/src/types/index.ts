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
  | 'new'
  | 'contacted'
  | 'responding'
  | 'qualified_hot'
  | 'qualified_warm'
  | 'qualified_cold'
  | 'offer_made'
  | 'under_contract'
  | 'dead'
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
