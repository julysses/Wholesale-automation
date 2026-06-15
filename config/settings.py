import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = "claude-sonnet-4-6"

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./wholesale_agency.db")

    # Agency identity (used in outreach templates)
    agency_name: str = os.getenv("AGENCY_NAME", "Texas Wholesale Solutions")
    agency_state: str = os.getenv("AGENCY_STATE", "TX")
    agency_contact_name: str = os.getenv("AGENCY_CONTACT_NAME", "Alex")
    agency_phone: str = os.getenv("AGENCY_PHONE", "")

    # Lead pipeline
    distress_score_threshold: int = int(os.getenv("DISTRESS_SCORE_THRESHOLD", "45"))
    outreach_cooldown_days: int = int(os.getenv("OUTREACH_COOLDOWN_DAYS", "30"))

    # Outreach limits — Section 4 rules
    # Seller: 1 first touch + max 1 follow-up (then hard stop unless seller replies)
    max_seller_followups: int = int(os.getenv("MAX_SELLER_FOLLOWUPS", "1"))
    # Total attempts = first touch + follow-ups
    max_outreach_attempts: int = int(os.getenv("MAX_OUTREACH_ATTEMPTS", "2"))
    # One channel per contact per day
    max_channels_per_contact_per_day: int = int(
        os.getenv("MAX_CHANNELS_PER_CONTACT_PER_DAY", "1")
    )

    # TCPA / Texas scheduling — Section 5 rules
    # Allowed window: 9:00am – 7:00pm Texas local time (America/Chicago)
    texas_timezone: str = os.getenv("TEXAS_TIMEZONE", "America/Chicago")
    tcpa_allowed_start_hour: int = int(os.getenv("TCPA_ALLOWED_START_HOUR", "9"))   # 9am CT
    tcpa_allowed_end_hour: int = int(os.getenv("TCPA_ALLOWED_END_HOUR", "19"))      # 7pm CT
    # Legacy names kept for backward compat in tests; map to new fields
    @property
    def tcpa_quiet_hours_start(self) -> int:
        return self.tcpa_allowed_end_hour  # quiet starts when allowed ends

    @property
    def tcpa_quiet_hours_end(self) -> int:
        return self.tcpa_allowed_start_hour  # quiet ends when allowed starts

    # SMS blocked on weekends (Saturday=5, Sunday=6) unless inbound-initiated
    sms_weekend_blocked: bool = os.getenv("SMS_WEEKEND_BLOCKED", "true").lower() == "true"

    # DNC enforcement
    dnc_check_enabled: bool = os.getenv("DNC_CHECK_ENABLED", "true").lower() == "true"

    # SMS provider (primary: Twilio; alternatives: Telnyx, MessageBird)
    sms_provider: str = os.getenv("SMS_PROVIDER", "twilio")
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")
    telnyx_api_key: str = os.getenv("TELNYX_API_KEY", "")
    telnyx_from_number: str = os.getenv("TELNYX_FROM_NUMBER", "")
    messagebird_api_key: str = os.getenv("MESSAGEBIRD_API_KEY", "")
    messagebird_originator: str = os.getenv("MESSAGEBIRD_ORIGINATOR", "Texas Wholesale")

    # Email provider (SendGrid, Mailgun, Instantly)
    email_provider: str = os.getenv("EMAIL_PROVIDER", "sendgrid")
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    mailgun_api_key: str = os.getenv("MAILGUN_API_KEY", "")
    from_email: str = os.getenv("FROM_EMAIL", "")

    # DNC scrubbing providers (DataAxle, Contact Center Compliance, NumVerify)
    dnc_provider: str = os.getenv("DNC_PROVIDER", "")
    dnc_provider_api_key: str = os.getenv("DNC_PROVIDER_API_KEY", "")
    numverify_api_key: str = os.getenv("NUMVERIFY_API_KEY", "")

    # Data providers
    propstream_api_key: str = os.getenv("PROPSTREAM_API_KEY", "")
    batchleads_api_key: str = os.getenv("BATCHLEADS_API_KEY", "")

    # ── New integrations (blueprint) ──────────────────────────────────────────

    # BatchData / BatchSkipTracing
    batchdata_api_key: str = os.getenv("BATCHDATA_API_KEY", "")

    # BatchDialer
    batchdialer_api_key: str = os.getenv("BATCHDIALER_API_KEY", "")
    # Default campaign to push A/B leads into (set after creating a campaign in BatchDialer)
    batchdialer_default_campaign_id: str = os.getenv("BATCHDIALER_DEFAULT_CAMPAIGN_ID", "")

    # Readymode (adapter slot — use CSV/webhook integration)
    readymode_api_key: str = os.getenv("READYMODE_API_KEY", "")
    readymode_webhook_url: str = os.getenv("READYMODE_WEBHOOK_URL", "")

    # Launch Control SMS
    # Mode: zapier_webhook | csv_sync | api_direct
    launch_control_mode: str = os.getenv("LAUNCH_CONTROL_MODE", "zapier_webhook")
    launch_control_zapier_hook_url: str = os.getenv("LAUNCH_CONTROL_ZAPIER_HOOK_URL", "")
    launch_control_api_key: str = os.getenv("LAUNCH_CONTROL_API_KEY", "")  # private API (optional)
    # Default SMS campaign name for C-tier nurture
    launch_control_default_campaign: str = os.getenv("LAUNCH_CONTROL_DEFAULT_CAMPAIGN", "Nurture Sequence")

    # Podio CRM
    podio_client_id: str = os.getenv("PODIO_CLIENT_ID", "")
    podio_client_secret: str = os.getenv("PODIO_CLIENT_SECRET", "")
    podio_app_id_leads: str = os.getenv("PODIO_APP_ID_LEADS", "")
    podio_app_token_leads: str = os.getenv("PODIO_APP_TOKEN_LEADS", "")

    # REsimpli CRM
    resimpli_api_key: str = os.getenv("RESIMPLI_API_KEY", "")
    resimpli_webhook_url: str = os.getenv("RESIMPLI_WEBHOOK_URL", "")

    # Notifications
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    notification_email: str = os.getenv("NOTIFICATION_EMAIL", "")

    # Retell AI (primary AI calling provider)
    retell_api_key: str = os.getenv("RETELL_API_KEY", "")
    retell_agent_id: str = os.getenv("RETELL_AGENT_ID", "")
    retell_from_number: str = os.getenv("RETELL_FROM_NUMBER", "")
    retell_webhook_secret: str = os.getenv("RETELL_WEBHOOK_SECRET", "")

    # Air AI (alternative AI calling provider)
    air_ai_api_key: str = os.getenv("AIR_AI_API_KEY", "")
    air_ai_agent_id: str = os.getenv("AIR_AI_AGENT_ID", "")
    air_ai_from_number: str = os.getenv("AIR_AI_FROM_NUMBER", "")
    air_ai_webhook_secret: str = os.getenv("AIR_AI_WEBHOOK_SECRET", "")

    # VAPI.ai (preferred AI calling provider — $0.07/min vs Retell's $0.11/min)
    vapi_api_key: str = os.getenv("VAPI_API_KEY", "")
    # Phone number ID from VAPI dashboard (Settings → Phone Numbers)
    vapi_phone_number_id: str = os.getenv("VAPI_PHONE_NUMBER_ID", "")
    # Optional: pre-built assistant ID. Leave blank to use inline system prompt.
    vapi_assistant_id: str = os.getenv("VAPI_ASSISTANT_ID", "")
    vapi_webhook_secret: str = os.getenv("VAPI_WEBHOOK_SECRET", "")

    # AI calling provider selection: "vapi" | "retell" | "air_ai"
    ai_calling_provider: str = os.getenv("AI_CALLING_PROVIDER", "retell")

    # ── Calendar Integration ──────────────────────────────────────────────────
    google_calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "")
    calendly_api_key: str = os.getenv("CALENDLY_API_KEY", "")

    # ── Facebook Lead Ads ─────────────────────────────────────────────────────
    facebook_app_id: str = os.getenv("FACEBOOK_APP_ID", "")
    facebook_app_secret: str = os.getenv("FACEBOOK_APP_SECRET", "")
    # Page or user access token (long-lived, 60-day, or never-expiring system token)
    facebook_access_token: str = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    # Must match the verify token in your Facebook App webhook settings
    facebook_webhook_verify_token: str = os.getenv("FACEBOOK_WEBHOOK_VERIFY_TOKEN", "")
    # Format: act_XXXXX or just the numeric ID
    facebook_ad_account_id: str = os.getenv("FACEBOOK_AD_ACCOUNT_ID", "")

    # Webhook secrets (for verifying inbound webhooks)
    batchdialer_webhook_secret: str = os.getenv("BATCHDIALER_WEBHOOK_SECRET", "")
    launch_control_webhook_secret: str = os.getenv("LAUNCH_CONTROL_WEBHOOK_SECRET", "")

    # ── Seller score routing thresholds ───────────────────────────────────────
    # Tiers: A=90+ B=70-89 C=50-69 D<50  (A+B → AI calling, C → SMS, D → suppress)
    seller_score_dialer_min_tier: str = os.getenv("SELLER_SCORE_DIALER_MIN_TIER", "B")
    seller_score_sms_min_tier: str = os.getenv("SELLER_SCORE_SMS_MIN_TIER", "C")
    # Skip trace all leads by default before scoring
    auto_skip_trace: bool = os.getenv("AUTO_SKIP_TRACE", "true").lower() == "true"
    # Auto-push A/B leads to BatchDialer after scoring
    auto_push_to_dialer: bool = os.getenv("AUTO_PUSH_TO_DIALER", "false").lower() == "true"
    # Auto-enroll C leads in Launch Control SMS
    auto_enroll_sms_nurture: bool = os.getenv("AUTO_ENROLL_SMS_NURTURE", "false").lower() == "true"


settings = Settings()
