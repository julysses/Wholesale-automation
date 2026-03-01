"""
Seller Outreach Agent tests — verify compliance filtering and banned phrase detection.
No real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock

from agents.seller_outreach_agent import (
    SellerOutreachAgent,
    MessageDraft,
    BANNED_PHRASES,
)
from schemas.outreach import OutreachStatus
from schemas.property import DataSource, NormalizedAddress, PropertyLead


def _make_lead() -> PropertyLead:
    return PropertyLead(
        address=NormalizedAddress(
            street="300 Cedar Ln", city="San Antonio", state="TX", zip_code="78201"
        ),
        owner_name="Maria Garcia",
        source=DataSource.TAX_DELINQUENT,
        phone_numbers=["5559876543"],
    )


class TestSellerOutreachAgent:
    def setup_method(self):
        with patch("agents.base_agent.anthropic.Anthropic"):
            self.agent = SellerOutreachAgent()

    def test_clean_message_is_cleared(self):
        lead = _make_lead()
        clean_draft = MessageDraft(
            body="Hi Maria, I'm a local buyer in San Antonio. Would you be open to a quick conversation about your property? Reply STOP to opt out.",
            channel="sms",
            tone_assessment="respectful",
            compliance_notes="",
        )

        with patch.object(self.agent, "_call_structured", return_value=clean_draft):
            msg = self.agent.draft_sms(lead)

        assert msg.compliance_cleared is True
        assert msg.status != OutreachStatus.STOPPED

    def test_banned_phrase_blocks_message(self):
        lead = _make_lead()
        dirty_draft = MessageDraft(
            body="Act now! Limited time cash offer for your property. Don't miss this!",
            channel="sms",
            tone_assessment="aggressive",
            compliance_notes="",
        )
        # On second call, still dirty
        with patch.object(self.agent, "_call_structured", return_value=dirty_draft):
            msg = self.agent.draft_sms(lead)

        assert msg.status == OutreachStatus.STOPPED
        assert not msg.compliance_cleared

    def test_banned_phrases_list_is_comprehensive(self):
        required = ["limited time", "act now", "urgent", "expires", "last chance"]
        for phrase in required:
            assert phrase in BANNED_PHRASES

    def test_check_banned_phrases_case_insensitive(self):
        found = self.agent._check_for_banned_phrases("ACT NOW before it's too late!")
        assert "act now" in found

    def test_email_draft_cleared(self):
        lead = _make_lead()
        clean_draft = MessageDraft(
            body="Subject: A question about your property\n\nHi Maria, I help Texas homeowners explore their options. Would you be open to a brief conversation? You can unsubscribe anytime. — Alex, Texas Property Solutions, 555-0100",
            channel="email",
            tone_assessment="professional",
            compliance_notes="",
        )

        with patch.object(self.agent, "_call_structured", return_value=clean_draft):
            msg = self.agent.draft_email(lead)

        assert msg.compliance_cleared is True

    def test_handle_response_negative_stops_outreach(self):
        lead = _make_lead()
        from schemas.outreach import OutreachChannel, OutreachMessage
        from uuid import uuid4

        msg = OutreachMessage(
            lead_id=uuid4(),
            channel=OutreachChannel.SMS,
            body="Hi Maria...",
        )

        with patch.object(
            self.agent,
            "_call",
            return_value='{"sentiment": "negative", "next_action": "stop_outreach", "suggested_reply": ""}',
        ):
            result = self.agent.handle_response(lead, "Not interested, please remove me", msg)

        assert result["next_action"] == "stop_outreach"
        assert result["sentiment"] == "negative"
