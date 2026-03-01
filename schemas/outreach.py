from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OutreachChannel(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    DIRECT_MAIL = "direct_mail"
    FACEBOOK_DM = "facebook_dm"
    PHONE_CALL = "phone_call"


class OutreachStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENT = "sent"
    DELIVERED = "delivered"
    RESPONDED_POSITIVE = "responded_positive"
    RESPONDED_NEGATIVE = "responded_negative"
    NO_RESPONSE = "no_response"
    STOPPED = "stopped"  # DNC / opt-out


class OutreachMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    channel: OutreachChannel
    body: str
    attempt_number: int = 1
    status: OutreachStatus = OutreachStatus.DRAFT
    sent_at: Optional[datetime] = None
    response_received_at: Optional[datetime] = None
    response_text: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    compliance_cleared: bool = False
    compliance_notes: str = ""

    def mark_sent(self) -> None:
        self.status = OutreachStatus.SENT
        self.sent_at = datetime.utcnow()

    def mark_stopped(self, reason: str) -> None:
        self.status = OutreachStatus.STOPPED
        self.compliance_notes = reason
