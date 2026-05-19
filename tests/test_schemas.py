"""Schema validation tests — no API calls required."""

import pytest
from uuid import uuid4

from schemas.property import (
    DataSource,
    DistressSignal,
    NormalizedAddress,
    PropertyLead,
    SIGNAL_WEIGHTS,
)
from schemas.deal import ARVRange, DealStrategy, RehabRange, UnderwritingReport
from schemas.buyer import BuyerProfile, BuyerQualification, BuyerSource, BuyerStrategy
from schemas.outreach import OutreachChannel, OutreachMessage, OutreachStatus
from schemas.compliance import ComplianceCheck, ComplianceFlag, ComplianceStatus


# ── NormalizedAddress ──────────────────────────────────────────────────────────


class TestNormalizedAddress:
    def test_valid_texas_address(self):
        addr = NormalizedAddress(
            street="123 Main St",
            city="Dallas",
            state="TX",
            zip_code="75201",
        )
        assert addr.state == "TX"
        assert "123 Main St" in addr.full

    def test_rejects_non_texas(self):
        with pytest.raises(ValueError, match="Texas"):
            NormalizedAddress(
                street="123 Oak Ave",
                city="Phoenix",
                state="AZ",
                zip_code="85001",
            )

    def test_auto_builds_full(self):
        addr = NormalizedAddress(
            street="456 Elm St", city="Houston", state="TX", zip_code="77001"
        )
        assert addr.full == "456 Elm St, Houston, TX 77001"


# ── PropertyLead ───────────────────────────────────────────────────────────────


class TestPropertyLead:
    def _make_lead(self, **kwargs) -> PropertyLead:
        defaults = dict(
            address=NormalizedAddress(
                street="789 Pine Rd", city="Austin", state="TX", zip_code="78701"
            ),
            owner_name="John Smith",
            source=DataSource.TAX_DELINQUENT,
            source_confidence=0.8,
        )
        defaults.update(kwargs)
        return PropertyLead(**defaults)

    def test_creates_with_defaults(self):
        lead = self._make_lead()
        assert lead.id is not None
        assert lead.flagged is False
        assert lead.distress_score is None

    def test_source_confidence_bounds(self):
        with pytest.raises(Exception):
            self._make_lead(source_confidence=1.5)

        with pytest.raises(Exception):
            self._make_lead(source_confidence=-0.1)


# ── Distress Signals & Weights ─────────────────────────────────────────────────


class TestDistressSignals:
    def test_all_signals_have_weights(self):
        for signal in DistressSignal:
            assert signal in SIGNAL_WEIGHTS, f"Missing weight for {signal}"

    def test_max_score_is_100(self):
        total = sum(SIGNAL_WEIGHTS.values())
        assert total >= 100

    def test_individual_weights(self):
        assert SIGNAL_WEIGHTS[DistressSignal.TAX_DELINQUENT] == 15
        assert SIGNAL_WEIGHTS[DistressSignal.PROBATE_INHERITED] == 25
        assert SIGNAL_WEIGHTS[DistressSignal.HIGH_EQUITY] == 10


# ── UnderwritingReport ─────────────────────────────────────────────────────────


class TestUnderwritingReport:
    def test_mao_calculation(self):
        # MAO = (ARV_low × 0.70) − Rehab_high
        mao = UnderwritingReport.calculate_mao(arv_low=200_000, rehab_high=30_000)
        assert mao == round(200_000 * 0.70 - 30_000, 2)
        assert mao == 110_000.0

    def test_arv_conservative_is_low(self):
        arv = ARVRange(low=180_000, mid=200_000, high=220_000)
        assert arv.conservative == 180_000

    def test_rehab_conservative_is_high(self):
        rehab = RehabRange(low=15_000, mid=25_000, high=40_000)
        assert rehab.conservative == 40_000


# ── BuyerQualification ─────────────────────────────────────────────────────────


class TestBuyerQualification:
    def _make_qual(self) -> BuyerQualification:
        return BuyerQualification(buyer_id=uuid4(), reliability_score=70.0)

    def test_degrade_for_ghost(self):
        qual = self._make_qual()
        qual.degrade_for_ghost()
        assert qual.reliability_score == 55.0
        assert qual.ghost_count == 1

    def test_degrade_for_lowball(self):
        qual = self._make_qual()
        qual.degrade_for_lowball()
        assert qual.reliability_score == 62.0
        assert qual.lowball_count == 1

    def test_upgrade_for_close(self):
        qual = self._make_qual()
        qual.upgrade_for_close(14)
        assert qual.reliability_score == 80.0
        assert qual.total_closes_with_agency == 1
        assert qual.avg_close_days == 14.0

    def test_score_floors_at_zero(self):
        qual = BuyerQualification(buyer_id=uuid4(), reliability_score=5.0)
        for _ in range(5):
            qual.degrade_for_ghost()
        assert qual.reliability_score == 0.0

    def test_score_caps_at_100(self):
        qual = BuyerQualification(buyer_id=uuid4(), reliability_score=95.0)
        qual.upgrade_for_close(7)
        assert qual.reliability_score == 100.0


# ── OutreachMessage ────────────────────────────────────────────────────────────


class TestOutreachMessage:
    def _make_msg(self) -> OutreachMessage:
        return OutreachMessage(
            lead_id=uuid4(),
            channel=OutreachChannel.SMS,
            body="Hi John, I'm a local buyer. Would you be open to a quick chat about your property? Reply STOP to opt out.",
            compliance_cleared=True,
        )

    def test_mark_sent(self):
        msg = self._make_msg()
        assert msg.sent_at is None
        msg.mark_sent()
        assert msg.status == OutreachStatus.SENT
        assert msg.sent_at is not None

    def test_mark_stopped(self):
        msg = self._make_msg()
        msg.mark_stopped("DNC match")
        assert msg.status == OutreachStatus.STOPPED
        assert "DNC" in msg.compliance_notes


# ── ComplianceCheck ────────────────────────────────────────────────────────────


class TestComplianceCheck:
    def test_cleared_status(self):
        check = ComplianceCheck(
            entity_id=uuid4(),
            entity_type="outreach",
            status=ComplianceStatus.CLEARED,
        )
        assert check.is_clear is True

    def test_blocked_status(self):
        check = ComplianceCheck(
            entity_id=uuid4(),
            entity_type="outreach",
            status=ComplianceStatus.BLOCKED,
            flags=[ComplianceFlag.TCPA_QUIET_HOURS],
        )
        assert check.is_clear is False
