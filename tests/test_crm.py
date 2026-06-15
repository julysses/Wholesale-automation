"""
CRM Store tests — uses in-memory SQLite.
"""

import pytest
from uuid import uuid4

from schemas.buyer import BuyerProfile, BuyerQualification, BuyerSource, BuyerStrategy
from schemas.compliance import AuditLogEntry
from schemas.deal import Deal, DealStatus
from schemas.property import DataSource, NormalizedAddress, PropertyLead
from tools.crm import CRMStore


@pytest.fixture
def crm():
    """In-memory SQLite CRM for testing."""
    return CRMStore(database_url="sqlite:///:memory:")


def _make_lead() -> PropertyLead:
    return PropertyLead(
        address=NormalizedAddress(
            street="100 Test St", city="Dallas", state="TX", zip_code="75201"
        ),
        owner_name="Test Owner",
        source=DataSource.TAX_DELINQUENT,
        source_confidence=0.9,
    )


def _make_buyer() -> tuple[BuyerProfile, BuyerQualification]:
    profile = BuyerProfile(
        name="Test Buyer",
        company="Test Investments LLC",
        source=BuyerSource.BIGGER_POCKETS,
        markets=["Dallas", "Houston"],
        strategies=[BuyerStrategy.FIX_AND_FLIP],
        price_min=50_000,
        price_max=200_000,
        proof_of_funds=True,
    )
    qual = BuyerQualification(
        buyer_id=profile.id,
        reliability_score=75.0,
    )
    return profile, qual


class TestCRMStore:
    def test_save_and_retrieve_lead(self, crm):
        lead = _make_lead()
        crm.save_lead(lead)

        result = crm.get_lead(str(lead.id))
        assert result is not None
        assert result["owner_name"] == "Test Owner"
        assert result["source"] == "tax_delinquent"

    def test_get_all_leads(self, crm):
        lead1 = _make_lead()
        lead2 = _make_lead()
        crm.save_lead(lead1)
        crm.save_lead(lead2)

        all_leads = crm.get_all_leads()
        assert len(all_leads) == 2

    def test_save_and_retrieve_deal(self, crm):
        lead = _make_lead()
        deal = Deal(lead_id=lead.id, status=DealStatus.UNDERWRITING)
        crm.save_deal(deal)

        active = crm.get_active_deals()
        assert len(active) == 1
        assert active[0]["status"] == "underwriting"

    def test_closed_deals_excluded_from_active(self, crm):
        lead = _make_lead()
        deal = Deal(lead_id=lead.id, status=DealStatus.CLOSED)
        crm.save_deal(deal)

        active = crm.get_active_deals()
        assert len(active) == 0

    def test_save_and_retrieve_buyer(self, crm):
        profile, qual = _make_buyer()
        crm.save_buyer(profile, qual)

        active = crm.get_active_buyers()
        assert len(active) == 1
        assert active[0]["name"] == "Test Buyer"
        assert active[0]["reliability_score"] == 75.0

    def test_disqualified_buyer_excluded(self, crm):
        profile, qual = _make_buyer()
        qual.disqualified = True
        crm.save_buyer(profile, qual)

        active = crm.get_active_buyers()
        assert len(active) == 0

    def test_save_and_retrieve_audit_entry(self, crm):
        entry = AuditLogEntry(
            agent="test_agent",
            action="test_action",
            input_summary="test input",
            output_summary="test output",
            status="success",
        )
        crm.save_audit_entry(entry)

        log = crm.get_audit_log()
        assert len(log) == 1
        assert log[0]["agent"] == "test_agent"
        assert log[0]["action"] == "test_action"

    def test_audit_log_filtered_by_agent(self, crm):
        for agent in ["agent_a", "agent_b", "agent_a"]:
            crm.save_audit_entry(
                AuditLogEntry(agent=agent, action="test")
            )

        a_log = crm.get_audit_log(agent="agent_a")
        assert len(a_log) == 2

    def test_lead_upsert(self, crm):
        lead = _make_lead()
        crm.save_lead(lead)
        lead.distress_score = 75
        crm.save_lead(lead)  # should update, not duplicate

        all_leads = crm.get_all_leads()
        assert len(all_leads) == 1
        assert all_leads[0]["distress_score"] == 75

    def test_dedup_on_import_collapses_same_address(self, crm):
        first = _make_lead()
        second = _make_lead()  # same address, different id
        assert first.id != second.id

        assert crm.save_lead(first, dedup=True) is True    # new
        assert crm.save_lead(second, dedup=True) is False  # duplicate updated

        all_leads = crm.get_all_leads()
        assert len(all_leads) == 1
        # The original row id is preserved
        assert str(all_leads[0]["id"]) == str(first.id)

    def test_dedup_disabled_allows_duplicates(self, crm):
        crm.save_lead(_make_lead())  # default dedup=False
        crm.save_lead(_make_lead())
        assert len(crm.get_all_leads()) == 2

    def test_find_lead_by_address_case_insensitive(self, crm):
        lead = _make_lead()
        crm.save_lead(lead)
        found = crm.find_lead_by_address(lead.address.full.upper())
        assert found is not None
        assert str(found["id"]) == str(lead.id)
        assert crm.find_lead_by_address("999 Nowhere Ave") is None
