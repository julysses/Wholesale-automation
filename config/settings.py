import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = "claude-sonnet-4-6"

    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./wholesale_agency.db")

    # Agency
    agency_name: str = os.getenv("AGENCY_NAME", "Texas Wholesale Solutions")
    agency_state: str = os.getenv("AGENCY_STATE", "TX")
    distress_score_threshold: int = int(os.getenv("DISTRESS_SCORE_THRESHOLD", "45"))
    max_outreach_attempts: int = int(os.getenv("MAX_OUTREACH_ATTEMPTS", "2"))
    outreach_cooldown_days: int = int(os.getenv("OUTREACH_COOLDOWN_DAYS", "30"))

    # SMS
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Data Providers
    propstream_api_key: str = os.getenv("PROPSTREAM_API_KEY", "")
    batchleads_api_key: str = os.getenv("BATCHLEADS_API_KEY", "")

    # Compliance
    dnc_check_enabled: bool = os.getenv("DNC_CHECK_ENABLED", "true").lower() == "true"
    tcpa_quiet_hours_start: int = int(os.getenv("TCPA_QUIET_HOURS_START", "21"))
    tcpa_quiet_hours_end: int = int(os.getenv("TCPA_QUIET_HOURS_END", "8"))


settings = Settings()
