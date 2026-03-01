"""
Compliance & Logging Agent — Sections 4 & 5 enforcement.

Enforces: TCPA, CAN-SPAM, Texas scheduling, DNC, opt-out suppression,
follow-up limits, channel frequency, content rules, and audit logging.

MANDATORY RULE: If compliance is uncertain, do not send. Log and escalate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

from config.prompts import SystemPrompts
from config.settings import settings
from schemas.compliance import (
    AuditLogEntry,
    ComplianceCheck,
    ComplianceFlag,
    ComplianceStatus,
    HARD_BLOCK_FLAGS,
    OptOutRecord,
)
from schemas.outreach import OutreachMessage, OutreachStatus
from schemas.property import PropertyLead
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Opt-out keyword registry (Section 4 & 5) ─────────────────────────────────
# Immediate suppression on any of these — no confirmation, no follow-up
OPT_OUT_KEYWORDS: frozenset[str] = frozenset({
    "stop",
    "no",
    "remove",
    "unsubscribe",
    "not interested",
    "dont contact",
    "do not contact",
    "dont call",
    "do not call",
    "leave me alone",
    "remove me",
    "take me off",
    "opt out",
    "optout",
})

# Illegal local-language patterns (Section 4) — imply physical observation
ILLEGAL_LOCAL_PHRASES: frozenset[str] = frozenset({
    "drove by",
    "drive by",
    "driving by",
    "drove past",
    "noticed your property",
    "noticed your home",
    "noticed your house",
    "saw your property",
    "saw your home",
    "saw your house",
    "been watching",
    "keeping an eye",
    "been monitoring",
    "walking by",
    "walked by",
    "passed by",
    "pass by",
})


def _texas_now() -> datetime:
    """Return the current datetime in Texas local time (America/Chicago)."""
    try:
        tz = ZoneInfo(settings.texas_timezone)
    except Exception:
        tz = timezone.utc
    return datetime.now(tz=tz)


class ComplianceLoggingAgent(BaseAgent):
    name = "compliance_logging_agent"
    system_prompt = SystemPrompts.COMPLIANCE_LOGGING

    def __init__(self) -> None:
        super().__init__()
        self._audit_log: list[AuditLogEntry] = []
        self._opt_out_records: list[OptOutRecord] = []
        self._suppressed_contacts: set[str] = set()  # phone_or_email strings

    # ── Opt-out detection & suppression ──────────────────────────────────────

    def detect_opt_out(self, text: str) -> Optional[str]:
        """
        Scan inbound text for opt-out keywords.
        Returns the matched keyword (lowercase) or None.
        Iterates longest-first to prevent "no" matching before "not interested".
        Section 4 rule: suppress immediately, no confirmation.
        """
        lowered = text.lower().strip()
        for keyword in sorted(OPT_OUT_KEYWORDS, key=len, reverse=True):
            if keyword in lowered:
                return keyword
        return None

    def process_inbound_reply(
        self,
        lead: PropertyLead,
        reply_text: str,
        message: OutreachMessage,
        contact_identifier: str,  # phone number or email
    ) -> bool:
        """
        Process an inbound seller reply. If opt-out detected, suppress immediately.
        Returns True if opt-out was detected and contact suppressed.
        """
        keyword = self.detect_opt_out(reply_text)
        if keyword:
            # Suppress the contact permanently
            self._suppressed_contacts.add(contact_identifier.lower())

            # Record the opt-out immutably
            record = OptOutRecord(
                lead_id=lead.id,
                phone_or_email=contact_identifier,
                opt_out_keyword=keyword,
                channel=message.channel.value,
                inbound_text=reply_text[:500],
            )
            self._opt_out_records.append(record)

            # Mark message as opted out
            message.mark_opted_out(keyword, reply_text[:500])

            self.log_action(
                agent=self.name,
                action="opt_out_suppression",
                entity_id=lead.id,
                entity_type="lead",
                input_summary=f"keyword='{keyword}', contact={contact_identifier[:6]}***",
                output_summary="Contact permanently suppressed. No further outreach.",
                status="blocked",
                metadata={"opt_out_keyword": keyword, "channel": message.channel.value},
            )
            logger.warning(
                f"[{self.name}] OPT-OUT: lead {lead.id} suppressed "
                f"(keyword='{keyword}', contact={contact_identifier[:6]}***)"
            )
            return True
        return False

    def is_suppressed(self, contact_identifier: str) -> bool:
        """Check if a contact has opted out and is suppressed."""
        return contact_identifier.lower() in self._suppressed_contacts

    # ── Scheduling checks (Section 5) ────────────────────────────────────────

    def _in_allowed_hours(self) -> bool:
        """Check if current Texas time is within 9:00am–7:00pm CT."""
        now = _texas_now()
        start = settings.tcpa_allowed_start_hour   # 9
        end = settings.tcpa_allowed_end_hour        # 19
        return start <= now.hour < end

    def _is_weekend(self) -> bool:
        """Check if today is Saturday (5) or Sunday (6) in Texas local time."""
        return _texas_now().weekday() >= 5

    # ── Illegal content checks (Section 4) ───────────────────────────────────

    def check_local_language(self, text: str) -> list[str]:
        """Detect illegal local-language phrases implying physical observation."""
        lowered = text.lower()
        return [phrase for phrase in ILLEGAL_LOCAL_PHRASES if phrase in lowered]

    # ── Master outreach pre-flight check ─────────────────────────────────────

    def check_outreach(
        self,
        message: OutreachMessage,
        lead: PropertyLead,
        existing_attempt_count: int,
        has_inbound_reply: bool = False,
        contact_identifier: str = "",
    ) -> ComplianceCheck:
        """
        Run ALL compliance checks before allowing a message to be sent.
        Any HARD_BLOCK_FLAG causes an immediate block.
        If ANY check is uncertain, the message is blocked (Section 5 mandatory rule).
        """
        flags: dict[ComplianceFlag, str] = {}

        # 1. Suppression check (opted-out contact)
        if contact_identifier and self.is_suppressed(contact_identifier):
            flags[ComplianceFlag.DNC_NO_CONSENT] = (
                f"Contact {contact_identifier[:6]}*** is suppressed (opted out)"
            )

        # 2. Max total attempts
        if existing_attempt_count >= settings.max_outreach_attempts:
            flags[ComplianceFlag.MAX_ATTEMPTS_EXCEEDED] = (
                f"Attempt {existing_attempt_count + 1} exceeds "
                f"max {settings.max_outreach_attempts}"
            )

        # 3. Follow-up limit: max 1 follow-up without a seller reply (Section 4)
        if message.is_followup and not has_inbound_reply:
            prior_followups = max(0, existing_attempt_count - 1)  # attempts beyond first touch
            if prior_followups >= settings.max_seller_followups:
                flags[ComplianceFlag.FOLLOW_UP_LIMIT_EXCEEDED] = (
                    f"Follow-up limit reached ({settings.max_seller_followups} max). "
                    "Stop all SMS outreach until seller initiates."
                )

        # 4. Texas scheduling — allowed hours 9am–7pm CT
        if not self._in_allowed_hours():
            now = _texas_now()
            flags[ComplianceFlag.TCPA_QUIET_HOURS] = (
                f"Current Texas time {now.strftime('%H:%M %Z')} is outside "
                f"allowed window ({settings.tcpa_allowed_start_hour}:00–"
                f"{settings.tcpa_allowed_end_hour}:00 CT)"
            )

        # 5. Weekend SMS block (Section 5) — unless inbound-initiated
        if (
            message.channel.value == "sms"
            and settings.sms_weekend_blocked
            and self._is_weekend()
            and not message.is_inbound_reply
        ):
            flags[ComplianceFlag.WEEKEND_SMS_BLOCKED] = (
                f"SMS blocked on weekends ({_texas_now().strftime('%A')}). "
                "Only allowed if seller initiated the contact."
            )

        # 6. Phone validation
        if not lead.phone_numbers:
            flags[ComplianceFlag.INVALID_PHONE] = "No phone number on file for this lead"

        # 7. Message content clearance by outreach agent
        if not message.compliance_cleared:
            flags[ComplianceFlag.HIGH_PRESSURE_LANGUAGE] = (
                "Message was not cleared by seller outreach agent — content unverified"
            )

        # 8. Illegal local language in message body
        illegal = self.check_local_language(message.body)
        if illegal:
            flags[ComplianceFlag.ILLEGAL_LOCAL_LANGUAGE] = (
                f"Message contains illegal phrases implying physical observation: {illegal}"
            )

        # 9. Determine final status
        has_hard_block = any(f in HARD_BLOCK_FLAGS for f in flags)
        if has_hard_block:
            status = ComplianceStatus.BLOCKED
            escalation = (
                "MANDATORY ESCALATION: Message blocked due to hard compliance violation. "
                "Do not retry without resolving flagged issues."
            )
        elif flags:
            status = ComplianceStatus.FLAGGED
            escalation = "Review flagged issues before sending."
        else:
            status = ComplianceStatus.CLEARED
            escalation = ""

        check = ComplianceCheck(
            entity_id=message.id,
            entity_type="outreach",
            status=status,
            flags=list(flags.keys()),
            flag_details={f.value: detail for f, detail in flags.items()},
            auto_halted=status == ComplianceStatus.BLOCKED,
            escalation_note=escalation,
        )

        log_status = "blocked" if status == ComplianceStatus.BLOCKED else "success"
        self.log_action(
            agent=self.name,
            action="outreach_compliance_check",
            entity_id=message.id,
            entity_type="outreach",
            input_summary=(
                f"lead={lead.id}, channel={message.channel.value}, "
                f"attempt={existing_attempt_count + 1}, "
                f"is_followup={message.is_followup}, "
                f"has_reply={has_inbound_reply}"
            ),
            output_summary=(
                f"status={status.value}, "
                f"flags={[f.value for f in check.flags]}"
            ),
            status=log_status,
        )

        if check.auto_halted:
            logger.warning(
                f"[{self.name}] BLOCKED lead={lead.id} "
                f"flags={[f.value for f in check.flags]}"
            )

        return check

    def review_message_tone(self, message_body: str) -> ComplianceCheck:
        """
        Use Claude to review a draft message for tone compliance.
        Checks pressure language, urgency, illegal local phrases, and promotional content.
        """
        from uuid import uuid4

        prompt = f"""
Review this outreach message for compliance with Sections 4 & 5 ethical outreach rules.

Message:
---
{message_body}
---

Check for ALL of the following violations:
1. high_pressure_language — urgency, pressure, deadlines
2. false_urgency — "act now", "expires", "limited time", "last chance"
3. promotional_content — the message reads like an advertisement rather than a personal inquiry
4. illegal_local_language — implies physical observation: "drove by", "noticed your property",
   "saw your home", "been watching", "keeping an eye", "walked by", "passed by"

ALSO verify:
- The message uses only approved local phrases: "I live in the area", "I'm local to the neighborhood",
  "I'm based nearby", or "local to the area"
- The message includes an opt-out instruction (e.g. "Reply STOP to opt out")
- The message is informational, not promotional

If uncertain about ANY element: return compliance_status as "blocked" and set
compliance_uncertain flag.

Return JSON with:
- compliance_status: "cleared" | "flagged" | "blocked"
- flags: list of violation types found
- flag_details: dict explaining each flag
- entity_id: "draft"
- entity_type: "message_draft"
- auto_halted: true if blocked
- escalation_note: explanation if blocked
"""
        check = self._call_structured(prompt, ComplianceCheck)
        check.entity_id = uuid4()
        return check

    # ── Audit logging ─────────────────────────────────────────────────────────

    def log_action(
        self,
        agent: str,
        action: str,
        entity_id: Optional[UUID] = None,
        entity_type: str = "",
        input_summary: str = "",
        output_summary: str = "",
        status: str = "success",
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            agent=agent,
            action=action,
            entity_id=entity_id,
            entity_type=entity_type,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            metadata=metadata or {},
        )
        self._audit_log.append(entry)
        logger.info(
            f"[AUDIT] {entry.timestamp.isoformat()} | {agent} | {action} | "
            f"{entity_type}={entity_id} | {status}"
        )
        return entry

    def export_audit_log(self) -> list[dict[str, Any]]:
        """Return the full immutable audit log as dicts."""
        return [entry.model_dump(mode="json") for entry in self._audit_log]

    def get_log(self) -> list[AuditLogEntry]:
        return list(self._audit_log)

    def get_opt_out_records(self) -> list[OptOutRecord]:
        return list(self._opt_out_records)

    def run(self, *args: Any, **kwargs: Any) -> list[AuditLogEntry]:
        return self.get_log()
