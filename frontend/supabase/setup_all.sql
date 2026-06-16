-- =====================================================================
-- WholesaleOS — complete database setup
-- Run this ONCE in the Supabase Dashboard → SQL Editor (project
-- dvzhzlipbwzzcliujzyz), then create your admin user.
--
-- It applies migrations 001–010 + 013 in order. Migrations 011/012 belong
-- to the unmerged RealtyAPI PR and are intentionally omitted.
--
-- Why this is needed: the project's public schema was never applied, but an
-- orphaned on_auth_user_created trigger remained — it tried to INSERT INTO a
-- non-existent "profiles" table, so every signup failed with
-- "Database error creating new user". We drop that orphan first, then build
-- the real schema (which recreates the trigger correctly).
-- =====================================================================

-- 0) Remove the orphaned signup trigger + function from the prior partial setup.
drop trigger if exists on_auth_user_created on auth.users;
drop function if exists public.handle_new_user() cascade;


-- ============================================================
-- BEGIN 001_initial_schema.sql
-- ============================================================
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

-- END 001_initial_schema.sql

-- ============================================================
-- BEGIN 002_workflow_enhancements.sql
-- ============================================================
-- ─── Migration 002: Workflow Enhancements ─────────────────────────────────────
-- Adds blueprint-aligned scoring columns, skip-trace tracking, dialer refs,
-- and the full set of supporting tables needed for automated outreach routing.

-- ── New columns on leads ───────────────────────────────────────────────────────

ALTER TABLE leads ADD COLUMN IF NOT EXISTS apn                  TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS county               TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS absentee_owner       BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS out_of_state_owner   BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS pre_foreclosure      BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS tax_delinquent_flag  BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS vacant               BOOLEAN DEFAULT FALSE;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS years_owned          INT;

-- Seller score (blueprint additive formula: +20 absentee, +20 vacant, etc.)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS seller_score         INT;
-- Priority tier: A (70+), B (50-69), C (30-49), D (<30)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS priority_tier        TEXT CHECK (priority_tier IN ('A','B','C','D'));

-- Skip trace tracking
ALTER TABLE leads ADD COLUMN IF NOT EXISTS skip_traced_at       TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS skip_trace_provider  TEXT DEFAULT 'batchdata';

-- Phone enrichment from skip trace (in addition to existing owner_phone_*)
ALTER TABLE leads ADD COLUMN IF NOT EXISTS phones               JSONB DEFAULT '[]'::jsonb;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS emails_enriched      JSONB DEFAULT '[]'::jsonb;

-- Dialer & CRM references
ALTER TABLE leads ADD COLUMN IF NOT EXISTS dialer_contact_id    TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS dialer_campaign_id   TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS launch_control_id    TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS podio_item_id        TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS resimpli_lead_id     TEXT;

-- ── New index on tier ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_leads_priority_tier ON leads(priority_tier);
CREATE INDEX IF NOT EXISTS idx_leads_seller_score  ON leads(seller_score DESC);

-- ─── CAMPAIGNS ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaigns (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  name            TEXT NOT NULL,
  type            TEXT NOT NULL DEFAULT 'dialer',  -- dialer | sms | email
  status          TEXT NOT NULL DEFAULT 'active',  -- active | paused | completed
  dialer          TEXT,                            -- batchdialer | readymode
  external_id     TEXT,                            -- vendor campaign id
  settings        JSONB DEFAULT '{}'::jsonb,
  notes           TEXT
);

CREATE TRIGGER campaigns_updated_at BEFORE UPDATE ON campaigns FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── CAMPAIGN MEMBERS ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campaign_members (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  campaign_id     UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  status          TEXT NOT NULL DEFAULT 'active',  -- active | paused | completed | removed
  external_contact_id TEXT,
  added_at        TIMESTAMPTZ DEFAULT NOW(),
  removed_at      TIMESTAMPTZ,
  UNIQUE (campaign_id, lead_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_members_lead     ON campaign_members(lead_id);
CREATE INDEX IF NOT EXISTS idx_campaign_members_campaign ON campaign_members(campaign_id);

-- ─── CALL EVENTS ──────────────────────────────────────────────────────────────
-- Stores normalized call results from BatchDialer / Readymode webhooks.
CREATE TABLE IF NOT EXISTS call_events (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  dialer          TEXT NOT NULL DEFAULT 'batchdialer',
  agent_id        TEXT,
  phone_number    TEXT,
  -- Normalized disposition: NO_ANSWER|VOICEMAIL|WRONG_NUMBER|DNC|NOT_INTERESTED|
  --                         CALLBACK|WARM|HOT|APPOINTMENT_SET
  disposition     TEXT NOT NULL,
  duration_sec    INT,
  recording_url   TEXT,
  notes           TEXT,
  raw_payload     JSONB DEFAULT '{}'::jsonb,
  occurred_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_events_lead        ON call_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_call_events_disposition ON call_events(disposition);

-- ─── SMS EVENTS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sms_events (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  provider        TEXT NOT NULL DEFAULT 'launch_control',
  direction       TEXT NOT NULL DEFAULT 'outbound',  -- outbound | inbound
  phone_number    TEXT,
  body            TEXT,
  status          TEXT,   -- sent | delivered | failed | replied
  opt_out         BOOLEAN DEFAULT FALSE,
  raw_payload     JSONB DEFAULT '{}'::jsonb,
  occurred_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sms_events_lead     ON sms_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_sms_events_opt_out  ON sms_events(opt_out) WHERE opt_out = TRUE;

-- ─── DNC REGISTRY ─────────────────────────────────────────────────────────────
-- Immutable — records are never deleted.
CREATE TABLE IF NOT EXISTS dnc_registry (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  phone_number    TEXT,
  email           TEXT,
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  reason          TEXT NOT NULL DEFAULT 'opt_out',  -- opt_out | manual | litigator | national_dnc
  source          TEXT,  -- sms_reply | call_disposition | manual | import
  opt_out_keyword TEXT,
  raw_payload     JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dnc_phone ON dnc_registry(phone_number);
CREATE INDEX IF NOT EXISTS idx_dnc_email ON dnc_registry(email);

-- ─── VENDOR SYNC LOGS ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendor_sync_logs (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  vendor          TEXT NOT NULL,   -- batchdata | batchdialer | podio | resimpli | launch_control
  direction       TEXT NOT NULL,   -- push | pull | webhook
  entity_type     TEXT,            -- lead | contact | campaign | call_event
  entity_id       UUID,
  status          TEXT NOT NULL DEFAULT 'success',  -- success | error | partial
  records_affected INT DEFAULT 0,
  error_message   TEXT,
  duration_ms     INT,
  raw_response    JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_vendor_sync_vendor ON vendor_sync_logs(vendor);
CREATE INDEX IF NOT EXISTS idx_vendor_sync_status ON vendor_sync_logs(status);

-- ─── RAW VENDOR PAYLOADS ──────────────────────────────────────────────────────
-- Immutable audit record of every raw API payload received/sent.
CREATE TABLE IF NOT EXISTS raw_vendor_payloads (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  vendor          TEXT NOT NULL,
  direction       TEXT NOT NULL,  -- inbound | outbound
  endpoint        TEXT,
  payload         JSONB NOT NULL,
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_payloads_vendor ON raw_vendor_payloads(vendor);

-- ─── RLS for new tables ────────────────────────────────────────────────────────
ALTER TABLE campaigns           ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_members    ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_events         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sms_events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE dnc_registry        ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_sync_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_vendor_payloads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON campaigns           FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON campaign_members    FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON call_events         FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON sms_events          FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON dnc_registry        FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON vendor_sync_logs    FOR ALL USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_full_access" ON raw_vendor_payloads FOR ALL USING (auth.role() = 'authenticated');

-- END 002_workflow_enhancements.sql

-- ============================================================
-- BEGIN 003_user_management.sql
-- ============================================================
-- ─── Migration 003: User Management + Notification System ───────────────────
-- Adds user profiles (role + approval status), in-app notifications,
-- and a setup checklist table.

-- ─── PROFILES ─────────────────────────────────────────────────────────────────
-- One row per auth.user. Created automatically via trigger on signup.
CREATE TABLE IF NOT EXISTS profiles (
  id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW(),
  email         TEXT NOT NULL,
  full_name     TEXT,
  -- role: admin | user
  role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
  -- status: pending (awaiting admin approval) | approved | denied | suspended
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'denied', 'suspended')),
  avatar_url    TEXT,
  approved_at   TIMESTAMPTZ,
  approved_by   UUID REFERENCES auth.users(id),
  denied_at     TIMESTAMPTZ,
  denied_by     UUID REFERENCES auth.users(id),
  denied_reason TEXT,
  last_seen_at  TIMESTAMPTZ
);

CREATE TRIGGER profiles_updated_at BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_role   ON profiles(role);

-- ── Auto-create profile on signup ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  admin_email TEXT := current_setting('app.admin_email', true);
  first_user  BOOLEAN;
BEGIN
  -- Check if this is the very first user (admin bootstrap)
  SELECT NOT EXISTS(SELECT 1 FROM profiles LIMIT 1) INTO first_user;

  INSERT INTO profiles (id, email, full_name, role, status, approved_at)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    -- First user or admin_email match gets admin + auto-approved
    CASE WHEN first_user OR NEW.email = admin_email THEN 'admin' ELSE 'user' END,
    CASE WHEN first_user OR NEW.email = admin_email THEN 'approved' ELSE 'pending' END,
    CASE WHEN first_user OR NEW.email = admin_email THEN NOW() ELSE NULL END
  );

  -- Notify admins of new pending user (skip for first admin)
  IF NOT first_user AND NEW.email != admin_email THEN
    INSERT INTO app_notifications (
      recipient_role, type, title, body,
      action_url, metadata
    ) VALUES (
      'admin', 'new_user_pending',
      'New User Awaiting Approval',
      COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email) || ' has requested access to WholesaleOS.',
      '/admin/users',
      jsonb_build_object('user_id', NEW.id, 'email', NEW.email)
    );
  END IF;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ─── APP NOTIFICATIONS ────────────────────────────────────────────────────────
-- Stores in-app notifications. Supports:
--   recipient_id  → specific user
--   recipient_role → broadcast to all users of that role (admin | user | all)
CREATE TABLE IF NOT EXISTS app_notifications (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  -- Target: either a specific user or broadcast to a role
  recipient_id   UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  recipient_role TEXT,  -- admin | user | all (used when recipient_id is null)
  -- Notification content
  type           TEXT NOT NULL,  -- new_user_pending | hot_lead | appointment_set |
                                 --   skip_trace_complete | pipeline_step | system
  title          TEXT NOT NULL,
  body           TEXT NOT NULL,
  -- Optional deep-link
  action_url     TEXT,
  action_label   TEXT,
  -- Lead / deal context
  lead_id        UUID REFERENCES leads(id) ON DELETE SET NULL,
  deal_id        UUID REFERENCES deals(id) ON DELETE SET NULL,
  -- State
  read           BOOLEAN DEFAULT FALSE,
  read_at        TIMESTAMPTZ,
  -- Extra data
  metadata       JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient   ON app_notifications(recipient_id) WHERE recipient_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_role        ON app_notifications(recipient_role) WHERE recipient_role IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_unread      ON app_notifications(read) WHERE read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_type        ON app_notifications(type);

-- ─── SETUP CHECKLIST ──────────────────────────────────────────────────────────
-- Tracks which setup steps each admin has completed.
CREATE TABLE IF NOT EXISTS setup_checklist (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  step         TEXT NOT NULL,   -- anthropic | supabase | agency | batchdata |
                                --  batchdialer | launch_control | email | test_complete
  completed    BOOLEAN DEFAULT FALSE,
  completed_at TIMESTAMPTZ,
  skipped      BOOLEAN DEFAULT FALSE,
  notes        TEXT,
  UNIQUE (user_id, step)
);

CREATE INDEX IF NOT EXISTS idx_setup_checklist_user ON setup_checklist(user_id);

-- ─── RLS ──────────────────────────────────────────────────────────────────────

ALTER TABLE profiles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup_checklist  ENABLE ROW LEVEL SECURITY;

-- Profiles: users can read their own; admins can read all; admins can update all
CREATE POLICY "profiles_read_own"    ON profiles FOR SELECT USING (id = auth.uid());
CREATE POLICY "profiles_admin_read"  ON profiles FOR SELECT USING (
  EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);
CREATE POLICY "profiles_admin_write" ON profiles FOR UPDATE USING (
  EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);

-- Notifications: users see their own + broadcasts to their role
CREATE POLICY "notifications_read" ON app_notifications FOR SELECT USING (
  recipient_id = auth.uid()
  OR recipient_role = 'all'
  OR (
    recipient_role = 'admin'
    AND EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
  )
  OR (
    recipient_role = 'user'
    AND EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.status = 'approved')
  )
);
CREATE POLICY "notifications_update_own" ON app_notifications FOR UPDATE USING (
  recipient_id = auth.uid()
  OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin')
);

-- Setup checklist: only own rows
CREATE POLICY "setup_own" ON setup_checklist FOR ALL USING (user_id = auth.uid());

-- ─── PROTECT ALL DATA TABLES FROM PENDING/DENIED USERS ────────────────────────
-- Add an approved-user check to all existing table policies.
-- These supplement the existing "authenticated_full_access" policies.

CREATE OR REPLACE FUNCTION is_approved()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
  SELECT EXISTS (
    SELECT 1 FROM profiles
    WHERE id = auth.uid() AND status = 'approved'
  );
$$;

-- Helper view so frontend can check own profile without a full table scan
CREATE OR REPLACE VIEW my_profile AS
  SELECT id, email, full_name, role, status, avatar_url, created_at, approved_at
  FROM profiles
  WHERE id = auth.uid();

GRANT SELECT ON my_profile TO authenticated;

-- ─── FUNCTION: Admin approve / deny ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION admin_set_user_status(
  target_user_id UUID,
  new_status TEXT,
  reason TEXT DEFAULT NULL
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  -- Only admins may call this
  IF NOT EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') THEN
    RAISE EXCEPTION 'Unauthorized: admin role required';
  END IF;

  UPDATE profiles SET
    status      = new_status,
    approved_at = CASE WHEN new_status = 'approved' THEN NOW() ELSE approved_at END,
    approved_by = CASE WHEN new_status = 'approved' THEN auth.uid() ELSE approved_by END,
    denied_at   = CASE WHEN new_status = 'denied'   THEN NOW() ELSE denied_at   END,
    denied_by   = CASE WHEN new_status = 'denied'   THEN auth.uid() ELSE denied_by  END,
    denied_reason = COALESCE(reason, denied_reason)
  WHERE id = target_user_id;

  -- Notify the user of the decision
  INSERT INTO app_notifications (recipient_id, type, title, body, action_url)
  VALUES (
    target_user_id,
    CASE new_status WHEN 'approved' THEN 'access_approved' ELSE 'access_denied' END,
    CASE new_status WHEN 'approved' THEN 'Access Approved' ELSE 'Access Denied' END,
    CASE new_status
      WHEN 'approved' THEN 'Your account has been approved. You can now access WholesaleOS.'
      ELSE COALESCE('Your access request was denied. ' || reason, 'Your access request was not approved.')
    END,
    '/login'
  );
END;
$$;

-- ─── FUNCTION: Admin set role ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION admin_set_user_role(
  target_user_id UUID,
  new_role TEXT
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin') THEN
    RAISE EXCEPTION 'Unauthorized: admin role required';
  END IF;
  UPDATE profiles SET role = new_role WHERE id = target_user_id;
END;
$$;

-- END 003_user_management.sql

-- ============================================================
-- BEGIN 004_distress_stacking.sql
-- ============================================================
-- ── Migration 004: Distress stacking + AI calling columns ─────────────────────
-- Adds government data signal columns, stacking score fields,
-- AI calling records table, and appointments table.

-- ── 1. New signal columns on leads ────────────────────────────────────────────

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS code_violation_status  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS utility_shutoff_status BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS municipal_lien_status  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS pre_foreclosure_status BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS probate_status         BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS lien_amount            NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS year_built             SMALLINT,
  ADD COLUMN IF NOT EXISTS beds                   SMALLINT,
  ADD COLUMN IF NOT EXISTS baths                  NUMERIC(4,1),
  ADD COLUMN IF NOT EXISTS sqft                   INTEGER,
  ADD COLUMN IF NOT EXISTS property_type          TEXT DEFAULT 'single_family';

-- ── 2. Stack scoring columns ───────────────────────────────────────────────────

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS stack_name   TEXT,
  ADD COLUMN IF NOT EXISTS stack_bonus  INTEGER DEFAULT 0;

-- Rename stacked_score → seller_score if migration 002 used stacked_score
-- (safe: does nothing if seller_score already exists from 002)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'leads' AND column_name = 'stacked_score'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'leads' AND column_name = 'seller_score'
  ) THEN
    ALTER TABLE leads RENAME COLUMN stacked_score TO seller_score;
  END IF;
END $$;

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS seller_score  INTEGER,
  ADD COLUMN IF NOT EXISTS priority_tier TEXT CHECK (priority_tier IN ('A','B','C','D'));

-- ── 3. AI calling records ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_call_records (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  provider        TEXT NOT NULL CHECK (provider IN ('retell','air_ai')),
  call_id         TEXT NOT NULL UNIQUE,
  phone_number    TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'initiated',
  disposition     TEXT,
  duration_sec    INTEGER,
  recording_url   TEXT,
  transcript      TEXT,
  -- Qualification answers extracted by AI
  timeline_to_sell    TEXT,
  property_condition  TEXT,
  occupancy           TEXT,
  mortgage_balance    NUMERIC(12,2),
  asking_price        NUMERIC(12,2),
  call_notes          TEXT,
  -- Metadata
  campaign_id     TEXT,
  raw_payload     JSONB,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ai_call_records_lead_id_idx ON ai_call_records(lead_id);
CREATE INDEX IF NOT EXISTS ai_call_records_disposition_idx ON ai_call_records(disposition);

-- ── 4. Appointments table ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS appointments (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
  scheduled_at    TIMESTAMPTZ NOT NULL,
  appointment_type TEXT NOT NULL DEFAULT 'phone'
                  CHECK (appointment_type IN ('phone','in_person','video')),
  status          TEXT NOT NULL DEFAULT 'scheduled'
                  CHECK (status IN ('scheduled','confirmed','completed','no_show','cancelled')),
  notes           TEXT,
  -- Source of appointment (call, sms, manual)
  source          TEXT DEFAULT 'ai_call',
  ai_call_id      UUID REFERENCES ai_call_records(id) ON DELETE SET NULL,
  created_by      UUID REFERENCES auth.users(id),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS appointments_lead_id_idx ON appointments(lead_id);
CREATE INDEX IF NOT EXISTS appointments_scheduled_at_idx ON appointments(scheduled_at);

-- ── 5. Lead scores history ─────────────────────────────────────────────────────
-- Keeps a scoring audit trail each time SellerScoreAgent runs

CREATE TABLE IF NOT EXISTS lead_scores (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
  seller_score    INTEGER NOT NULL,
  priority_tier   TEXT NOT NULL,
  signal_score    INTEGER NOT NULL,
  stack_name      TEXT,
  stack_bonus     INTEGER DEFAULT 0,
  score_breakdown JSONB,
  active_signals  TEXT[],
  routing_action  TEXT,
  scored_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS lead_scores_lead_id_idx ON lead_scores(lead_id);
CREATE INDEX IF NOT EXISTS lead_scores_priority_tier_idx ON lead_scores(priority_tier);

-- ── 6. Updated_at triggers ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ai_call_records_updated_at ON ai_call_records;
CREATE TRIGGER ai_call_records_updated_at
  BEFORE UPDATE ON ai_call_records
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS appointments_updated_at ON appointments;
CREATE TRIGGER appointments_updated_at
  BEFORE UPDATE ON appointments
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── 7. RLS policies ───────────────────────────────────────────────────────────

ALTER TABLE ai_call_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments    ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_scores     ENABLE ROW LEVEL SECURITY;

-- Approved users can read all call records / appointments / scores
CREATE POLICY "approved_read_ai_calls"
  ON ai_call_records FOR SELECT
  TO authenticated
  USING (is_approved());

CREATE POLICY "approved_write_ai_calls"
  ON ai_call_records FOR INSERT
  TO authenticated
  WITH CHECK (is_approved());

CREATE POLICY "approved_read_appointments"
  ON appointments FOR SELECT
  TO authenticated
  USING (is_approved());

CREATE POLICY "approved_write_appointments"
  ON appointments FOR ALL
  TO authenticated
  USING (is_approved())
  WITH CHECK (is_approved());

CREATE POLICY "approved_read_lead_scores"
  ON lead_scores FOR SELECT
  TO authenticated
  USING (is_approved());

CREATE POLICY "approved_write_lead_scores"
  ON lead_scores FOR INSERT
  TO authenticated
  WITH CHECK (is_approved());

-- ── 8. Dashboard view: funnel metrics ─────────────────────────────────────────

CREATE OR REPLACE VIEW funnel_metrics AS
SELECT
  COUNT(*)                                          AS total_leads,
  COUNT(*) FILTER (WHERE priority_tier = 'A')       AS tier_a,
  COUNT(*) FILTER (WHERE priority_tier = 'B')       AS tier_b,
  COUNT(*) FILTER (WHERE priority_tier = 'C')       AS tier_c,
  COUNT(*) FILTER (WHERE priority_tier = 'D')       AS tier_d,
  COUNT(*) FILTER (WHERE seller_score >= 70)        AS calling_eligible,
  (SELECT COUNT(*) FROM ai_call_records)            AS total_calls,
  (SELECT COUNT(*) FROM ai_call_records
   WHERE disposition NOT IN ('no_answer','voicemail','unknown'))
                                                    AS conversations,
  (SELECT COUNT(*) FROM ai_call_records
   WHERE disposition IN ('warm','hot','appointment_set'))
                                                    AS interested,
  (SELECT COUNT(*) FROM ai_call_records
   WHERE disposition = 'hot')                       AS hot_leads,
  (SELECT COUNT(*) FROM appointments)               AS appointments,
  (SELECT COUNT(*) FROM appointments
   WHERE status = 'completed')                      AS appointments_completed
FROM leads;

-- END 004_distress_stacking.sql

-- ============================================================
-- BEGIN 005_call_transcripts.sql
-- ============================================================
-- ── Migration 005: Call transcripts, qualification results, audit logs ────────

-- ── 1. call_transcripts ───────────────────────────────────────────────────────
-- Stores raw and processed transcripts from AI calling sessions.

CREATE TABLE IF NOT EXISTS call_transcripts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id         TEXT NOT NULL UNIQUE,     -- matches ai_call_records.call_id
  lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
  provider        TEXT NOT NULL DEFAULT 'retell',
  raw_transcript  TEXT,                     -- verbatim transcript text
  formatted       JSONB,                    -- [{role, content, timestamp}, ...]
  word_count      INTEGER GENERATED ALWAYS AS (
    CASE WHEN raw_transcript IS NOT NULL
      THEN array_length(string_to_array(trim(raw_transcript), ' '), 1)
      ELSE 0
    END
  ) STORED,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS call_transcripts_call_id_idx  ON call_transcripts(call_id);
CREATE INDEX IF NOT EXISTS call_transcripts_lead_id_idx  ON call_transcripts(lead_id);

-- ── 2. qualification_results ──────────────────────────────────────────────────
-- LLM-extracted qualification signals + blueprint scoring per call.

CREATE TABLE IF NOT EXISTS qualification_results (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id               TEXT NOT NULL,
  lead_id               UUID REFERENCES leads(id) ON DELETE SET NULL,
  transcript_id         UUID REFERENCES call_transcripts(id) ON DELETE SET NULL,

  -- Extracted signals
  timeline              TEXT CHECK (timeline IN (
                          'immediately','30_days','60_days','3_to_6_months','no_timeline'
                        )),
  condition             TEXT CHECK (condition IN (
                          'fully_updated','minor_repairs','needs_repairs','major_repairs'
                        )),
  occupancy             TEXT CHECK (occupancy IN (
                          'owner_occupied','tenant_occupied','vacant'
                        )),
  asking_price          NUMERIC(12,2),
  mortgage_balance      NUMERIC(12,2),
  sentiment             TEXT CHECK (sentiment IN (
                          'motivated','neutral','hesitant','not_interested'
                        )),

  -- Negative flags
  expressed_no_interest BOOLEAN DEFAULT FALSE,
  hung_up               BOOLEAN DEFAULT FALSE,
  named_price           BOOLEAN DEFAULT FALSE,

  -- Scoring
  qualification_score   INTEGER NOT NULL DEFAULT 0,
  classification        TEXT NOT NULL DEFAULT 'COLD'
                        CHECK (classification IN ('HOT','WARM','COLD')),
  score_breakdown       JSONB,

  -- Offer guidance
  offer_range_low       NUMERIC(12,2),
  offer_range_high      NUMERIC(12,2),

  -- LLM output
  summary               TEXT,
  key_quotes            TEXT[],

  created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS qual_results_lead_id_idx       ON qualification_results(lead_id);
CREATE INDEX IF NOT EXISTS qual_results_classification_idx ON qualification_results(classification);
CREATE INDEX IF NOT EXISTS qual_results_call_id_idx        ON qualification_results(call_id);

-- ── 3. Add qual columns to ai_call_records ────────────────────────────────────

ALTER TABLE ai_call_records
  ADD COLUMN IF NOT EXISTS qual_score          INTEGER,
  ADD COLUMN IF NOT EXISTS classification      TEXT CHECK (classification IN ('HOT','WARM','COLD')),
  ADD COLUMN IF NOT EXISTS qual_result_id      UUID REFERENCES qualification_results(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS sentiment           TEXT,
  ADD COLUMN IF NOT EXISTS offer_range_low     NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS offer_range_high    NUMERIC(12,2);

-- ── 4. audit_logs ─────────────────────────────────────────────────────────────
-- Immutable event log for all system actions affecting leads.

CREATE TABLE IF NOT EXISTS audit_logs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type  TEXT NOT NULL,   -- lead | call | appointment | sms | task
  entity_id    TEXT,            -- UUID as text (flexible)
  action       TEXT NOT NULL,   -- created | updated | deleted | status_changed | dnc_added | etc.
  actor        TEXT DEFAULT 'system',  -- user_id | "system" | "ai_agent"
  old_value    JSONB,
  new_value    JSONB,
  metadata     JSONB,
  occurred_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_logs_entity_idx ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS audit_logs_action_idx ON audit_logs(action);
CREATE INDEX IF NOT EXISTS audit_logs_occurred_at_idx ON audit_logs(occurred_at DESC);

-- ── 5. Update funnel_metrics view (new targets: 30k → 6 contracts) ────────────

CREATE OR REPLACE VIEW funnel_metrics AS
SELECT
  -- Lead pool
  COUNT(*)                                              AS total_leads,
  COUNT(*) FILTER (WHERE priority_tier = 'A')           AS tier_a,
  COUNT(*) FILTER (WHERE priority_tier = 'B')           AS tier_b,
  COUNT(*) FILTER (WHERE priority_tier = 'C')           AS tier_c,
  COUNT(*) FILTER (WHERE priority_tier = 'D')           AS tier_d,
  COUNT(*) FILTER (WHERE seller_score >= 70)            AS calling_eligible,

  -- AI Calling funnel
  (SELECT COUNT(*) FROM ai_call_records)                AS total_calls,
  (SELECT COUNT(*) FROM ai_call_records
   WHERE disposition NOT IN ('no_answer','voicemail','unknown','wrong_number'))
                                                        AS conversations,
  (SELECT COUNT(*) FROM ai_call_records
   WHERE disposition IN ('warm','hot','appointment_set','callback'))
                                                        AS interested,
  (SELECT COUNT(*) FROM qualification_results
   WHERE classification = 'WARM')                       AS warm_leads,
  (SELECT COUNT(*) FROM ai_call_records
   WHERE disposition = 'hot')                           AS hot_leads,
  (SELECT COUNT(*) FROM appointments)                   AS appointments,
  (SELECT COUNT(*) FROM appointments
   WHERE status = 'completed')                          AS contracts_closed
FROM leads;

-- ── 6. HOT lead notification helper ──────────────────────────────────────────
-- Trigger that auto-inserts an app_notification when a HOT qualification is recorded.

CREATE OR REPLACE FUNCTION notify_hot_lead()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.classification = 'HOT' AND NEW.lead_id IS NOT NULL THEN
    INSERT INTO app_notifications (
      recipient_role,
      type,
      title,
      body,
      action_url,
      lead_id
    ) VALUES (
      'admin',
      'hot_lead',
      '🔥 HOT Lead — Qualification Complete',
      FORMAT(
        'Qual score: %s | Sentiment: %s | %s',
        NEW.qualification_score,
        COALESCE(NEW.sentiment, 'unknown'),
        COALESCE(NEW.summary, '')
      ),
      '/acquisitions',
      NEW.lead_id
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS qualification_hot_lead_notify ON qualification_results;
CREATE TRIGGER qualification_hot_lead_notify
  AFTER INSERT ON qualification_results
  FOR EACH ROW EXECUTE FUNCTION notify_hot_lead();

-- ── 7. RLS policies ───────────────────────────────────────────────────────────

ALTER TABLE call_transcripts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE qualification_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs            ENABLE ROW LEVEL SECURITY;

CREATE POLICY "approved_read_transcripts"
  ON call_transcripts FOR SELECT TO authenticated USING (is_approved());

CREATE POLICY "approved_write_transcripts"
  ON call_transcripts FOR INSERT TO authenticated WITH CHECK (is_approved());

CREATE POLICY "approved_read_qual_results"
  ON qualification_results FOR SELECT TO authenticated USING (is_approved());

CREATE POLICY "approved_write_qual_results"
  ON qualification_results FOR INSERT TO authenticated WITH CHECK (is_approved());

CREATE POLICY "approved_read_audit_logs"
  ON audit_logs FOR SELECT TO authenticated USING (is_approved());

-- audit_logs: only system (service_role) can insert
CREATE POLICY "service_write_audit_logs"
  ON audit_logs FOR INSERT TO service_role WITH CHECK (true);

-- END 005_call_transcripts.sql

-- ============================================================
-- BEGIN 006_deal_analyzer.sql
-- ============================================================
-- ── Migration 006: Deal Analyzer — precision targeting tables ────────────────
--
-- New tables:
--   priority_scores       — per-lead precision targeting score (distress + stack)
--   deal_analyses         — AI deal analyzer output (ARV, repair, MAO, offer range)
--   repair_estimates      — detailed repair cost breakdown per property
--   offer_recommendations — structured offer + negotiation brief per lead
--
-- Also adds precision_tier and priority_rank columns to leads.

-- ── 1. precision_tier + priority_rank on leads ────────────────────────────────
-- Precision tier maps the PRD conversion bands:
--   Tier 1 = 1 deal / 200–700 records  (highest priority)
--   Tier 2 = 1 deal / 500–1200 records
--   Tier 3 = 1 deal / 2000–4000 records

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS precision_tier    SMALLINT CHECK (precision_tier IN (1, 2, 3)),
  ADD COLUMN IF NOT EXISTS priority_rank     INTEGER,    -- 1 = highest in the batch
  ADD COLUMN IF NOT EXISTS targeting_batch   TEXT,       -- e.g. "2024-Q1-TX-Dallas"
  ADD COLUMN IF NOT EXISTS ai_calling_paused BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS leads_precision_tier_idx ON leads(precision_tier, seller_score DESC);
CREATE INDEX IF NOT EXISTS leads_priority_rank_idx  ON leads(priority_rank)
  WHERE priority_rank IS NOT NULL;

-- ── 2. priority_scores ────────────────────────────────────────────────────────
-- Stores per-lead precision targeting calculation detail.

CREATE TABLE IF NOT EXISTS priority_scores (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id             UUID REFERENCES leads(id) ON DELETE CASCADE,
  base_distress_score INTEGER NOT NULL DEFAULT 0,
  stack_bonus         INTEGER NOT NULL DEFAULT 0,
  total_score         INTEGER GENERATED ALWAYS AS (base_distress_score + stack_bonus) STORED,
  stack_name          TEXT,
  precision_tier      SMALLINT CHECK (precision_tier IN (1, 2, 3)),
  signals_present     TEXT[],
  score_breakdown     JSONB,
  scored_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS priority_scores_lead_id_idx ON priority_scores(lead_id);
CREATE INDEX IF NOT EXISTS priority_scores_total_score_idx ON priority_scores(total_score DESC);

-- ── 3. deal_analyses ──────────────────────────────────────────────────────────
-- AI deal analyzer output — one row per analysis run on a lead.

CREATE TABLE IF NOT EXISTS deal_analyses (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id                 UUID REFERENCES leads(id) ON DELETE SET NULL,

  -- ARV estimate
  arv_low                 NUMERIC(12,2),
  arv_mid                 NUMERIC(12,2),
  arv_high                NUMERIC(12,2),
  arv_confidence          TEXT CHECK (arv_confidence IN ('low','medium','high')),
  arv_comp_count          SMALLINT DEFAULT 0,
  arv_notes               TEXT,

  -- Repair estimate
  repair_tier             TEXT CHECK (repair_tier IN ('light','moderate','heavy','full_gut')),
  repair_tier_label       TEXT,
  repair_sqft             INTEGER,
  repair_cost_low         NUMERIC(12,2),
  repair_cost_mid         NUMERIC(12,2),
  repair_cost_high        NUMERIC(12,2),
  repair_cost_per_sqft_low  NUMERIC(8,2),
  repair_cost_per_sqft_high NUMERIC(8,2),

  -- Cost assumptions
  holding_costs           NUMERIC(12,2),
  closing_costs           NUMERIC(12,2),
  assignment_fee          NUMERIC(12,2) DEFAULT 15000,
  investor_buy_ratio      NUMERIC(5,4)  DEFAULT 0.70,

  -- Key outputs
  mao                     NUMERIC(12,2),
  as_is_value             NUMERIC(12,2),
  offer_range_low         NUMERIC(12,2),
  offer_range_high        NUMERIC(12,2),
  projected_assignment_fee NUMERIC(12,2),
  deal_spread             NUMERIC(12,2),

  -- Strategy
  exit_strategy           TEXT CHECK (exit_strategy IN (
                            'wholesale_assignment','novation_agreement',
                            'wholetail','investor_resale','too_risky'
                          )),
  is_viable               BOOLEAN DEFAULT TRUE,
  weak_deal_reasons       TEXT[],
  summary                 TEXT,

  analyzed_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS deal_analyses_lead_id_idx     ON deal_analyses(lead_id);
CREATE INDEX IF NOT EXISTS deal_analyses_exit_strategy_idx ON deal_analyses(exit_strategy);
CREATE INDEX IF NOT EXISTS deal_analyses_mao_idx         ON deal_analyses(mao DESC)
  WHERE is_viable = TRUE;

-- Convenience: propagate latest analysis values back to leads
CREATE OR REPLACE FUNCTION sync_deal_to_lead()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE leads SET
    estimated_arv   = NEW.arv_low,
    mao             = NEW.mao,
    offer_low       = NEW.offer_range_low,
    offer_high      = NEW.offer_range_high
  WHERE id = NEW.lead_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS deal_analysis_sync ON deal_analyses;
CREATE TRIGGER deal_analysis_sync
  AFTER INSERT OR UPDATE ON deal_analyses
  FOR EACH ROW EXECUTE FUNCTION sync_deal_to_lead();

-- ── 4. repair_estimates ───────────────────────────────────────────────────────
-- Granular line-item repair breakdown (optional detail level).

CREATE TABLE IF NOT EXISTS repair_estimates (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_analysis_id  UUID REFERENCES deal_analyses(id) ON DELETE CASCADE,
  lead_id           UUID REFERENCES leads(id) ON DELETE SET NULL,
  category          TEXT NOT NULL,   -- foundation | roof | hvac | plumbing | cosmetic | etc.
  description       TEXT,
  cost_low          NUMERIC(12,2),
  cost_high         NUMERIC(12,2),
  priority          TEXT DEFAULT 'standard' CHECK (priority IN ('critical','major','standard','cosmetic')),
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS repair_estimates_deal_id_idx ON repair_estimates(deal_analysis_id);
CREATE INDEX IF NOT EXISTS repair_estimates_lead_id_idx ON repair_estimates(lead_id);

-- ── 5. offer_recommendations ─────────────────────────────────────────────────
-- Negotiation intelligence output per lead/call.

CREATE TABLE IF NOT EXISTS offer_recommendations (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id             UUID REFERENCES leads(id) ON DELETE SET NULL,
  deal_analysis_id    UUID REFERENCES deal_analyses(id) ON DELETE SET NULL,
  qual_result_id      UUID REFERENCES qualification_results(id) ON DELETE SET NULL,

  -- Offer structure
  opening_offer       NUMERIC(12,2),
  target_offer        NUMERIC(12,2),
  ceiling_offer       NUMERIC(12,2),      -- = MAO, never exceed
  assignment_fee      NUMERIC(12,2),

  -- Negotiation intelligence
  pain_points         TEXT[],
  motivation_level    TEXT CHECK (motivation_level IN ('low','medium','high','urgent')),
  primary_exit        TEXT,
  secondary_exit      TEXT,
  exit_rationale      TEXT,
  opening_script      TEXT,
  closing_notes       TEXT,
  objection_handlers  JSONB,             -- [{objection, response}, ...]

  generated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS offer_recs_lead_id_idx ON offer_recommendations(lead_id);

-- ── 6. Stack analytics view ───────────────────────────────────────────────────
-- PRD Precision Targeting Dashboard — deals by list stack.

CREATE OR REPLACE VIEW stack_analytics AS
SELECT
  COALESCE(l.stack_name, 'No Stack') AS stack_name,
  COUNT(*)                            AS total_leads,
  COUNT(*) FILTER (
    WHERE l.precision_tier = 1
  )                                   AS tier_1_leads,
  COUNT(*) FILTER (
    WHERE l.status IN ('hot','appointment_set','contract')
  )                                   AS converted_leads,
  ROUND(
    COUNT(*) FILTER (WHERE l.status IN ('hot','appointment_set','contract'))::NUMERIC
    / NULLIF(COUNT(*), 0) * 100, 2
  )                                   AS conversion_pct,
  ROUND(AVG(da.projected_assignment_fee), -3) AS avg_assignment_fee,
  ROUND(AVG(l.seller_score), 1)       AS avg_seller_score
FROM leads l
LEFT JOIN deal_analyses da ON da.lead_id = l.id AND da.is_viable = TRUE
GROUP BY COALESCE(l.stack_name, 'No Stack')
ORDER BY tier_1_leads DESC, total_leads DESC;

-- ── 7. Precision targeting summary view ───────────────────────────────────────

CREATE OR REPLACE VIEW precision_targeting_summary AS
SELECT
  COUNT(*)                                          AS total_imported,
  COUNT(*) FILTER (WHERE l.status = 'suppressed' OR l.status = 'dnc')
                                                    AS total_suppressed,
  COUNT(*) FILTER (WHERE l.precision_tier IS NOT NULL)
                                                    AS total_prioritized,
  COUNT(*) FILTER (WHERE l.precision_tier = 1)      AS tier_1_count,
  COUNT(*) FILTER (WHERE l.precision_tier = 2)      AS tier_2_count,
  COUNT(*) FILTER (WHERE l.precision_tier = 3)      AS tier_3_count,
  COUNT(*) FILTER (WHERE l.priority_rank <= 2000)   AS top_2000_count,
  COUNT(*) FILTER (
    WHERE l.status IN ('hot','appointment_set','contract')
  )                                                 AS total_converted,
  ROUND(AVG(da.projected_assignment_fee) FILTER (
    WHERE da.projected_assignment_fee IS NOT NULL
  ), -3)                                            AS avg_assignment_fee
FROM leads l
LEFT JOIN deal_analyses da ON da.lead_id = l.id AND da.is_viable = TRUE;

-- ── 8. RLS policies ───────────────────────────────────────────────────────────

ALTER TABLE priority_scores       ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_analyses         ENABLE ROW LEVEL SECURITY;
ALTER TABLE repair_estimates      ENABLE ROW LEVEL SECURITY;
ALTER TABLE offer_recommendations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "approved_read_priority_scores"
  ON priority_scores FOR SELECT TO authenticated USING (is_approved());
CREATE POLICY "approved_write_priority_scores"
  ON priority_scores FOR ALL TO authenticated USING (is_approved()) WITH CHECK (is_approved());

CREATE POLICY "approved_read_deal_analyses"
  ON deal_analyses FOR SELECT TO authenticated USING (is_approved());
CREATE POLICY "approved_write_deal_analyses"
  ON deal_analyses FOR ALL TO authenticated USING (is_approved()) WITH CHECK (is_approved());

CREATE POLICY "approved_read_repair_estimates"
  ON repair_estimates FOR SELECT TO authenticated USING (is_approved());
CREATE POLICY "approved_write_repair_estimates"
  ON repair_estimates FOR ALL TO authenticated USING (is_approved()) WITH CHECK (is_approved());

CREATE POLICY "approved_read_offer_recs"
  ON offer_recommendations FOR SELECT TO authenticated USING (is_approved());
CREATE POLICY "approved_write_offer_recs"
  ON offer_recommendations FOR ALL TO authenticated USING (is_approved()) WITH CHECK (is_approved());

-- END 006_deal_analyzer.sql

-- ============================================================
-- BEGIN 007_land_wholesaling.sql
-- ============================================================
-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration 007 — Vacant Land Wholesaling Module
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── LAND LEADS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS land_leads (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW(),

  -- Source linkage
  lead_id               UUID REFERENCES leads(id) ON DELETE SET NULL,  -- optional link to main leads table
  xleads_id             TEXT,                                          -- XLeads record ID for dedup
  source                TEXT DEFAULT 'manual',                         -- xleads | csv_import | manual

  -- Owner info
  owner_name            TEXT NOT NULL,
  owner_phone_1         TEXT,
  owner_phone_2         TEXT,
  owner_mailing_address TEXT,
  owner_email           TEXT,

  -- Property info
  property_address      TEXT NOT NULL,
  city                  TEXT NOT NULL,
  state                 TEXT DEFAULT 'TX',
  zip_code              TEXT,
  county                TEXT,
  apn                   TEXT,                  -- assessor parcel number

  -- Land specifics
  lot_size_acres        NUMERIC(10,4),
  lot_size_sqft         INT,
  zoning                TEXT,                  -- single_family | multifamily | commercial | agricultural | mixed | unknown
  zoning_raw            TEXT,                  -- raw text from county record

  -- Utilities
  water_source          TEXT DEFAULT 'unknown',  -- city | well | none | unknown
  sewage                TEXT DEFAULT 'unknown',  -- city_sewer | septic | none | unknown
  septic_last_pump_date DATE,
  power_available       BOOLEAN,
  power_hookup_possible BOOLEAN,

  -- Buildability
  is_buildable          BOOLEAN,
  buildability_issues   TEXT[],                -- sinkholes | flood_zone | endangered_species | wetlands | easement | other
  flood_zone            TEXT,                  -- AE | X | VE | unknown

  -- Special flags
  infill_lot            BOOLEAN DEFAULT FALSE, -- House-Land-House = premium from builders
  infill_confirmed_at   TIMESTAMPTZ,

  -- Financial
  tav                   NUMERIC(12,2),         -- Tax Assessed Value
  asking_price          NUMERIC(12,2),
  offer_price           NUMERIC(12,2),
  mao                   NUMERIC(12,2),

  -- Status
  status                TEXT DEFAULT 'new',    -- new | vetting | vetted | comped | offer_made | under_contract | dead
  vetting_passed        BOOLEAN,
  assigned_to           UUID,
  internal_notes        TEXT,
  seller_notes          TEXT,

  -- Calling/SMS
  contact_attempts      INT DEFAULT 0,
  last_contact_date     DATE,
  dnc                   BOOLEAN DEFAULT FALSE,
  sms_sequence_active   BOOLEAN DEFAULT FALSE,
  dialer_campaign_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_land_leads_status   ON land_leads(status);
CREATE INDEX IF NOT EXISTS idx_land_leads_zoning   ON land_leads(zoning);
CREATE INDEX IF NOT EXISTS idx_land_leads_infill   ON land_leads(infill_lot) WHERE infill_lot = TRUE;
CREATE INDEX IF NOT EXISTS idx_land_leads_xleads   ON land_leads(xleads_id) WHERE xleads_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_land_leads_zip      ON land_leads(zip_code);

ALTER TABLE land_leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON land_leads FOR ALL USING (auth.role() = 'authenticated');

CREATE TRIGGER land_leads_updated_at
  BEFORE UPDATE ON land_leads
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ─── 7 MUSTS VETTING ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS land_vetting (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW(),
  land_lead_id          UUID NOT NULL REFERENCES land_leads(id) ON DELETE CASCADE,
  vetted_by             UUID,
  started_at            TIMESTAMPTZ DEFAULT NOW(),
  completed_at          TIMESTAMPTZ,

  -- Must #1: Lot Size
  lot_size_confirmed    BOOLEAN,
  lot_size_record       NUMERIC(10,4),   -- what county records say
  lot_size_actual       NUMERIC(10,4),   -- what seller confirmed
  lot_size_notes        TEXT,

  -- Must #2: Zoning
  zoning_confirmed      BOOLEAN,
  zoning_type           TEXT,            -- single_family | multifamily | commercial | agricultural | mixed
  zoning_notes          TEXT,

  -- Must #3: Motivation
  seller_motivation     TEXT,            -- free text from seller call
  motivation_score      INT CHECK (motivation_score BETWEEN 1 AND 5),
  motivation_tag        TEXT,            -- divorce | probate | financial | tired_landlord | inherited | other

  -- Must #4: Water
  water_confirmed       BOOLEAN,
  water_source          TEXT,            -- city | well | none
  water_notes           TEXT,

  -- Must #5: Sewage
  sewage_confirmed      BOOLEAN,
  sewage_type           TEXT,            -- city_sewer | septic | none
  septic_pump_date      DATE,
  sewage_notes          TEXT,

  -- Must #6: Power
  power_confirmed       BOOLEAN,
  power_type            TEXT,            -- connected | hookup_available | none
  power_notes           TEXT,

  -- Must #7: Buildability
  buildability_confirmed BOOLEAN,
  can_build             BOOLEAN,
  buildability_issues   TEXT[],
  buildability_notes    TEXT,

  -- Overall result
  passed                BOOLEAN,
  fail_reasons          TEXT[],
  recommendation        TEXT
);

ALTER TABLE land_vetting ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON land_vetting FOR ALL USING (auth.role() = 'authenticated');

CREATE TRIGGER land_vetting_updated_at
  BEFORE UPDATE ON land_vetting
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ─── LAND COMPS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS land_comps (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  land_lead_id          UUID NOT NULL REFERENCES land_leads(id) ON DELETE CASCADE,
  comped_by             UUID,

  -- Method 1: Direct land comps
  direct_comp_avg       NUMERIC(12,2),
  direct_comp_count     INT,
  direct_comp_low       NUMERIC(12,2),
  direct_comp_high      NUMERIC(12,2),
  direct_comp_details   JSONB,           -- array of {address, price, sqft, date, distance_mi}

  -- Method 2: 15% Rule (15% of avg house ARV in 0.5mi)
  avg_house_arv         NUMERIC(12,2),
  arv_15pct_value       NUMERIC(12,2),   -- avg_house_arv * 0.15
  house_comp_count      INT,
  house_comp_radius_mi  NUMERIC(4,2) DEFAULT 0.5,

  -- Method 3: Tax value
  tav                   NUMERIC(12,2),
  tav_source            TEXT,            -- county | xleads | manual

  -- Recommended offer
  recommended_offer_low  NUMERIC(12,2),
  recommended_offer_high NUMERIC(12,2),
  comp_notes            TEXT
);

ALTER TABLE land_comps ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON land_comps FOR ALL USING (auth.role() = 'authenticated');


-- ─── EXTEND BUYERS TABLE — land buyer type ────────────────────────────────────
ALTER TABLE buyers
  ADD COLUMN IF NOT EXISTS buyer_type        TEXT DEFAULT 'traditional',
  ADD COLUMN IF NOT EXISTS land_buyer_type   TEXT,   -- builder | land_banker | trailer_park | mineral_rights
  ADD COLUMN IF NOT EXISTS target_acres_min  NUMERIC(10,4),
  ADD COLUMN IF NOT EXISTS target_acres_max  NUMERIC(10,4),
  ADD COLUMN IF NOT EXISTS preferred_zoning  TEXT[],
  ADD COLUMN IF NOT EXISTS buys_land         BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS buys_infill       BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_buyers_land_type ON buyers(land_buyer_type) WHERE land_buyer_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_buyers_buys_land  ON buyers(buys_land) WHERE buys_land = TRUE;


-- ─── LAND IMPORT LOG ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS land_import_log (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  imported_by   UUID,
  source        TEXT NOT NULL,    -- xleads_csv | xleads_api | manual
  file_name     TEXT,
  total_rows    INT,
  imported      INT,
  skipped       INT,
  errors        INT,
  error_details JSONB
);

ALTER TABLE land_import_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON land_import_log FOR ALL USING (auth.role() = 'authenticated');


-- ─── VIEWS ────────────────────────────────────────────────────────────────────

-- Land funnel summary
CREATE OR REPLACE VIEW land_funnel AS
SELECT
  COUNT(*) FILTER (WHERE status = 'new')             AS new_leads,
  COUNT(*) FILTER (WHERE status = 'vetting')         AS in_vetting,
  COUNT(*) FILTER (WHERE vetting_passed = TRUE)      AS vetting_passed,
  COUNT(*) FILTER (WHERE status = 'comped')          AS comped,
  COUNT(*) FILTER (WHERE status = 'offer_made')      AS offers_made,
  COUNT(*) FILTER (WHERE status = 'under_contract')  AS under_contract,
  COUNT(*) FILTER (WHERE infill_lot = TRUE)          AS infill_lots,
  COUNT(*) FILTER (WHERE status = 'dead')            AS dead
FROM land_leads;

-- Infill lot pipeline
CREATE OR REPLACE VIEW infill_pipeline AS
SELECT
  ll.id, ll.property_address, ll.city, ll.zip_code,
  ll.lot_size_acres, ll.zoning, ll.tav,
  ll.offer_price, ll.status, ll.infill_confirmed_at,
  lc.direct_comp_avg, lc.arv_15pct_value, lc.recommended_offer_high
FROM land_leads ll
LEFT JOIN land_comps lc ON lc.land_lead_id = ll.id
WHERE ll.infill_lot = TRUE
ORDER BY ll.created_at DESC;

-- END 007_land_wholesaling.sql

-- ============================================================
-- BEGIN 008_buyer_intelligence.sql
-- ============================================================
-- ============================================================
-- 008_buyer_intelligence.sql
-- Investor Buyer Intelligence Engine (IBIE)
--
-- Extends buyers table with automated scoring/classification fields.
-- Adds tables for:
--   buyer_transactions   — purchase history per buyer (county records)
--   buyer_preferences    — detailed deal targeting preferences
--   buyer_import_log     — CSV/API import audit
--   deal_matches         — deal-to-buyer match results (ranked)
--   buyer_outreach_log   — SMS/email outreach sent to buyer
-- ============================================================

-- ── Extend buyers table ───────────────────────────────────────────────────────

ALTER TABLE buyers
  -- Entity info
  ADD COLUMN IF NOT EXISTS entity_name       TEXT,           -- LLC / INC name
  ADD COLUMN IF NOT EXISTS market            TEXT,           -- DFW | Houston | etc.

  -- IBIE computed fields
  ADD COLUMN IF NOT EXISTS ibie_score        NUMERIC(5,2) DEFAULT 0,   -- 0–100
  ADD COLUMN IF NOT EXISTS ibie_tier         TEXT DEFAULT 'D',         -- A | B | C | D
  ADD COLUMN IF NOT EXISTS buyer_type_ibie   TEXT,          -- flipper | landlord | institutional | builder
  ADD COLUMN IF NOT EXISTS ai_classified_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS tags              TEXT[] DEFAULT '{}',

  -- Transaction-derived signals
  ADD COLUMN IF NOT EXISTS cash_buyer             BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS repeat_buyer           BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS total_purchases_12mo   INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS properties_owned       INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS avg_purchase_price     NUMERIC(12,2),
  ADD COLUMN IF NOT EXISTS last_purchase_date     DATE,
  ADD COLUMN IF NOT EXISTS lender_used            TEXT,

  -- Engagement scoring adjustment (increases on response/close, decreases on ignore)
  ADD COLUMN IF NOT EXISTS engagement_delta       NUMERIC(5,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS outreach_ignore_count  INT     DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_scored_at         TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS score_version          INT     DEFAULT 0;


-- ── buyer_transactions ────────────────────────────────────────────────────────
-- Stores individual property purchase records per buyer
-- (sourced from county deed records, PropStream, or manual CSV)

CREATE TABLE IF NOT EXISTS buyer_transactions (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  buyer_id         UUID NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,

  property_address TEXT NOT NULL,
  city             TEXT,
  state            TEXT DEFAULT 'TX',
  zip_code         TEXT,
  county           TEXT,

  purchase_price   NUMERIC(12,2),
  purchase_date    DATE,
  cash_transaction BOOLEAN DEFAULT FALSE,
  lender_name      TEXT,
  loan_amount      NUMERIC(12,2),

  property_type    TEXT,          -- SFR | MFR | land | condo | commercial
  sqft             INT,
  bedrooms         INT,
  bathrooms        NUMERIC(3,1),
  year_built       INT,

  -- Flip detection: if re-sold within 18 months
  resale_date      DATE,
  resale_price     NUMERIC(12,2),
  flip_detected    BOOLEAN DEFAULT FALSE,

  -- Identifiers
  apn              TEXT,          -- assessor parcel number (dedup key)
  deed_book        TEXT,
  deed_page        TEXT,
  grantor          TEXT,          -- seller name on deed
  grantee          TEXT,          -- buyer name on deed

  source           TEXT DEFAULT 'csv',  -- csv | propstream | county_api | manual
  raw_data         JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_buyer_tx_apn_buyer
  ON buyer_transactions (buyer_id, apn)
  WHERE apn IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_buyer_tx_buyer_id ON buyer_transactions (buyer_id);
CREATE INDEX IF NOT EXISTS idx_buyer_tx_zip      ON buyer_transactions (zip_code);
CREATE INDEX IF NOT EXISTS idx_buyer_tx_date     ON buyer_transactions (purchase_date DESC NULLS LAST);


-- ── buyer_preferences ─────────────────────────────────────────────────────────
-- Detailed deal-targeting preferences per buyer (one row per buyer)

CREATE TABLE IF NOT EXISTS buyer_preferences (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  buyer_id         UUID NOT NULL UNIQUE REFERENCES buyers(id) ON DELETE CASCADE,

  -- Price range
  min_price        NUMERIC(12,2),
  max_price        NUMERIC(12,2),

  -- Property targeting
  preferred_property_types TEXT[] DEFAULT '{}',   -- SFR | MFR | land | condo
  preferred_condition      TEXT DEFAULT 'any',    -- distressed | cosmetic | turnkey | any
  preferred_zips           TEXT[] DEFAULT '{}',
  preferred_counties       TEXT[] DEFAULT '{}',

  -- Deal structure
  target_roi               NUMERIC(5,2),           -- target ROI %
  max_days_to_close        INT,
  requires_seller_finance   BOOLEAN DEFAULT FALSE,
  requires_subject_to      BOOLEAN DEFAULT FALSE,
  pays_above_market        BOOLEAN DEFAULT FALSE,   -- institutional flag

  -- Communication prefs
  contact_method           TEXT DEFAULT 'sms',     -- sms | email | phone | any
  preferred_contact_time   TEXT,                   -- morning | afternoon | evening
  do_not_contact_before    TIME,
  do_not_contact_after     TIME,

  notes                    TEXT
);

CREATE TRIGGER update_buyer_preferences_updated_at
  BEFORE UPDATE ON buyer_preferences
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ── buyer_import_log ──────────────────────────────────────────────────────────
-- Audit trail for every CSV / API import

CREATE TABLE IF NOT EXISTS buyer_import_log (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  imported_by      UUID REFERENCES auth.users(id),

  source           TEXT NOT NULL,     -- county_csv | propstream_csv | manual | api
  filename         TEXT,
  market           TEXT,

  rows_total       INT DEFAULT 0,
  rows_imported    INT DEFAULT 0,
  buyers_created   INT DEFAULT 0,
  buyers_updated   INT DEFAULT 0,
  transactions_created INT DEFAULT 0,
  rows_skipped     INT DEFAULT 0,
  errors           JSONB DEFAULT '[]',

  status           TEXT DEFAULT 'pending',   -- pending | processing | complete | failed
  completed_at     TIMESTAMPTZ
);


-- ── deal_matches ──────────────────────────────────────────────────────────────
-- Stores the result of each deal-matching run
-- (top 50 buyers ranked per deal, with match factors)

CREATE TABLE IF NOT EXISTS deal_matches (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  deal_id          UUID REFERENCES deals(id) ON DELETE CASCADE,
  buyer_id         UUID NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,

  -- Match factors (each 0–100)
  zip_score        NUMERIC(5,2) DEFAULT 0,
  price_score      NUMERIC(5,2) DEFAULT 0,
  type_score       NUMERIC(5,2) DEFAULT 0,
  ibie_score       NUMERIC(5,2) DEFAULT 0,   -- buyer's ibie_score at match time

  -- Combined rank score
  match_score      NUMERIC(5,2) DEFAULT 0,
  rank             INT,

  -- Outreach status
  sms_sent_at      TIMESTAMPTZ,
  email_sent_at    TIMESTAMPTZ,
  responded_at     TIMESTAMPTZ,
  response_type    TEXT,   -- interested | not_interested | callback | closed

  UNIQUE (deal_id, buyer_id)
);

CREATE INDEX IF NOT EXISTS idx_deal_matches_deal   ON deal_matches (deal_id);
CREATE INDEX IF NOT EXISTS idx_deal_matches_buyer  ON deal_matches (buyer_id);
CREATE INDEX IF NOT EXISTS idx_deal_matches_score  ON deal_matches (match_score DESC);


-- ── buyer_outreach_log ────────────────────────────────────────────────────────
-- Every SMS / email sent to a buyer (deal blasts + manual)

CREATE TABLE IF NOT EXISTS buyer_outreach_log (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  buyer_id         UUID NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,
  deal_id          UUID REFERENCES deals(id) ON DELETE SET NULL,
  deal_match_id    UUID REFERENCES deal_matches(id) ON DELETE SET NULL,

  channel          TEXT NOT NULL,    -- sms | email
  direction        TEXT DEFAULT 'outbound',
  status           TEXT DEFAULT 'queued',   -- queued | sent | delivered | failed | replied
  subject          TEXT,
  body             TEXT NOT NULL,
  to_address       TEXT NOT NULL,   -- phone or email address
  provider         TEXT,            -- twilio | sendgrid
  provider_msg_id  TEXT,

  opened_at        TIMESTAMPTZ,
  replied_at       TIMESTAMPTZ,
  reply_body       TEXT,

  sent_by          UUID REFERENCES auth.users(id)
);

CREATE INDEX IF NOT EXISTS idx_buyer_outreach_buyer ON buyer_outreach_log (buyer_id);
CREATE INDEX IF NOT EXISTS idx_buyer_outreach_deal  ON buyer_outreach_log (deal_id);


-- ── Views ─────────────────────────────────────────────────────────────────────

-- Top buyers leaderboard (used by BuyerIntelligence page)
CREATE OR REPLACE VIEW buyer_leaderboard AS
SELECT
  b.id,
  b.first_name,
  b.last_name,
  b.company,
  b.entity_name,
  b.email,
  b.phone,
  b.market,
  b.buyer_type_ibie,
  b.ibie_score,
  b.ibie_tier,
  b.cash_buyer,
  b.repeat_buyer,
  b.total_purchases_12mo,
  b.properties_owned,
  b.avg_purchase_price,
  b.last_purchase_date,
  b.tags,
  b.deals_closed,
  b.pof_verified,
  b.pof_amount,
  b.target_zips,
  b.min_price,
  b.max_price,
  b.tier           AS crm_tier,
  b.active,
  b.sms_opt_in,
  b.email_opt_in,
  b.outreach_ignore_count,
  b.last_scored_at,
  b.created_at,
  COUNT(DISTINCT bt.id)::INT AS transaction_count,
  MAX(bt.purchase_date)       AS most_recent_purchase
FROM buyers b
LEFT JOIN buyer_transactions bt ON bt.buyer_id = b.id
WHERE b.active = TRUE
GROUP BY b.id
ORDER BY b.ibie_score DESC NULLS LAST;


-- IBIE segment summary (dashboard KPI strip)
CREATE OR REPLACE VIEW ibie_segment_summary AS
SELECT
  ibie_tier,
  buyer_type_ibie,
  COUNT(*)::INT                          AS buyer_count,
  ROUND(AVG(ibie_score), 1)              AS avg_score,
  COUNT(*) FILTER (WHERE cash_buyer)::INT AS cash_buyer_count,
  COUNT(*) FILTER (WHERE repeat_buyer)::INT AS repeat_buyer_count,
  ROUND(AVG(total_purchases_12mo), 1)    AS avg_purchases_12mo,
  ROUND(AVG(avg_purchase_price))         AS avg_buy_price
FROM buyers
WHERE active = TRUE
GROUP BY ibie_tier, buyer_type_ibie;


-- ── RLS policies ─────────────────────────────────────────────────────────────

ALTER TABLE buyer_transactions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE buyer_preferences    ENABLE ROW LEVEL SECURITY;
ALTER TABLE buyer_import_log     ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_matches         ENABLE ROW LEVEL SECURITY;
ALTER TABLE buyer_outreach_log   ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated_full_access" ON buyer_transactions   FOR ALL TO authenticated USING (TRUE);
CREATE POLICY "authenticated_full_access" ON buyer_preferences    FOR ALL TO authenticated USING (TRUE);
CREATE POLICY "authenticated_full_access" ON buyer_import_log     FOR ALL TO authenticated USING (TRUE);
CREATE POLICY "authenticated_full_access" ON deal_matches         FOR ALL TO authenticated USING (TRUE);
CREATE POLICY "authenticated_full_access" ON buyer_outreach_log   FOR ALL TO authenticated USING (TRUE);

-- END 008_buyer_intelligence.sql

-- ============================================================
-- BEGIN 009_lead_generation.sql
-- ============================================================
-- ============================================================
-- Migration 009: Facebook / Social Media Lead Generation Engine
-- ============================================================
-- Tables: ad_campaigns, ad_creatives, lead_form_configs, lead_form_submissions
-- ALTER leads: add ad_campaign_id, ad_creative_id, form_submission_id, inbound_channel
-- ============================================================

-- Ad Campaigns (Facebook, Instagram, Google, TikTok)
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),
    name                    TEXT NOT NULL,
    platform                TEXT DEFAULT 'facebook',           -- facebook | instagram | google | tiktok
    status                  TEXT DEFAULT 'active',             -- active | paused | completed | draft
    campaign_objective      TEXT,                              -- lead_generation | awareness | conversions
    external_campaign_id    TEXT,                              -- Facebook campaign ID
    daily_budget            NUMERIC(10,2),
    total_spend             NUMERIC(10,2) DEFAULT 0,
    impressions             INT DEFAULT 0,
    clicks                  INT DEFAULT 0,
    leads_count             INT DEFAULT 0,
    cpl                     NUMERIC(10,2) GENERATED ALWAYS AS (
                                CASE WHEN leads_count > 0 THEN total_spend / leads_count ELSE NULL END
                            ) STORED,
    avg_lead_quality_score  NUMERIC(5,2),
    target_zip_codes        TEXT[],
    target_audience_notes   TEXT,
    start_date              DATE,
    end_date                DATE,
    settings                JSONB DEFAULT '{}'::JSONB
);

-- Ad Creatives (individual variants being A/B tested)
CREATE TABLE IF NOT EXISTS ad_creatives (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),
    campaign_id             UUID REFERENCES ad_campaigns(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,
    headline                TEXT,                              -- "We Buy Houses Fast"
    primary_text            TEXT,                             -- body copy
    cta_text                TEXT DEFAULT 'Get My Cash Offer',
    pain_point_angle        TEXT,                             -- foreclosure | divorce | inheritance | tired_landlord | relocation | repairs | generic
    image_url               TEXT,
    external_ad_id          TEXT,                             -- Facebook ad ID
    status                  TEXT DEFAULT 'active',            -- active | paused | winner | archived
    impressions             INT DEFAULT 0,
    clicks                  INT DEFAULT 0,
    leads_count             INT DEFAULT 0,
    cpl                     NUMERIC(10,2) GENERATED ALWAYS AS (
                                CASE WHEN leads_count > 0 THEN total_spend / leads_count ELSE NULL END
                            ) STORED,
    total_spend             NUMERIC(10,2) DEFAULT 0,
    avg_lead_quality_score  NUMERIC(5,2),
    is_winner               BOOLEAN DEFAULT FALSE
);

-- Lead Form Configurations (multi-step qualification forms)
CREATE TABLE IF NOT EXISTS lead_form_configs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),
    name                    TEXT NOT NULL,
    slug                    TEXT UNIQUE NOT NULL,              -- URL-friendly ID for /form/:slug
    campaign_id             UUID REFERENCES ad_campaigns(id),
    headline                TEXT DEFAULT 'Get a Fair Cash Offer',
    subheadline             TEXT DEFAULT 'Fill out the form below and we''ll get back to you within minutes.',
    brand_color             TEXT DEFAULT '#1B3A5C',
    logo_url                TEXT,
    thank_you_message       TEXT DEFAULT 'Thank you! We''ll be in touch within minutes with your cash offer.',
    send_confirmation_sms   BOOLEAN DEFAULT TRUE,
    send_confirmation_email BOOLEAN DEFAULT FALSE,
    active                  BOOLEAN DEFAULT TRUE,
    questions               JSONB DEFAULT '[]'::JSONB,         -- ordered question config array
    redirect_url            TEXT
);

-- Lead Form Submissions (raw answers before lead creation)
CREATE TABLE IF NOT EXISTS lead_form_submissions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    form_id                 UUID REFERENCES lead_form_configs(id),
    lead_id                 UUID REFERENCES leads(id),
    ip_address              TEXT,
    user_agent              TEXT,
    utm_source              TEXT,
    utm_medium              TEXT,
    utm_campaign            TEXT,
    raw_answers             JSONB NOT NULL DEFAULT '{}'::JSONB,
    computed_motivation_tag TEXT,
    computed_timeline       TEXT,
    computed_condition      TEXT,
    processing_status       TEXT DEFAULT 'pending'            -- pending | processed | failed
);

-- ALTER leads: link back to ad source
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS ad_campaign_id     UUID REFERENCES ad_campaigns(id),
    ADD COLUMN IF NOT EXISTS ad_creative_id     UUID REFERENCES ad_creatives(id),
    ADD COLUMN IF NOT EXISTS form_submission_id UUID REFERENCES lead_form_submissions(id),
    ADD COLUMN IF NOT EXISTS inbound_channel    TEXT;         -- facebook_lead_ad | web_form | phone | referral

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ad_creatives_campaign ON ad_creatives(campaign_id);
CREATE INDEX IF NOT EXISTS idx_lead_form_submissions_form ON lead_form_submissions(form_id);
CREATE INDEX IF NOT EXISTS idx_lead_form_submissions_lead ON lead_form_submissions(lead_id);
CREATE INDEX IF NOT EXISTS idx_leads_ad_campaign ON leads(ad_campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_inbound_channel ON leads(inbound_channel);

-- Updated_at triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ad_campaigns_updated_at') THEN
        CREATE TRIGGER update_ad_campaigns_updated_at
            BEFORE UPDATE ON ad_campaigns FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_ad_creatives_updated_at') THEN
        CREATE TRIGGER update_ad_creatives_updated_at
            BEFORE UPDATE ON ad_creatives FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_lead_form_configs_updated_at') THEN
        CREATE TRIGGER update_lead_form_configs_updated_at
            BEFORE UPDATE ON lead_form_configs FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- RLS
ALTER TABLE ad_campaigns         ENABLE ROW LEVEL SECURITY;
ALTER TABLE ad_creatives         ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_form_configs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_form_submissions ENABLE ROW LEVEL SECURITY;

-- Authenticated users can read/write ad tables
CREATE POLICY "auth_all_ad_campaigns"
    ON ad_campaigns FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_all_ad_creatives"
    ON ad_creatives FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_all_lead_form_configs"
    ON lead_form_configs FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_all_lead_form_submissions"
    ON lead_form_submissions FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);

-- Public can READ active form configs (for the embedded form page)
CREATE POLICY "public_read_active_forms"
    ON lead_form_configs FOR SELECT TO anon USING (active = TRUE);
-- Public can INSERT submissions (anon form submitters)
CREATE POLICY "public_insert_submissions"
    ON lead_form_submissions FOR INSERT TO anon WITH CHECK (TRUE);

-- Default form config with all 4 steps (seeded once)
INSERT INTO lead_form_configs (
    name, slug, headline, subheadline, thank_you_message,
    send_confirmation_sms, active,
    questions
) VALUES (
    'DFW Motivated Seller Form',
    'dfw-motivated-seller',
    'Get a Fair Cash Offer for Your House',
    'No repairs. No fees. Close on your timeline. Tell us about your property.',
    'We''ve received your information! Our team will call you within minutes with a fair cash offer.',
    TRUE, TRUE,
    '[
        {"id":"step1_address","step":1,"type":"text","field_name":"property_address","label":"What is the property address?","placeholder":"123 Main St, Dallas, TX","required":true},
        {"id":"step1_first_name","step":1,"type":"text","field_name":"first_name","label":"Your First Name","required":true},
        {"id":"step1_last_name","step":1,"type":"text","field_name":"last_name","label":"Your Last Name","required":false},
        {"id":"step1_phone","step":1,"type":"tel","field_name":"phone","label":"Best Phone Number","required":true},
        {"id":"step1_email","step":1,"type":"email","field_name":"email","label":"Email (optional)","required":false},
        {"id":"step2_motivation","step":2,"type":"radio","field_name":"motivation","label":"Why are you looking to sell?","required":true,"options":[
            {"value":"foreclosure","label":"Behind on payments / facing foreclosure","score_hint":3},
            {"value":"divorce","label":"Going through a divorce","score_hint":3},
            {"value":"inherited","label":"Inherited the property","score_hint":3},
            {"value":"tired_landlord","label":"Tired of being a landlord","score_hint":3},
            {"value":"relocation","label":"Need to relocate","score_hint":2},
            {"value":"repairs","label":"Property needs too many repairs","score_hint":2},
            {"value":"other","label":"Other reason","score_hint":1}
        ]},
        {"id":"step2_timeline","step":2,"type":"radio","field_name":"timeline","label":"When do you need to close?","required":true,"options":[
            {"value":"asap","label":"As soon as possible (30 days or less)","score_hint":3},
            {"value":"1_3mo","label":"1–3 months","score_hint":2},
            {"value":"3_6mo","label":"3–6 months","score_hint":1},
            {"value":"flexible","label":"No rush / flexible","score_hint":1}
        ]},
        {"id":"step3_condition","step":3,"type":"radio","field_name":"condition","label":"What condition is the property in?","required":true,"options":[
            {"value":"major_repairs","label":"Needs major repairs (roof, foundation, etc.)","score_hint":3},
            {"value":"cosmetic","label":"Needs cosmetic work (paint, flooring, etc.)","score_hint":2},
            {"value":"good","label":"Move-in ready / good condition","score_hint":1}
        ]},
        {"id":"step3_occupancy","step":3,"type":"radio","field_name":"occupancy","label":"Is the property currently occupied?","required":true,"options":[
            {"value":"owner","label":"Yes, I live there","score_hint":0},
            {"value":"tenant","label":"Yes, tenant occupied","score_hint":0},
            {"value":"vacant","label":"No, it is vacant","score_hint":1}
        ]},
        {"id":"step4_asking_price","step":4,"type":"number","field_name":"asking_price","label":"Do you have a price in mind? (optional)","placeholder":"Leave blank if unsure","required":false},
        {"id":"step4_sms_opt_in","step":4,"type":"checkbox","field_name":"sms_opt_in","label":"I agree to receive a text message with my offer details","required":false}
    ]'::JSONB
) ON CONFLICT (slug) DO NOTHING;

-- END 009_lead_generation.sql

-- ============================================================
-- BEGIN 010_fb_ads_command_center.sql
-- ============================================================
-- ============================================================
-- Migration 010: Facebook Ads Command Center
-- ============================================================

-- Campaigns table
CREATE TABLE IF NOT EXISTS fb_campaigns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    name                TEXT NOT NULL,
    status              TEXT DEFAULT 'draft',          -- draft | active | paused
    objective           TEXT DEFAULT 'LEAD_GENERATION',-- locked
    special_ad_category BOOLEAN DEFAULT TRUE,          -- locked ON
    ab_test_enabled     BOOLEAN DEFAULT TRUE,
    daily_budget        NUMERIC(10,2) DEFAULT 25.00,
    start_date          DATE,
    battle_plan_score   NUMERIC(5,2),
    wizard_step         INT DEFAULT 1,                 -- last completed step (1-6)
    wizard_state        JSONB DEFAULT '{}'::JSONB       -- full wizard draft state
);

-- Ad sets table
CREATE TABLE IF NOT EXISTS fb_ad_sets (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    campaign_id           UUID REFERENCES fb_campaigns(id) ON DELETE CASCADE,
    segment               TEXT,  -- pre-foreclosure|probate|divorce|tax|landlord|vacant|senior|high-equity
    audience_type         TEXT DEFAULT 'custom',  -- custom|interest|lookalike
    audience_size         INT DEFAULT 0,
    headline              TEXT,
    copy_version_a        TEXT,
    copy_version_b        TEXT,
    copy_version_c        TEXT,
    active_copy_version   TEXT DEFAULT 'A',
    placement_feed        BOOLEAN DEFAULT TRUE,
    placement_marketplace BOOLEAN DEFAULT TRUE,
    placement_instagram   BOOLEAN DEFAULT TRUE,
    placement_audience_network BOOLEAN DEFAULT FALSE,  -- locked OFF
    daily_budget          NUMERIC(10,2),
    tier1_signals         TEXT[],
    tier2_signals         TEXT[],
    tier3_signals         TEXT[],
    county                TEXT[]
);

-- Custom audiences table
CREATE TABLE IF NOT EXISTS fb_custom_audiences (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    ad_set_id     UUID REFERENCES fb_ad_sets(id) ON DELETE CASCADE,
    campaign_id   UUID REFERENCES fb_campaigns(id) ON DELETE CASCADE,
    audience_name TEXT NOT NULL,
    audience_type TEXT NOT NULL,  -- pre-foreclosure|probate|tax-delinquent|etc
    record_count  INT DEFAULT 0,
    county        TEXT,
    file_url      TEXT,
    priority      TEXT DEFAULT 'yellow'  -- red|orange|yellow
);

-- Facebook leads table
CREATE TABLE IF NOT EXISTS fb_leads (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at        TIMESTAMPTZ DEFAULT NOW(),
    campaign_id        UUID REFERENCES fb_campaigns(id),
    ad_set_id          UUID REFERENCES fb_ad_sets(id),
    name               TEXT,
    phone              TEXT,
    email              TEXT,
    property_address   TEXT,
    condition          TEXT,
    situations         TEXT[],
    timeline           TEXT,
    contact_preference TEXT,
    segment_tag        TEXT,  -- HOT-URGENT|HOT-ESTATE|HOT-LEGAL|WARM-LANDLORD|WARM-RELOCATION|COLD-NURTURE
    twilio_sms_sent    BOOLEAN DEFAULT FALSE,
    twilio_sms_time    TIMESTAMPTZ,
    contacted          BOOLEAN DEFAULT FALSE,
    appointment_set    BOOLEAN DEFAULT FALSE,
    -- link to main leads table after routing
    lead_id            UUID REFERENCES leads(id)
);

-- Campaign performance snapshots (daily)
CREATE TABLE IF NOT EXISTS fb_campaign_performance (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id  UUID REFERENCES fb_campaigns(id) ON DELETE CASCADE,
    ad_set_id    UUID REFERENCES fb_ad_sets(id),
    date         DATE NOT NULL,
    spend        NUMERIC(10,2) DEFAULT 0,
    leads        INT DEFAULT 0,
    cpl          NUMERIC(10,2) GENERATED ALWAYS AS (
                     CASE WHEN leads > 0 THEN spend / leads ELSE NULL END
                 ) STORED,
    contact_rate NUMERIC(5,2) DEFAULT 0,  -- percentage
    appt_rate    NUMERIC(5,2) DEFAULT 0,
    frequency    NUMERIC(5,2) DEFAULT 0,
    UNIQUE(campaign_id, ad_set_id, date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_fb_ad_sets_campaign ON fb_ad_sets(campaign_id);
CREATE INDEX IF NOT EXISTS idx_fb_custom_audiences_campaign ON fb_custom_audiences(campaign_id);
CREATE INDEX IF NOT EXISTS idx_fb_leads_campaign ON fb_leads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_fb_leads_segment ON fb_leads(segment_tag);
CREATE INDEX IF NOT EXISTS idx_fb_leads_received ON fb_leads(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_fb_perf_campaign ON fb_campaign_performance(campaign_id, date DESC);

-- Updated_at trigger (reuse existing function)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_fb_campaigns_updated_at') THEN
        CREATE TRIGGER update_fb_campaigns_updated_at
            BEFORE UPDATE ON fb_campaigns FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- RLS
ALTER TABLE fb_campaigns          ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_ad_sets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_custom_audiences   ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_leads              ENABLE ROW LEVEL SECURITY;
ALTER TABLE fb_campaign_performance ENABLE ROW LEVEL SECURITY;

CREATE POLICY "auth_fb_campaigns"       ON fb_campaigns FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_fb_ad_sets"         ON fb_ad_sets FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_fb_audiences"       ON fb_custom_audiences FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_fb_leads"           ON fb_leads FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);
CREATE POLICY "auth_fb_perf"            ON fb_campaign_performance FOR ALL TO authenticated USING (TRUE) WITH CHECK (TRUE);

-- Anon insert for webhook-received leads (edge function uses service role, but anon fallback)
CREATE POLICY "anon_insert_fb_leads"    ON fb_leads FOR INSERT TO anon WITH CHECK (TRUE);

-- END 010_fb_ads_command_center.sql

-- ============================================================
-- BEGIN 013_webhook_jobs.sql
-- ============================================================
-- ─────────────────────────────────────────────────────────────────────────────
-- 013_webhook_jobs.sql — durable async queue for serverless (Vercel) webhooks
--
-- Why: On Vercel the FastAPI function is frozen the instant it returns a
-- response, so FastAPI BackgroundTasks (and any fire-and-forget asyncio task)
-- never finish. Inbound webhooks therefore enqueue a row here and return 200
-- immediately; a Vercel Cron hits POST /webhooks/_worker/drain once a minute to
-- process pending rows by replaying them through the existing handlers.
--
-- Standalone — does NOT depend on migrations 011/012 (RealtyAPI). Safe to apply
-- on its own.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS webhook_jobs (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  source       TEXT        NOT NULL,            -- batchdialer | launch_control | retell | retell_call | air_ai | vapi | facebook
  payload      JSONB       NOT NULL,            -- raw provider payload, replayed by the worker
  status       TEXT        NOT NULL DEFAULT 'pending',  -- pending | processing | done | failed
  attempts     INT         NOT NULL DEFAULT 0,
  last_error   TEXT,
  processed_at TIMESTAMPTZ
);

-- Drain query: oldest pending first.
CREATE INDEX IF NOT EXISTS idx_webhook_jobs_status_created
  ON webhook_jobs (status, created_at);

-- Service-role only. The webhook function authenticates with the Supabase
-- service-role key (which bypasses RLS); enabling RLS with no public policy
-- keeps the queue invisible to anon/authenticated browser clients.
ALTER TABLE webhook_jobs ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE webhook_jobs IS
  'Durable queue for inbound provider webhooks under serverless (Vercel) hosting. Drained by POST /webhooks/_worker/drain via Vercel Cron.';

-- END 013_webhook_jobs.sql
