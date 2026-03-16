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
