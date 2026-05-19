"""
Seller Outreach Agent tests — Sections 4 & 5 enforcement.
Covers: approved templates, local-language rules, follow-up limits, opt-out signals.
"""

import pytest
from unittest.mock import patch, MagicMock

from agents.seller_outreach_agent import (
    SellerOutreachAgent,
    BANNED_PHRASES,
    ILLEGAL_LOCAL_PHRASES,
    OPT_OUT_SIGNALS,
    SELLER_SMS_FIRST_TOUCH_TEMPLATE,
    SELLER_SMS_FOLLOWUP_TEMPLATE,
)
from config.settings import settings
from schemas.outreach import OutreachChannel, OutreachMessage, OutreachStatus
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


@pytest.fixture
def agent():
    with patch("agents.base_agent.anthropic.Anthropic"):
        return SellerOutreachAgent()


# ── Approved template rendering ───────────────────────────────────────────────

class TestApprovedTemplates:
    def test_first_touch_uses_approved_template(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=1)
        assert msg.status != OutreachStatus.STOPPED
        assert "Maria" in msg.body or "there" in msg.body   # owner name or fallback
        assert "live in the area" in msg.body               # approved local phrase

    def test_first_touch_contains_address(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=1)
        assert "300 Cedar Ln" in msg.body or "San Antonio" in msg.body

    def test_first_touch_no_urgency(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=1)
        assert "No rush" in msg.body or "no rush" in msg.body

    def test_first_touch_is_cleared(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=1)
        assert msg.compliance_cleared is True

    def test_followup_uses_followup_template(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=2, has_inbound_reply=False)
        assert msg.status != OutreachStatus.STOPPED
        assert msg.is_followup is True

    def test_followup_contains_opt_out(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=2, has_inbound_reply=False)
        assert "STOP" in msg.body or "stop" in msg.body.lower() or "opt out" in msg.body.lower()

    def test_first_touch_contains_opt_out(self, agent):
        lead = _make_lead()
        msg = agent.draft_sms(lead, attempt_number=1)
        assert "reply stop" in msg.body.lower()


# ── Follow-up limit enforcement (Section 4) ───────────────────────────────────

class TestFollowUpLimit:
    def test_attempt_3_blocked_without_reply(self, agent):
        """Third attempt (2nd follow-up) must be blocked if no seller reply."""
        lead = _make_lead()
        with patch.object(settings, "max_seller_followups", 1):
            msg = agent.draft_sms(lead, attempt_number=3, has_inbound_reply=False)
        assert msg.status == OutreachStatus.STOPPED
        assert "limit" in msg.compliance_notes.lower()

    def test_attempt_3_allowed_with_reply(self, agent):
        """Third attempt is allowed if seller has replied (within total limit)."""
        lead = _make_lead()
        with patch.object(settings, "max_outreach_attempts", 5):
            msg = agent.draft_sms(lead, attempt_number=3, has_inbound_reply=True)
        assert msg.status != OutreachStatus.STOPPED

    def test_follow_up_allowed_checks_correct_limit(self, agent):
        """Verify boundary condition: attempt 2 is the only allowed follow-up."""
        lead = _make_lead()
        with patch.object(settings, "max_seller_followups", 1):
            with patch.object(settings, "max_outreach_attempts", 2):
                msg_1 = agent.draft_sms(lead, attempt_number=1)
                msg_2 = agent.draft_sms(lead, attempt_number=2, has_inbound_reply=False)
                msg_3 = agent.draft_sms(lead, attempt_number=3, has_inbound_reply=False)
        assert msg_1.status != OutreachStatus.STOPPED
        assert msg_2.status != OutreachStatus.STOPPED
        assert msg_3.status == OutreachStatus.STOPPED


# ── Local language enforcement (Section 4) ───────────────────────────────────

class TestLocalLanguageEnforcement:
    def test_illegal_phrase_in_body_blocks_message(self, agent):
        lead = _make_lead()
        # Inject an illegal phrase into the rendered body
        with patch.object(agent, "_render_first_touch_sms",
                          return_value="Hi Maria, I drove by your property. It looks interesting."):
            msg = agent.draft_sms(lead, attempt_number=1)
        assert msg.status == OutreachStatus.STOPPED
        assert not msg.compliance_cleared

    def test_saw_your_property_is_blocked(self, agent):
        lead = _make_lead()
        with patch.object(agent, "_render_first_touch_sms",
                          return_value="Hi Maria, I saw your property on Elm St."):
            msg = agent.draft_sms(lead, attempt_number=1)
        assert msg.status == OutreachStatus.STOPPED

    def test_approved_phrase_passes(self, agent):
        lead = _make_lead()
        body = agent._render_first_touch_sms(lead)
        illegal = agent._check_illegal_local_language(body)
        assert len(illegal) == 0

    def test_illegal_phrases_registry_is_comprehensive(self):
        required = {
            "drove by", "noticed your property", "saw your property",
            "been watching", "keeping an eye", "walked by",
        }
        assert required.issubset(ILLEGAL_LOCAL_PHRASES)


# ── Banned phrase enforcement ─────────────────────────────────────────────────

class TestBannedPhraseEnforcement:
    def test_banned_phrase_blocks_message(self, agent):
        lead = _make_lead()
        with patch.object(agent, "_render_first_touch_sms",
                          return_value="Act now! Limited time offer on your property!"):
            msg = agent.draft_sms(lead, attempt_number=1)
        assert msg.status == OutreachStatus.STOPPED

    def test_banned_phrases_registry_is_comprehensive(self):
        required = {"limited time", "act now", "urgent", "expires", "last chance"}
        assert required.issubset(BANNED_PHRASES)

    def test_clean_message_passes(self, agent):
        lead = _make_lead()
        banned = agent._check_banned_phrases(
            "Hi Maria, I live in the area. Would you be open to a conversation? No rush."
        )
        assert len(banned) == 0

    def test_sms_without_opt_out_is_blocked(self, agent):
        lead = _make_lead()
        with patch.object(
            agent,
            "_render_first_touch_sms",
            return_value="Hi Maria, I live in the area and came across your property.",
        ):
            msg = agent.draft_sms(lead, attempt_number=1)
        assert msg.status == OutreachStatus.STOPPED
        assert "opt-out" in msg.compliance_notes.lower()


# ── Opt-out signal detection ──────────────────────────────────────────────────

class TestOptOutSignals:
    def test_stop_triggers_stop_outreach(self, agent):
        lead = _make_lead()
        msg = OutreachMessage(
            lead_id=lead.id, channel=OutreachChannel.SMS, body="Hi Maria..."
        )
        result = agent.handle_response(lead, "STOP", msg)
        assert result["next_action"] == "stop_outreach"
        assert result["suggested_reply"] == ""
        assert result["sentiment"] == "unsubscribe"

    def test_not_interested_triggers_stop(self, agent):
        lead = _make_lead()
        msg = OutreachMessage(
            lead_id=lead.id, channel=OutreachChannel.SMS, body="Hi Maria..."
        )
        result = agent.handle_response(lead, "not interested", msg)
        assert result["next_action"] == "stop_outreach"

    def test_remove_me_triggers_stop(self, agent):
        lead = _make_lead()
        msg = OutreachMessage(
            lead_id=lead.id, channel=OutreachChannel.SMS, body="Hi Maria..."
        )
        result = agent.handle_response(lead, "Please remove me", msg)
        assert result["next_action"] == "stop_outreach"

    def test_opt_out_signals_registry_complete(self):
        required = {"stop", "no", "remove", "unsubscribe", "not interested"}
        assert required.issubset(OPT_OUT_SIGNALS)

    def test_negative_sentiment_forces_stop(self, agent):
        """Even if Claude classifies as negative (not unsubscribe), we force stop."""
        lead = _make_lead()
        msg = OutreachMessage(
            lead_id=lead.id, channel=OutreachChannel.SMS, body="Hi Maria..."
        )
        with patch.object(
            agent, "_call",
            return_value='{"sentiment": "negative", "next_action": "send_follow_up", "suggested_reply": "Let me explain..."}'
        ):
            result = agent.handle_response(lead, "I don't want to talk about this", msg)
        # Safety override: negative sentiment always stops
        assert result["next_action"] == "stop_outreach"
        assert result["suggested_reply"] == ""


# ── Channel routing ───────────────────────────────────────────────────────────

class TestChannelRouting:
    def test_email_uses_draft_email(self, agent):
        lead = _make_lead()
        draft_mock = MagicMock()
        draft_mock.body = "Subject: A question\n\nHi Maria, I'm local to the area..."
        draft_mock.compliance_notes = ""

        with patch.object(agent, "_call_structured", return_value=draft_mock):
            msg = agent.draft_email(lead, attempt_number=1)

        assert msg.channel == OutreachChannel.EMAIL

    def test_run_uses_sms_by_default(self, agent):
        lead = _make_lead()
        messages = agent.run([lead], channel=OutreachChannel.SMS)
        assert len(messages) == 1
        assert messages[0].channel == OutreachChannel.SMS
