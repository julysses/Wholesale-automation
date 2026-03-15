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
