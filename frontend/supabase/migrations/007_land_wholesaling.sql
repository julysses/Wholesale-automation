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
