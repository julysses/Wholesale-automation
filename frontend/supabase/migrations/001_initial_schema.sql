-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── LEADS TABLE ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  property_address    TEXT NOT NULL,
  city                TEXT NOT NULL,
  state               TEXT DEFAULT 'TX',
  zip_code            TEXT,
  property_type       TEXT,
  bedrooms            INT,
  bathrooms           NUMERIC(3,1),
  sqft                INT,
  year_built          INT,
  owner_first_name    TEXT,
  owner_last_name     TEXT,
  owner_phone_1       TEXT,
  owner_phone_2       TEXT,
  owner_phone_3       TEXT,
  owner_email         TEXT,
  owner_mailing_address TEXT,
  source              TEXT,
  motivation_tag      TEXT,
  status              TEXT DEFAULT 'new',
  score_motivation    INT CHECK (score_motivation BETWEEN 1 AND 3),
  score_timeline      INT CHECK (score_timeline BETWEEN 1 AND 3),
  score_equity        INT CHECK (score_equity BETWEEN 1 AND 3),
  score_condition     INT CHECK (score_condition BETWEEN 1 AND 3),
  score_flexibility   INT CHECK (score_flexibility BETWEEN 1 AND 3),
  total_score         INT GENERATED ALWAYS AS (
    COALESCE(score_motivation,0) + COALESCE(score_timeline,0) +
    COALESCE(score_equity,0) + COALESCE(score_condition,0) +
    COALESCE(score_flexibility,0)
  ) STORED,
  estimated_arv       NUMERIC(12,2),
  estimated_repairs   NUMERIC(12,2),
  loan_balance        NUMERIC(12,2),
  estimated_equity_pct NUMERIC(5,2),
  mao                 NUMERIC(12,2),
  offer_price         NUMERIC(12,2),
  asking_price        NUMERIC(12,2),
  last_contact_date   DATE,
  next_follow_up_date DATE,
  contact_attempts    INT DEFAULT 0,
  sms_sequence_active BOOLEAN DEFAULT FALSE,
  email_sequence_active BOOLEAN DEFAULT FALSE,
  dnc                 BOOLEAN DEFAULT FALSE,
  seller_notes        TEXT,
  internal_notes      TEXT,
  ai_qualification_summary TEXT,
  assigned_to         UUID
);

-- ─── BUYERS TABLE ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS buyers (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  first_name      TEXT NOT NULL,
  last_name       TEXT NOT NULL,
  company         TEXT,
  email           TEXT,
  phone           TEXT,
  source          TEXT,
  target_zips     TEXT[],
  min_price       NUMERIC(12,2),
  max_price       NUMERIC(12,2),
  property_types  TEXT[],
  min_beds        INT,
  min_baths       NUMERIC(3,1),
  max_repairs     NUMERIC(12,2),
  strategy        TEXT[],
  close_speed_days INT,
  tier            TEXT DEFAULT 'C',
  deals_closed    INT DEFAULT 0,
  pof_verified    BOOLEAN DEFAULT FALSE,
  pof_amount      NUMERIC(12,2),
  active          BOOLEAN DEFAULT TRUE,
  email_opt_in    BOOLEAN DEFAULT TRUE,
  sms_opt_in      BOOLEAN DEFAULT TRUE,
  notes           TEXT,
  last_contact_date DATE
);

-- ─── DEALS TABLE ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS deals (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  lead_id         UUID NOT NULL REFERENCES leads(id),
  deal_name       TEXT,
  stage           TEXT NOT NULL DEFAULT 'offer_made',
  contract_price      NUMERIC(12,2),
  arv                 NUMERIC(12,2),
  repair_estimate     NUMERIC(12,2),
  assignment_fee      NUMERIC(12,2),
  buyer_price         NUMERIC(12,2),
  earnest_money       NUMERIC(12,2),
  contract_date       DATE,
  inspection_deadline DATE,
  closing_date        DATE,
  actual_close_date   DATE,
  seller_name         TEXT,
  buyer_id            UUID REFERENCES buyers(id),
  title_company       TEXT,
  title_contact       TEXT,
  title_phone         TEXT,
  psa_doc_url         TEXT,
  assignment_doc_url  TEXT,
  notes               TEXT,
  assigned_to         UUID
);

-- ─── TASKS TABLE ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  due_date        TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  title           TEXT NOT NULL,
  description     TEXT,
  priority        TEXT DEFAULT 'medium',
  status          TEXT DEFAULT 'pending',
  type            TEXT,
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  deal_id         UUID REFERENCES deals(id) ON DELETE SET NULL,
  buyer_id        UUID REFERENCES buyers(id) ON DELETE SET NULL,
  assigned_to     UUID
);

-- ─── OUTREACH ACTIVITY TABLE ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_activity (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  lead_id     UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  channel     TEXT NOT NULL,
  direction   TEXT NOT NULL,
  status      TEXT,
  message     TEXT,
  response    TEXT,
  duration_seconds INT,
  performed_by UUID
);

-- ─── COMPS TABLE ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS comps (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  address         TEXT NOT NULL,
  city            TEXT,
  zip_code        TEXT,
  sale_price      NUMERIC(12,2),
  sale_date       DATE,
  sqft            INT,
  bedrooms        INT,
  bathrooms       NUMERIC(3,1),
  price_per_sqft  NUMERIC(8,2),
  condition       TEXT,
  distance_miles  NUMERIC(4,2),
  source          TEXT,
  notes           TEXT
);

-- ─── AI AGENT LOG ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_agent_log (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  agent_type      TEXT NOT NULL,
  lead_id         UUID REFERENCES leads(id),
  deal_id         UUID REFERENCES deals(id),
  input_data      JSONB,
  output_data     JSONB,
  tokens_used     INT,
  duration_ms     INT
);

-- ─── INDEXES ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_total_score ON leads(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_zip ON leads(zip_code);
CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_closing_date ON deals(closing_date);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_outreach_lead ON outreach_activity(lead_id);
CREATE INDEX IF NOT EXISTS idx_buyers_tier ON buyers(tier);

-- ─── ROW LEVEL SECURITY ────────────────────────────────────────────────────────
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE buyers ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE comps ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_agent_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON leads FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON deals FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON buyers FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON tasks FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON comps FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON outreach_activity FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON ai_agent_log FOR ALL USING (auth.role() = 'authenticated');

-- ─── UPDATED_AT TRIGGER ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER leads_updated_at BEFORE UPDATE ON leads FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER deals_updated_at BEFORE UPDATE ON deals FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER buyers_updated_at BEFORE UPDATE ON buyers FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── INCREMENT CONTACT ATTEMPTS FUNCTION ──────────────────────────────────────
CREATE OR REPLACE FUNCTION increment_contact_attempts(lead_id UUID)
RETURNS void AS $$
BEGIN
  UPDATE leads SET contact_attempts = contact_attempts + 1, last_contact_date = CURRENT_DATE WHERE id = lead_id;
END;
$$ LANGUAGE plpgsql;
