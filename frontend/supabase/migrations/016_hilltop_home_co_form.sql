-- Hilltop Home Co. website — dedicated lead_form_configs entry.
--
-- The Hilltop Home Co. marketing site (julysses/hilltophome) submits its
-- "Get an Offer" form to POST /api/forms/hilltop-home-co/submit. Its
-- questions[] use the SAME field_names/types/option-values as the existing
-- `dfw-motivated-seller` form (see 009_lead_generation.sql) — this is
-- intentional: _compute_scores_from_answers() in web/api/lead_forms_api.py
-- reads answers by these exact keys, so reusing the vocabulary means the
-- new form scores correctly with zero backend code changes. Only branding,
-- copy, and the sms_opt_in label (upgraded to real TCPA consent language,
-- and marked required — the website's own client-side validation enforces
-- this regardless of the `required` flag here, which the backend does not
-- itself enforce) differ from the generic form.
--
-- The website form itself is a single scrolling page, not a step-gated
-- wizard — the questions[].step numbers below are kept only as the
-- backend's own record of which fields are grouped together, not an
-- actual UI step sequence.
--
-- expected_range is a new question (price-band select) replacing the old
-- free-text asking_price question — a band doesn't map to the single
-- numeric asking_price column _compute_scores_from_answers() writes, so
-- it's captured in raw_answers for the team's reference but intentionally
-- not wired into the scoring math.
--
-- NOTE: the phone number below is a placeholder — replace with the real
-- Hilltop Home Co. business line before this form goes live.

INSERT INTO lead_form_configs (
    name, slug, headline, subheadline, brand_color, thank_you_message,
    send_confirmation_sms, active,
    questions
) VALUES (
    'Hilltop Home Co. — Get an Offer',
    'hilltop-home-co',
    'Sell Your DFW House As-Is, For Cash',
    'No repairs. No agent fees. No showings. Get a fair cash offer and close on your timeline.',
    '#CE0435',
    'Thanks — we''ll be in touch shortly. If it''s urgent, call or text us at (214) 555-0100.',
    TRUE, TRUE,
    '[
        {"id":"step1_address","step":1,"type":"text","field_name":"property_address","label":"Property Address","placeholder":"123 Main St, Garland, TX","required":true},
        {"id":"step1_first_name","step":1,"type":"text","field_name":"first_name","label":"Your First Name","required":true},
        {"id":"step1_last_name","step":1,"type":"text","field_name":"last_name","label":"Your Last Name (optional)","required":false},
        {"id":"step1_phone","step":1,"type":"tel","field_name":"phone","label":"Best Phone Number","required":true},
        {"id":"step1_email","step":1,"type":"email","field_name":"email","label":"Email (optional)","required":false},
        {"id":"step1_expected_range","step":1,"type":"radio","field_name":"expected_range","label":"What price range are you expecting?","required":false,"options":[
            {"value":"under_150k","label":"Under $150K"},
            {"value":"150k_250k","label":"$150K – $250K"},
            {"value":"250k_350k","label":"$250K – $350K"},
            {"value":"350k_500k","label":"$350K – $500K"},
            {"value":"500k_plus","label":"$500K+"},
            {"value":"not_sure","label":"Not sure"}
        ]},
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
        {"id":"step4_sms_opt_in","step":4,"type":"checkbox","field_name":"sms_opt_in","label":"By checking this box, I agree to receive text messages from Hilltop Home Co. about my property inquiry. Message and data rates may apply. Reply STOP to opt out.","required":true}
    ]'::JSONB
) ON CONFLICT (slug) DO NOTHING;
