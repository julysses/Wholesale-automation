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
