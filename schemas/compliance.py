from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ComplianceFlag(str, Enum):
    # Scheduling / TCPA
    TCPA_QUIET_HOURS = "tcpa_quiet_hours"
    WEEKEND_SMS_BLOCKED = "weekend_sms_blocked"

    # DNC / consent
    DNC_LIST_MATCH = "dnc_list_match"
    DNC_NO_CONSENT = "dnc_no_consent"
    CONSENT_UNCLEAR = "consent_unclear"

    # Attempt limits (Section 4)
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    FOLLOW_UP_LIMIT_EXCEEDED = "follow_up_limit_exceeded"
    COOLDOWN_ACTIVE = "cooldown_active"

    # Channel rules
    CHANNEL_LIMIT_EXCEEDED = "channel_limit_exceeded"  # one channel per day

    # Phone / contact
    INVALID_PHONE = "invalid_phone"

    # Content violations
    HIGH_PRESSURE_LANGUAGE = "high_pressure_language"
    FALSE_URGENCY = "false_urgency"
    PROMOTIONAL_CONTENT = "promotional_content"
    ILLEGAL_LOCAL_LANGUAGE = "illegal_local_language"  # implied surveillance/physical observation

    # Legal
    ASSIGNMENT_LAW_RISK = "assignment_law_risk"
    MISSING_REQUIRED_DATA = "missing_required_data"

    # Compliance uncertainty — mandatory escalation (Section 5)
    COMPLIANCE_UNCERTAIN = "compliance_uncertain"


# Flags that cause an immediate hard BLOCK (no send under any circumstance)
HARD_BLOCK_FLAGS: frozenset[ComplianceFlag] = frozenset({
    ComplianceFlag.DNC_LIST_MATCH,
    ComplianceFlag.DNC_NO_CONSENT,
    ComplianceFlag.WEEKEND_SMS_BLOCKED,
    ComplianceFlag.MAX_ATTEMPTS_EXCEEDED,
    ComplianceFlag.FOLLOW_UP_LIMIT_EXCEEDED,
    ComplianceFlag.HIGH_PRESSURE_LANGUAGE,
    ComplianceFlag.ILLEGAL_LOCAL_LANGUAGE,
    ComplianceFlag.COMPLIANCE_UNCERTAIN,
    ComplianceFlag.TCPA_QUIET_HOURS,
})


class ComplianceStatus(str, Enum):
    CLEARED = "cleared"
    FLAGGED = "flagged"   # escalate / review before sending
    BLOCKED = "blocked"   # hard stop; do not send


class ComplianceCheck(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    entity_type: str  # "lead" | "deal" | "outreach" | "message_draft"
    status: ComplianceStatus
    flags: list[ComplianceFlag] = Field(default_factory=list)
    flag_details: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    checked_by_agent: str = "compliance_logging_agent"
    auto_halted: bool = False
    escalation_note: str = ""

    @property
    def is_clear(self) -> bool:
        return self.status == ComplianceStatus.CLEARED


class OptOutRecord(BaseModel):
    """Immutable record of a contact opting out — never deleted."""
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    phone_or_email: str
    opt_out_keyword: str
    channel: str
    received_at: datetime = Field(default_factory=datetime.utcnow)
    suppressed_at: datetime = Field(default_factory=datetime.utcnow)
    inbound_text: str = ""


class AuditLogEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent: str
    action: str
    entity_id: Optional[UUID] = None
    entity_type: str = ""
    input_summary: str = ""
    output_summary: str = ""
    status: str = "success"  # success | warning | error | blocked | escalated
    metadata: dict[str, Any] = Field(default_factory=dict)
