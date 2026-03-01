"""
Compliance agent tests — covers all Section 4 & 5 enforcement rules.
No real API calls.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from uuid import uuid4

from agents.compliance_logging_agent import (
    ComplianceLoggingAgent,
    ILLEGAL_LOCAL_PHRASES,
    OPT_OUT_KEYWORDS,
)
from config.settings import settings
from schemas.compliance import ComplianceFlag, ComplianceStatus
from schemas.outreach import OutreachChannel, OutreachMessage, OutreachStatus
from schemas.property import DataSource, NormalizedAddress, PropertyLead


def _make_lead(with_phone: bool = True) -> PropertyLead:
    return PropertyLead(
        address=NormalizedAddress(
            street="100 Oak St", city="Dallas", state="TX", zip_code="75201"
        ),
        owner_name="Jane Doe",
        source=DataSource.TAX_DELINQUENT,
        phone_numbers=["5551234567"] if with_phone else [],
    )


def _make_message(cleared: bool = True, is_followup: bool = False,
                  is_inbound: bool = False) -> OutreachMessage:
    return OutreachMessage(
        lead_id=uuid4(),
        channel=OutreachChannel.SMS,
        body="Hi Jane, I live in the area and came across your property. Reply STOP to opt out.",
        compliance_cleared=cleared,
        is_followup=is_followup,
        is_inbound_reply=is_inbound,
    )


@pytest.fixture
def agent():
    with patch("agents.base_agent.anthropic.Anthropic"):
        return ComplianceLoggingAgent()


# ── Opt-out keyword detection ─────────────────────────────────────────────────

class TestOptOutDetection:
    def test_detects_stop(self, agent):
        assert agent.detect_opt_out("STOP") == "stop"

    def test_detects_no(self, agent):
        assert agent.detect_opt_out("No thanks") == "no"

    def test_detects_remove(self, agent):
        result = agent.detect_opt_out("Please REMOVE me")
        assert result is not None and "remove" in result

    def test_detects_unsubscribe(self, agent):
        assert agent.detect_opt_out("unsubscribe") == "unsubscribe"

    def test_detects_not_interested(self, agent):
        assert agent.detect_opt_out("I'm NOT INTERESTED") == "not interested"

    def test_detects_do_not_contact(self, agent):
        assert agent.detect_opt_out("Do not contact me") == "do not contact"

    def test_no_opt_out_in_positive_reply(self, agent):
        assert agent.detect_opt_out("Sure, I'm open to chatting") is None

    def test_opt_out_keywords_covers_all_required(self):
        required = {"stop", "no", "remove", "unsubscribe", "not interested"}
        assert required.issubset(OPT_OUT_KEYWORDS)


class TestOptOutSuppression:
    def test_process_inbound_suppresses_contact(self, agent):
        lead = _make_lead()
        msg = _make_message()
        result = agent.process_inbound_reply(lead, "STOP", msg, "5551234567")
        assert result is True
        assert agent.is_suppressed("5551234567")
        assert msg.status == OutreachStatus.OPTED_OUT
        assert msg.opt_out_detected is True

    def test_suppressed_contact_is_flagged(self, agent):
        lead = _make_lead()
        msg = _make_message()
        # Suppress the contact first
        agent.process_inbound_reply(lead, "STOP", msg, "5551234567")
        # Now check outreach to the same contact
        new_msg = _make_message()
        check = agent.check_outreach(new_msg, lead, 0, contact_identifier="5551234567")
        assert ComplianceFlag.DNC_NO_CONSENT in check.flags
        assert check.auto_halted is True

    def test_positive_reply_does_not_suppress(self, agent):
        lead = _make_lead()
        msg = _make_message()
        result = agent.process_inbound_reply(
            lead, "Yes, I'm open to it", msg, "5551234567"
        )
        assert result is False
        assert not agent.is_suppressed("5551234567")

    def test_opt_out_creates_immutable_record(self, agent):
        lead = _make_lead()
        msg = _make_message()
        agent.process_inbound_reply(lead, "Not interested", msg, "5559876543")
        records = agent.get_opt_out_records()
        assert len(records) == 1
        assert records[0].opt_out_keyword == "not interested"
        assert records[0].phone_or_email == "5559876543"

    def test_no_confirmation_after_opt_out(self, agent):
        """Opt-out records the keyword and suppresses — no follow-up message generated."""
        lead = _make_lead()
        msg = _make_message()
        agent.process_inbound_reply(lead, "STOP", msg, "5551234567")
        # Verify msg is OPTED_OUT, NOT SENT or RESPONDED_POSITIVE
        assert msg.status == OutreachStatus.OPTED_OUT


# ── Texas scheduling checks ───────────────────────────────────────────────────

class TestTexasScheduling:
    def test_blocked_outside_allowed_hours(self, agent):
        lead = _make_lead()
        msg = _make_message()
        # Simulate 8pm Texas time (hour=20) — outside allowed window 9–19
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=20, weekday=MagicMock(return_value=1)  # Tuesday 8pm
            )
            check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.TCPA_QUIET_HOURS in check.flags
        assert check.auto_halted is True

    def test_cleared_during_allowed_hours(self, agent):
        lead = _make_lead()
        msg = _make_message()
        # Simulate 10am Texas time (hour=10) — inside allowed window
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=10, weekday=MagicMock(return_value=1)  # Tuesday 10am
            )
            check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.TCPA_QUIET_HOURS not in check.flags

    def test_blocked_before_9am(self, agent):
        lead = _make_lead()
        msg = _make_message()
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=8, weekday=MagicMock(return_value=2)  # Wednesday 8am
            )
            check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.TCPA_QUIET_HOURS in check.flags

    def test_weekend_sms_blocked(self, agent):
        lead = _make_lead()
        msg = _make_message(is_inbound=False)  # outbound, not seller-initiated
        with patch.object(settings, "sms_weekend_blocked", True):
            with patch("agents.compliance_logging_agent._texas_now") as mock_now:
                mock_now.return_value = MagicMock(
                    hour=12, weekday=MagicMock(return_value=5)  # Saturday noon
                )
                check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.WEEKEND_SMS_BLOCKED in check.flags
        assert check.auto_halted is True

    def test_weekend_sms_allowed_if_inbound_initiated(self, agent):
        lead = _make_lead()
        msg = _make_message(is_inbound=True)  # seller initiated
        with patch.object(settings, "sms_weekend_blocked", True):
            with patch("agents.compliance_logging_agent._texas_now") as mock_now:
                mock_now.return_value = MagicMock(
                    hour=12, weekday=MagicMock(return_value=6)  # Sunday noon
                )
                check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.WEEKEND_SMS_BLOCKED not in check.flags


# ── Follow-up limit (Section 4) ───────────────────────────────────────────────

class TestFollowUpLimit:
    def test_second_followup_blocked_without_reply(self, agent):
        """After 1 follow-up with no reply, block all further outreach."""
        lead = _make_lead()
        # attempt_number=3 = second follow-up = should be blocked
        msg = _make_message(is_followup=True)
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            with patch.object(settings, "max_seller_followups", 1):
                # existing_attempt_count=2 means we've done first_touch + 1 followup
                check = agent.check_outreach(
                    msg, lead,
                    existing_attempt_count=2,
                    has_inbound_reply=False,
                )
        assert ComplianceFlag.FOLLOW_UP_LIMIT_EXCEEDED in check.flags
        assert check.auto_halted is True

    def test_followup_allowed_if_seller_replied(self, agent):
        """If seller has replied, follow-up is allowed within attempt limit."""
        lead = _make_lead()
        msg = _make_message(is_followup=True)
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            check = agent.check_outreach(
                msg, lead,
                existing_attempt_count=1,
                has_inbound_reply=True,
            )
        assert ComplianceFlag.FOLLOW_UP_LIMIT_EXCEEDED not in check.flags

    def test_max_attempts_blocked(self, agent):
        lead = _make_lead()
        msg = _make_message()
        with patch.object(settings, "max_outreach_attempts", 2):
            check = agent.check_outreach(msg, lead, existing_attempt_count=2)
        assert ComplianceFlag.MAX_ATTEMPTS_EXCEEDED in check.flags
        assert check.auto_halted is True


# ── Illegal local language ─────────────────────────────────────────────────────

class TestIllegalLocalLanguage:
    def test_detects_drove_by(self, agent):
        found = agent.check_local_language("I drove by your property yesterday.")
        assert "drove by" in found

    def test_detects_noticed_property(self, agent):
        found = agent.check_local_language("I noticed your property needs some work.")
        assert "noticed your property" in found

    def test_detects_keeping_an_eye(self, agent):
        found = agent.check_local_language("I've been keeping an eye on your home.")
        assert "keeping an eye" in found

    def test_clean_message_passes(self, agent):
        found = agent.check_local_language(
            "I live in the area and came across your property through public records."
        )
        assert len(found) == 0

    def test_illegal_language_in_message_blocks_outreach(self, agent):
        lead = _make_lead()
        msg = OutreachMessage(
            lead_id=lead.id,
            channel=OutreachChannel.SMS,
            body="Hi Jane, I drove by your property and noticed it might need some work.",
            compliance_cleared=True,  # agent tried to clear it — compliance catches it
        )
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.ILLEGAL_LOCAL_LANGUAGE in check.flags
        assert check.auto_halted is True

    def test_illegal_phrases_registry_is_comprehensive(self):
        required = {
            "drove by", "noticed your property", "saw your property",
            "been watching", "keeping an eye", "walked by",
        }
        assert required.issubset(ILLEGAL_LOCAL_PHRASES)


# ── Hard block flags ──────────────────────────────────────────────────────────

class TestHardBlockFlags:
    def test_not_cleared_message_is_blocked(self, agent):
        lead = _make_lead()
        msg = _make_message(cleared=False)
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.HIGH_PRESSURE_LANGUAGE in check.flags
        assert check.auto_halted is True

    def test_no_phone_is_flagged(self, agent):
        lead = _make_lead(with_phone=False)
        msg = _make_message()
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            check = agent.check_outreach(msg, lead, 0)
        assert ComplianceFlag.INVALID_PHONE in check.flags


# ── Audit logging ─────────────────────────────────────────────────────────────

class TestAuditLogging:
    def test_log_grows_with_each_check(self, agent):
        lead = _make_lead()
        initial = len(agent.get_log())
        msg = _make_message()
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            agent.check_outreach(msg, lead, 0)
        assert len(agent.get_log()) == initial + 1

    def test_blocked_status_logged(self, agent):
        lead = _make_lead()
        msg = _make_message(cleared=False)
        with patch("agents.compliance_logging_agent._texas_now") as mock_now:
            mock_now.return_value = MagicMock(
                hour=11, weekday=MagicMock(return_value=1)
            )
            agent.check_outreach(msg, lead, 0)
        log = agent.get_log()
        assert any(e.status == "blocked" for e in log)

    def test_opt_out_suppression_is_logged(self, agent):
        lead = _make_lead()
        msg = _make_message()
        agent.process_inbound_reply(lead, "STOP", msg, "5551234567")
        log = agent.get_log()
        assert any(e.action == "opt_out_suppression" for e in log)

    def test_export_is_serializable(self, agent):
        agent.log_action(agent="test", action="serialization_check")
        exported = agent.export_audit_log()
        assert isinstance(exported, list)
        assert all(isinstance(e, dict) for e in exported)
