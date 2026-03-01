"""
Seller Outreach Agent — ethical, pressure-free communications only.

Enforces Sections 4 & 5 rules:
- Approved message templates only
- Strict local-language rules (no physical observation implied)
- Max 1 follow-up without seller reply, then hard stop
- Instant opt-out on negative signals
- Full banned-phrase enforcement
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from config.settings import settings
from schemas.outreach import OutreachChannel, OutreachMessage, OutreachStatus
from schemas.property import PropertyLead
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Banned phrases (hard block) ───────────────────────────────────────────────
BANNED_PHRASES: frozenset[str] = frozenset({
    "limited time",
    "act now",
    "expires",
    "last chance",
    "don't miss",
    "urgent",
    "must sell",
    "final offer",
    "guaranteed",
    "cash offer expires",
    "high pressure",
    "pressure tactics",
    "under pressure to sell",
    "deal ends",
    "only a few",
    "best offer",
    "time sensitive",
    "immediate",
    "today only",
    "don't wait",
})

# ── Illegal local-language phrases (Section 4) ────────────────────────────────
# These imply physical observation, monitoring, or false residency
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
    "passed by your",
    "pass by",
    "your property looks",
    "your home looks",
    "your house looks",
})

# ── Approved local-presence phrases (Section 4) ───────────────────────────────
APPROVED_LOCAL_PHRASES: tuple[str, ...] = (
    "I live in the area",
    "I'm local to the neighborhood",
    "I'm based nearby",
    "local to the area",
)

# ── Opt-out trigger words ─────────────────────────────────────────────────────
OPT_OUT_SIGNALS: frozenset[str] = frozenset({
    "stop", "no", "remove", "unsubscribe", "not interested",
    "dont contact", "do not contact", "leave me alone", "remove me",
})

# ── Approved SMS first-touch template (Section 4) ────────────────────────────
SELLER_SMS_FIRST_TOUCH_TEMPLATE = (
    "Hi {owner_name},\n"
    "My name is {sender_name}. I live in the area and came across your property "
    "at {address} through public records. "
    "I'm not sure if you'd ever consider selling, but if it's something you're open to "
    "discussing at some point, I'd be happy to share what options exist.\n"
    "No rush at all—just wanted to ask.\n"
    "— {sender_name}"
)

# ── Approved SMS follow-up template (Section 4) ───────────────────────────────
SELLER_SMS_FOLLOWUP_TEMPLATE = (
    "Hi {owner_name}, this is {sender_name} again regarding {address}. "
    "Just following up on my earlier message. "
    "No pressure at all—happy to connect if the timing ever works for you. "
    "Reply STOP to opt out.\n"
    "— {sender_name}"
)


class MessageDraft(BaseModel):
    body: str
    channel: str
    tone_assessment: str
    compliance_notes: str


class SellerOutreachAgent(BaseAgent):
    name = "seller_outreach_agent"
    system_prompt = SystemPrompts.SELLER_OUTREACH

    # ── Compliance checkers ───────────────────────────────────────────────────

    def _check_banned_phrases(self, text: str) -> list[str]:
        lowered = text.lower()
        return [p for p in BANNED_PHRASES if p in lowered]

    def _check_illegal_local_language(self, text: str) -> list[str]:
        """Detect phrases that imply physical observation (Section 4)."""
        lowered = text.lower()
        return [p for p in ILLEGAL_LOCAL_PHRASES if p in lowered]

    def _check_has_opt_out_instruction(self, text: str) -> bool:
        """Verify the message includes an opt-out instruction."""
        lowered = text.lower()
        return any(phrase in lowered for phrase in (
            "reply stop", "text stop", "opt out", "unsubscribe",
        ))

    def _check_followup_allowed(
        self, existing_attempt_count: int, has_inbound_reply: bool
    ) -> bool:
        """
        Section 4 rule: max ONE follow-up if no reply.
        If seller has replied, follow-ups can continue within attempt limit.
        """
        if has_inbound_reply:
            return existing_attempt_count < settings.max_outreach_attempts
        # Without a seller reply: only 1 follow-up (attempt_number 2) is allowed
        return existing_attempt_count < (1 + settings.max_seller_followups)

    # ── Template-based message rendering (Section 4) ─────────────────────────

    def _render_first_touch_sms(self, lead: PropertyLead) -> str:
        """Render the approved first-touch SMS template."""
        owner_first = lead.owner_name.split()[0] if lead.owner_name else "there"
        return SELLER_SMS_FIRST_TOUCH_TEMPLATE.format(
            owner_name=owner_first,
            sender_name=settings.agency_contact_name,
            address=lead.address.full,
        )

    def _render_followup_sms(self, lead: PropertyLead) -> str:
        """Render the approved follow-up SMS template."""
        owner_first = lead.owner_name.split()[0] if lead.owner_name else "there"
        return SELLER_SMS_FOLLOWUP_TEMPLATE.format(
            owner_name=owner_first,
            sender_name=settings.agency_contact_name,
            address=lead.address.full,
        )

    def _validate_and_block(
        self,
        body: str,
        lead: PropertyLead,
        msg: OutreachMessage,
    ) -> bool:
        """
        Run hard content checks. Mutates msg if blocked.
        Returns True if message should be blocked.
        """
        banned = self._check_banned_phrases(body)
        illegal_local = self._check_illegal_local_language(body)
        violations = []

        if banned:
            violations.append(f"banned phrases: {banned}")
        if illegal_local:
            violations.append(f"illegal local language: {illegal_local}")

        if violations:
            reason = " | ".join(violations)
            msg.compliance_notes = f"[BLOCKED] {reason}"
            msg.status = OutreachStatus.STOPPED
            logger.error(
                f"[{self.name}] Message blocked for lead {lead.id}: {reason}"
            )
            return True
        return False

    # ── Public draft methods ──────────────────────────────────────────────────

    def draft_sms(
        self,
        lead: PropertyLead,
        attempt_number: int = 1,
        has_inbound_reply: bool = False,
    ) -> OutreachMessage:
        """
        Draft an SMS using the approved template.

        First touch (attempt 1): use SELLER_SMS_FIRST_TOUCH_TEMPLATE.
        Follow-up (attempt 2): use SELLER_SMS_FOLLOWUP_TEMPLATE.
        Attempt 3+: blocked unless seller has replied.
        """
        is_followup = attempt_number > 1

        # Section 4: follow-up gate
        if not self._check_followup_allowed(attempt_number - 1, has_inbound_reply):
            msg = OutreachMessage(
                lead_id=lead.id,
                channel=OutreachChannel.SMS,
                body="",
                attempt_number=attempt_number,
                is_followup=is_followup,
                is_inbound_reply=has_inbound_reply,
                status=OutreachStatus.STOPPED,
                compliance_notes=(
                    f"[BLOCKED] Follow-up limit reached. "
                    f"Max {settings.max_seller_followups} follow-up(s) without seller reply. "
                    "Stop all outreach until seller initiates."
                ),
            )
            logger.warning(
                f"[{self.name}] Follow-up blocked for lead {lead.id}: "
                f"attempt={attempt_number}, has_reply={has_inbound_reply}"
            )
            return msg

        # Select the approved template
        if is_followup:
            body = self._render_followup_sms(lead)
        else:
            body = self._render_first_touch_sms(lead)

        msg = OutreachMessage(
            lead_id=lead.id,
            channel=OutreachChannel.SMS,
            body=body,
            attempt_number=attempt_number,
            is_followup=is_followup,
            is_inbound_reply=has_inbound_reply,
        )

        if self._validate_and_block(body, lead, msg):
            return msg

        # Verify opt-out instruction present in follow-ups
        if is_followup and not self._check_has_opt_out_instruction(body):
            msg.compliance_notes = "[WARNING] Follow-up missing opt-out instruction"
            logger.warning(f"[{self.name}] Follow-up missing opt-out for lead {lead.id}")

        msg.compliance_cleared = True
        logger.info(f"[{self.name}] SMS drafted for lead {lead.id}, attempt {attempt_number}")
        return msg

    def draft_email(
        self,
        lead: PropertyLead,
        attempt_number: int = 1,
        has_inbound_reply: bool = False,
        context: str = "",
    ) -> OutreachMessage:
        """
        Draft a CAN-SPAM compliant seller outreach email.
        Uses Claude within strict template guidance.
        Email is the preferred channel (Section 5 priority #1).
        """
        is_followup = attempt_number > 1

        if not self._check_followup_allowed(attempt_number - 1, has_inbound_reply):
            msg = OutreachMessage(
                lead_id=lead.id,
                channel=OutreachChannel.EMAIL,
                body="",
                attempt_number=attempt_number,
                is_followup=is_followup,
                status=OutreachStatus.STOPPED,
                compliance_notes=(
                    "[BLOCKED] Follow-up limit reached without seller reply."
                ),
            )
            return msg

        owner_first = lead.owner_name.split()[0] if lead.owner_name else "there"
        prompt = f"""
Draft a CAN-SPAM compliant seller outreach email.

Property: {lead.address.full}
Owner first name: {owner_first}
Sender name: {settings.agency_contact_name}
Agency: {settings.agency_name}
Agency phone: {settings.agency_phone or "available on request"}
Attempt number: {attempt_number}
Context: {context or "None"}

MANDATORY STRUCTURE:
Subject: A question about your property at {lead.address.street}

Body (3–4 sentences max):
- Open with "Hi {owner_first},"
- Introduce sender as local to the area using ONLY one of:
  "I live in the area" / "I'm local to the neighborhood" / "I'm based nearby"
- Frame as: "I came across your property through public records and wanted to ask..."
- State clearly this is optional / no pressure / no rush
- Include physical mailing address for CAN-SPAM compliance
- Include unsubscribe instruction: "Reply UNSUBSCRIBE to stop receiving messages"
- Sign with: sender name, agency name, phone

HARD RULES:
- NO pressure language
- NO urgency or deadlines
- NO "drove by", "noticed", "saw your property" or any physical observation phrasing
- NO promotional language
- Tone: informational, respectful, peer-to-peer

Return body (full email text including subject line as "Subject: ...\\n\\nBody text"),
tone_assessment, compliance_notes, channel="email".
"""
        draft = self._call_structured(prompt, MessageDraft)

        msg = OutreachMessage(
            lead_id=lead.id,
            channel=OutreachChannel.EMAIL,
            body=draft.body,
            attempt_number=attempt_number,
            is_followup=is_followup,
            is_inbound_reply=has_inbound_reply,
            compliance_notes=draft.compliance_notes,
        )

        if self._validate_and_block(draft.body, lead, msg):
            return msg

        msg.compliance_cleared = True
        logger.info(f"[{self.name}] Email drafted for lead {lead.id}, attempt {attempt_number}")
        return msg

    def handle_response(
        self,
        lead: PropertyLead,
        response_text: str,
        message: OutreachMessage,
    ) -> dict:
        """
        Classify a seller's response and determine next action.
        Any opt-out signal → stop_outreach immediately.
        Section 4: never suggest pushing harder.
        """
        # Hard check for opt-out keywords first (before API call)
        lowered = response_text.lower().strip()
        for keyword in sorted(OPT_OUT_SIGNALS, key=len, reverse=True):
            if keyword in lowered:
                logger.info(
                    f"[{self.name}] Opt-out detected for lead {lead.id}: '{keyword}'"
                )
                return {
                    "sentiment": "unsubscribe",
                    "next_action": "stop_outreach",
                    "suggested_reply": "",
                    "opt_out_keyword": keyword,
                }

        prompt = f"""
A Texas homeowner responded to our outreach. Classify and recommend next action.

Our message (attempt {message.attempt_number}): {message.body}
Their response: {response_text}

Classify:
- sentiment: "positive" | "negative" | "neutral" | "unsubscribe"
- next_action: "schedule_call" | "send_follow_up" | "stop_outreach" | "clarify"
- suggested_reply: brief respectful reply (empty string if stopping)

Rules (Section 4):
- ANY hint of disinterest → stop_outreach immediately
- ANY opt-out language → stop_outreach, empty suggested_reply
- Never recommend pushing harder
- suggested_reply must be non-pressuring, informational only
- If uncertain about sentiment → stop_outreach (reputation > conversion)

Return valid JSON with: sentiment, next_action, suggested_reply.
"""
        raw = self._call(prompt)
        try:
            result = json.loads(raw)
            # Safety: if sentiment is negative/unsubscribe, force stop
            if result.get("sentiment") in ("negative", "unsubscribe"):
                result["next_action"] = "stop_outreach"
                result["suggested_reply"] = ""
            return result
        except Exception:
            # Default safe: stop outreach on any parse failure
            return {
                "sentiment": "unknown",
                "next_action": "stop_outreach",
                "suggested_reply": "",
            }

    def run(
        self,
        leads: list[PropertyLead],
        channel: OutreachChannel = OutreachChannel.SMS,
    ) -> list[OutreachMessage]:
        """Draft first-touch messages for a list of leads using approved templates."""
        messages: list[OutreachMessage] = []
        for lead in leads:
            if channel == OutreachChannel.SMS:
                msg = self.draft_sms(lead, attempt_number=1)
            elif channel == OutreachChannel.EMAIL:
                msg = self.draft_email(lead, attempt_number=1)
            else:
                logger.warning(f"[{self.name}] Unsupported channel: {channel}")
                continue
            messages.append(msg)
        return messages
