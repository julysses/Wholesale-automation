-- ── Migration 011: RealtyAPI.io Integration ──────────────────────────────────
--
-- New tables:
--   property_enrichment  — Zillow/Realtor.com property detail per lead
--   arv_results          — Claude-computed ARV range per lead
--   rental_yield         — LTR + STR yield data per lead
--   market_pulse         — Weekly zip-level DFW market intelligence
--
-- Altered tables:
--   leads   — deal_score, tags, motivation_score, priority, list_price
--   comps   — similarity_score, raw_payload, fetched_at
--
-- Trigger:
--   enrich_lead_on_insert — fires enrich-property edge function after lead INSERT
--
-- Cron jobs (pg_cron):
--   motivated-seller-scan — Sunday 6AM CST (12:00 UTC)
--   market-pulse          — Sunday 7AM CST (13:00 UTC)
--
-- Prerequisites:
--   After running this migration, execute in SQL editor:
--     ALTER DATABASE postgres SET app.supabase_url  = 'https://YOUR-PROJECT.supabase.co';
--     ALTER DATABASE postgres SET app.supabase_anon_key = 'YOUR_ANON_KEY';
--   These are needed by the pg_net trigger and cron HTTP calls.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_net;

-- ── 1. Alter leads table ──────────────────────────────────────────────────────
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS deal_score       INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tags             TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS motivation_score INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS priority         BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS list_price       BIGINT;

CREATE INDEX IF NOT EXISTS leads_tags_idx    ON leads USING GIN(tags);
CREATE INDEX IF NOT EXISTS leads_priority_idx ON leads(priority) WHERE priority = TRUE;

-- ── 2. Alter comps table ──────────────────────────────────────────────────────
ALTER TABLE comps
  ADD COLUMN IF NOT EXISTS similarity_score NUMERIC(5,2),
  ADD COLUMN IF NOT EXISTS raw_payload      JSONB,
  ADD COLUMN IF NOT EXISTS fetched_at       TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS comps_similarity_idx ON comps(lead_id, similarity_score DESC);

-- ── 3. property_enrichment ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS property_enrichment (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
  address         TEXT NOT NULL,
  beds            INT,
  baths           NUMERIC(3,1),
  sqft            INT,
  year_built      INT,
  lot_size_sqft   INT,
  last_sale_price BIGINT,
  last_sale_date  DATE,
  zestimate       BIGINT,
  tax_assessment  BIGINT,
  property_type   TEXT,
  zpid            TEXT,
  data_source     TEXT DEFAULT 'zillow',
  raw_payload     JSONB,
  fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS property_enrichment_lead_id_idx ON property_enrichment(lead_id);
CREATE INDEX IF NOT EXISTS property_enrichment_address_idx ON property_enrichment(address);

ALTER TABLE property_enrichment ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON property_enrichment FOR ALL USING (auth.role() = 'authenticated');

-- ── 4. arv_results ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS arv_results (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id        UUID REFERENCES leads(id) ON DELETE CASCADE,
  arv_low        BIGINT,
  arv_mid        BIGINT,
  arv_high       BIGINT,
  avg_ppsf       NUMERIC(10,2),
  comp_count     INT,
  confidence     TEXT CHECK (confidence IN ('high', 'medium', 'low')),
  methodology    TEXT,
  computed_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS arv_results_lead_id_idx ON arv_results(lead_id, computed_at DESC);

ALTER TABLE arv_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON arv_results FOR ALL USING (auth.role() = 'authenticated');

-- ── 5. rental_yield ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rental_yield (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
  ltr_monthly_est BIGINT,
  str_monthly_est BIGINT,
  str_occupancy   NUMERIC(5,2),
  str_adr         NUMERIC(10,2),
  gross_yield_ltr NUMERIC(5,2),
  gross_yield_str NUMERIC(5,2),
  fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS rental_yield_lead_id_idx ON rental_yield(lead_id);

ALTER TABLE rental_yield ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON rental_yield FOR ALL USING (auth.role() = 'authenticated');

-- ── 6. market_pulse ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS market_pulse (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zip_code            TEXT NOT NULL,
  median_list_price   BIGINT,
  median_ppsf         NUMERIC(10,2),
  avg_dom             INT,
  list_to_sale_ratio  NUMERIC(5,3),
  price_cut_pct       NUMERIC(5,2),
  market_temp         TEXT CHECK (market_temp IN ('hot', 'warm', 'neutral', 'cool')),
  fetched_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS market_pulse_zip_fetched_idx ON market_pulse(zip_code, fetched_at DESC);

ALTER TABLE market_pulse ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authenticated_full_access" ON market_pulse FOR ALL USING (auth.role() = 'authenticated');

-- ── 7. DB trigger: enrich lead on insert ──────────────────────────────────────
-- Requires pg_net extension and app.supabase_url / app.supabase_anon_key
-- database parameters to be set (see migration header).

CREATE OR REPLACE FUNCTION trigger_enrich_lead()
RETURNS TRIGGER AS $$
DECLARE
  v_url     TEXT;
  v_anon    TEXT;
BEGIN
  BEGIN
    v_url  := current_setting('app.supabase_url');
    v_anon := current_setting('app.supabase_anon_key');
  EXCEPTION WHEN OTHERS THEN
    -- If settings not configured, skip silently — manual enrichment still works
    RETURN NEW;
  END;

  PERFORM net.http_post(
    url     := v_url || '/functions/v1/enrich-property',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer ' || v_anon
    ),
    body    := jsonb_build_object(
      'lead_id', NEW.id,
      'address', NEW.property_address
    )::text
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS enrich_lead_on_insert ON leads;
CREATE TRIGGER enrich_lead_on_insert
  AFTER INSERT ON leads
  FOR EACH ROW EXECUTE FUNCTION trigger_enrich_lead();

-- ── 8. pg_cron schedules ──────────────────────────────────────────────────────
-- Requires pg_cron extension (enabled by default on Supabase Pro).
-- Runs motivated-seller-scan every Sunday at 12:00 UTC (6AM CST).
-- Runs market-pulse every Sunday at 13:00 UTC (7AM CST).

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

    PERFORM cron.schedule(
      'motivated-seller-scan',
      '0 12 * * 0',
      $$
        SELECT net.http_post(
          url     := current_setting('app.supabase_url') || '/functions/v1/motivated-seller-scan',
          headers := jsonb_build_object(
            'Content-Type',  'application/json',
            'Authorization', 'Bearer ' || current_setting('app.supabase_anon_key')
          ),
          body    := '{}'::text
        );
      $$
    );

    PERFORM cron.schedule(
      'market-pulse',
      '0 13 * * 0',
      $$
        SELECT net.http_post(
          url     := current_setting('app.supabase_url') || '/functions/v1/market-pulse',
          headers := jsonb_build_object(
            'Content-Type',  'application/json',
            'Authorization', 'Bearer ' || current_setting('app.supabase_anon_key')
          ),
          body    := '{}'::text
        );
      $$
    );

  END IF;
END;
$$;
