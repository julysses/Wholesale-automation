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
