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
    OPTED_OUT = "opted_out"        # inbound opt-out keyword received — suppress immediately
    STOPPED = "stopped"            # compliance block / DNC
    SUPPRESSED = "suppressed"      # permanently suppressed after opt-out


# Legal channel priority order (Section 5): Email > Direct Mail > SMS
CHANNEL_PRIORITY: list[OutreachChannel] = [
    OutreachChannel.EMAIL,
    OutreachChannel.DIRECT_MAIL,
    OutreachChannel.SMS,
]

# Approved A2P 10DLC SMS providers (Section 5)
APPROVED_SMS_PROVIDERS: frozenset[str] = frozenset({"twilio", "telnyx", "messagebird"})

# Approved email providers (Section 5)
APPROVED_EMAIL_PROVIDERS: frozenset[str] = frozenset({"sendgrid", "mailgun", "instantly"})


class OutreachMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    lead_id: UUID
    channel: OutreachChannel
    body: str
    attempt_number: int = 1
    is_followup: bool = False          # True for attempt_number >= 2
    is_inbound_reply: bool = False     # True if this thread was seller-initiated
    status: OutreachStatus = OutreachStatus.DRAFT
    sent_at: Optional[datetime] = None
    response_received_at: Optional[datetime] = None
    response_text: str = ""
    opt_out_detected: bool = False
    opt_out_keyword: str = ""
    a2p_provider: str = ""             # "twilio" | "telnyx" | "messagebird"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    compliance_cleared: bool = False
    compliance_notes: str = ""

    def mark_sent(self) -> None:
        self.status = OutreachStatus.SENT
        self.sent_at = datetime.utcnow()

    def mark_opted_out(self, keyword: str, inbound_text: str = "") -> None:
        """Immediately suppress on opt-out. No confirmation. No follow-up."""
        self.opt_out_detected = True
        self.opt_out_keyword = keyword.upper()
        self.status = OutreachStatus.OPTED_OUT
        self.response_text = inbound_text
        self.response_received_at = datetime.utcnow()

    def mark_stopped(self, reason: str) -> None:
        self.status = OutreachStatus.STOPPED
        self.compliance_notes = reason
