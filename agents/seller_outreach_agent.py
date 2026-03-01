"""Seller Outreach Agent — ethical, pressure-free communications only."""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from schemas.outreach import OutreachChannel, OutreachMessage, OutreachStatus
from schemas.property import PropertyLead
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Hard-coded banned phrases — model may never include these
BANNED_PHRASES = [
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
    "pressure",
    "deal ends",
    "only a few",
]


class MessageDraft(BaseModel):
    body: str
    channel: str
    tone_assessment: str
    compliance_notes: str


class SellerOutreachAgent(BaseAgent):
    name = "seller_outreach_agent"
    system_prompt = SystemPrompts.SELLER_OUTREACH

    def _check_for_banned_phrases(self, text: str) -> list[str]:
        found = []
        lower = text.lower()
        for phrase in BANNED_PHRASES:
            if phrase in lower:
                found.append(phrase)
        return found

    def draft_sms(
        self,
        lead: PropertyLead,
        attempt_number: int = 1,
        context: str = "",
    ) -> OutreachMessage:
        """Draft a first-touch or follow-up SMS for a seller lead."""
        prompt = f"""
Draft a {attempt_number}-touch SMS to a Texas homeowner.

Property: {lead.address.full}
Owner name: {lead.owner_name}
Attempt number: {attempt_number}
Additional context: {context if context else "None"}

Requirements:
- Maximum 160 characters for SMS
- Introduce yourself briefly as a Texas property buyer
- Frame it as: we may be able to help / would you be open to a conversation?
- NO pressure, NO urgency, NO guarantees
- Include an easy opt-out option ("Reply STOP to opt out")
- Tone: neighborly, respectful, peer-to-peer

Return tone_assessment (1 sentence) and compliance_notes (any issues flagged).
Return channel as "sms".
"""
        draft = self._call_structured(prompt, MessageDraft)

        # Hard compliance check before any send
        violations = self._check_for_banned_phrases(draft.body)
        if violations:
            logger.warning(
                f"[{self.name}] Draft contained banned phrases for {lead.id}: {violations}"
            )
            # Regenerate once with explicit violation callout
            prompt += f"\n\nPREVIOUS DRAFT FAILED: contained banned phrases: {violations}. Remove them."
            draft = self._call_structured(prompt, MessageDraft)
            violations = self._check_for_banned_phrases(draft.body)

        msg = OutreachMessage(
            lead_id=lead.id,
            channel=OutreachChannel.SMS,
            body=draft.body,
            attempt_number=attempt_number,
            compliance_notes=draft.compliance_notes,
        )

        if violations:
            msg.compliance_notes += f" [BLOCKED — banned phrases: {violations}]"
            msg.status = OutreachStatus.STOPPED
            logger.error(
                f"[{self.name}] Message blocked for lead {lead.id}: still contains banned phrases"
            )
        else:
            msg.compliance_cleared = True

        logger.info(f"[{self.name}] Drafted SMS for lead {lead.id}, attempt {attempt_number}")
        return msg

    def draft_email(
        self,
        lead: PropertyLead,
        attempt_number: int = 1,
        context: str = "",
    ) -> OutreachMessage:
        """Draft an outreach email."""
        prompt = f"""
Draft a seller outreach email to a Texas homeowner.

Property: {lead.address.full}
Owner name: {lead.owner_name}
Attempt number: {attempt_number}
Additional context: {context if context else "None"}

Requirements:
- Subject line should be warm and non-salesy (5–8 words max)
- Body: 3–4 short sentences max
- Frame as: you may have options / we help homeowners explore their choices
- NO pressure, NO urgency, NO guarantees
- Include unsubscribe option
- Sign with a real first name + company + phone
- Combine subject into body as "Subject: ... \\n\\n Body: ..."

Return tone_assessment and compliance_notes.
Return channel as "email".
"""
        draft = self._call_structured(prompt, MessageDraft)
        violations = self._check_for_banned_phrases(draft.body)

        msg = OutreachMessage(
            lead_id=lead.id,
            channel=OutreachChannel.EMAIL,
            body=draft.body,
            attempt_number=attempt_number,
            compliance_notes=draft.compliance_notes,
        )

        if violations:
            msg.compliance_notes += f" [BLOCKED — banned phrases: {violations}]"
            msg.status = OutreachStatus.STOPPED
        else:
            msg.compliance_cleared = True

        return msg

    def handle_response(
        self,
        lead: PropertyLead,
        response_text: str,
        message: OutreachMessage,
    ) -> dict:
        """
        Classify a seller's response and recommend next step.
        Returns dict with: sentiment, next_action, suggested_reply.
        """
        prompt = f"""
A Texas homeowner responded to our outreach. Classify their response and recommend the right next step.

Our message: {message.body}
Their response: {response_text}

Classify:
- sentiment: "positive" | "negative" | "neutral" | "unsubscribe"
- next_action: "schedule_call" | "send_follow_up" | "stop_outreach" | "clarify"
- suggested_reply: a brief, respectful reply (or empty string if stopping)

Rules:
- If ANY hint of disinterest or opt-out, recommend stop_outreach immediately
- Never suggest pushing harder
- Tone of suggested_reply must remain non-pressuring

Return valid JSON with: sentiment, next_action, suggested_reply.
"""
        raw = self._call(prompt)
        import json
        try:
            return json.loads(raw)
        except Exception:
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
        """Draft first-touch messages for a list of leads."""
        messages: list[OutreachMessage] = []
        for lead in leads:
            if channel == OutreachChannel.SMS:
                msg = self.draft_sms(lead)
            elif channel == OutreachChannel.EMAIL:
                msg = self.draft_email(lead)
            else:
                logger.warning(f"[{self.name}] Unsupported channel: {channel}")
                continue
            messages.append(msg)
        return messages
