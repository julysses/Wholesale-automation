"""
Compliance agent tests — no API calls (tests the deterministic logic only).
"""

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4

from agents.compliance_logging_agent import ComplianceLoggingAgent
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


def _make_message(cleared: bool = True) -> OutreachMessage:
    return OutreachMessage(
        lead_id=uuid4(),
        channel=OutreachChannel.SMS,
        body="Hi Jane, would you be open to a quick chat? Reply STOP to opt out.",
        compliance_cleared=cleared,
    )


class TestComplianceLoggingAgent:
    def setup_method(self):
        # Patch the Anthropic client so no real API calls are made
        with patch("agents.base_agent.anthropic.Anthropic"):
            self.agent = ComplianceLoggingAgent()

    def test_cleared_when_all_ok(self):
        lead = _make_lead(with_phone=True)
        msg = _make_message(cleared=True)

        # Patch quiet hours to be outside current time
        with patch.object(settings, "tcpa_quiet_hours_start", 23):
            with patch.object(settings, "tcpa_quiet_hours_end", 0):
                check = self.agent.check_outreach(msg, lead, existing_attempt_count=0)

        assert check.status == ComplianceStatus.CLEARED
        assert check.is_clear is True

    def test_blocked_when_max_attempts_exceeded(self):
        lead = _make_lead()
        msg = _make_message(cleared=True)

        with patch.object(settings, "max_outreach_attempts", 2):
            check = self.agent.check_outreach(msg, lead, existing_attempt_count=2)

        assert ComplianceFlag.MAX_ATTEMPTS_EXCEEDED in check.flags
        assert check.auto_halted is True

    def test_blocked_when_message_not_cleared(self):
        lead = _make_lead()
        msg = _make_message(cleared=False)

        check = self.agent.check_outreach(msg, lead, existing_attempt_count=0)

        assert ComplianceFlag.HIGH_PRESSURE_LANGUAGE in check.flags

    def test_flagged_when_no_phone(self):
        lead = _make_lead(with_phone=False)
        msg = _make_message(cleared=True)

        check = self.agent.check_outreach(msg, lead, existing_attempt_count=0)

        assert ComplianceFlag.INVALID_PHONE in check.flags

    def test_audit_log_grows(self):
        lead = _make_lead()
        msg = _make_message()

        initial_count = len(self.agent.get_log())
        self.agent.check_outreach(msg, lead, existing_attempt_count=0)
        assert len(self.agent.get_log()) == initial_count + 1

    def test_log_action_records_entry(self):
        self.agent.log_action(
            agent="test",
            action="unit_test",
            input_summary="in",
            output_summary="out",
            status="success",
        )
        log = self.agent.get_log()
        assert any(e.action == "unit_test" for e in log)

    def test_export_audit_log_is_serializable(self):
        self.agent.log_action(agent="test", action="serialization_test")
        exported = self.agent.export_audit_log()
        assert isinstance(exported, list)
        assert all(isinstance(e, dict) for e in exported)
