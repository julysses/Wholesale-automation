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
