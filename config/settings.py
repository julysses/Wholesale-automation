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
    messagebird_api_key: str = os.getenv("MESSAGEBIRD_API_KEY", "")

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


settings = Settings()
