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

-- Drop first: this redefinition reorders columns (adds warm_leads before
-- hot_leads), which CREATE OR REPLACE VIEW cannot do (ERROR 42P16).
DROP VIEW IF EXISTS funnel_metrics;
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
