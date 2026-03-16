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
