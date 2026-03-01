from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ComplianceFlag(str, Enum):
    TCPA_QUIET_HOURS = "tcpa_quiet_hours"
    DNC_LIST_MATCH = "dnc_list_match"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    COOLDOWN_ACTIVE = "cooldown_active"
    INVALID_PHONE = "invalid_phone"
    ASSIGNMENT_LAW_RISK = "assignment_law_risk"
    HIGH_PRESSURE_LANGUAGE = "high_pressure_language"
    FALSE_URGENCY = "false_urgency"
    MISSING_REQUIRED_DATA = "missing_required_data"


class ComplianceStatus(str, Enum):
    CLEARED = "cleared"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class ComplianceCheck(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID  # lead_id, deal_id, or outreach_id
    entity_type: str  # "lead" | "deal" | "outreach" | "message_draft"
    status: ComplianceStatus
    flags: list[ComplianceFlag] = Field(default_factory=list)
    flag_details: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    checked_by_agent: str = "compliance_logging_agent"
    auto_halted: bool = False

    @property
    def is_clear(self) -> bool:
        return self.status == ComplianceStatus.CLEARED


class AuditLogEntry(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent: str
    action: str
    entity_id: Optional[UUID] = None
    entity_type: str = ""
    input_summary: str = ""
    output_summary: str = ""
    status: str = "success"  # success | warning | error | blocked
    metadata: dict[str, Any] = Field(default_factory=dict)
