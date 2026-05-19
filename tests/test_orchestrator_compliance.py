"""Orchestrator compliance integration tests."""

from unittest.mock import patch

from agents.compliance_logging_agent import ComplianceLoggingAgent
from orchestrator import MasterOrchestrator
from schemas.outreach import OutreachChannel, OutreachMessage
from schemas.property import DataSource, NormalizedAddress, PropertyLead
from tools.crm import CRMStore


def _make_lead() -> PropertyLead:
    return PropertyLead(
        address=NormalizedAddress(
            street="100 Oak St", city="Dallas", state="TX", zip_code="75201"
        ),
        owner_name="Jane Doe",
        source=DataSource.TAX_DELINQUENT,
        phone_numbers=["5551234567"],
    )


def test_prepare_outreach_blocks_persisted_suppressed_phone():
    crm = CRMStore(database_url="sqlite:///:memory:")
    lead = _make_lead()
    original_msg = OutreachMessage(
        lead_id=lead.id,
        channel=OutreachChannel.SMS,
        body="Hi Jane, I live in the area. Reply STOP to opt out.",
        compliance_cleared=True,
    )

    with patch("agents.base_agent.anthropic.Anthropic"):
        compliance = ComplianceLoggingAgent(crm_store=crm)
        compliance.process_inbound_reply(lead, "STOP", original_msg, "5551234567")

        orch = MasterOrchestrator()
        orch.compliance = ComplianceLoggingAgent(crm_store=crm)

    with patch("agents.compliance_logging_agent._texas_now") as mock_now:
        mock_now.return_value.hour = 11
        mock_now.return_value.weekday.return_value = 1
        cleared = orch.prepare_outreach([lead], channel=OutreachChannel.SMS)

    assert cleared == []
    assert orch.state.outreach_messages == []
