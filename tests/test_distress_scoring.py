"""
Distress Scoring Agent tests.
Tests the deterministic score recalculation logic (no API calls).
"""

import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from agents.distress_scoring_agent import DistressScoringAgent, DistressScoreResult
from config.settings import settings
from schemas.property import (
    DataSource,
    DistressSignal,
    NormalizedAddress,
    PropertyLead,
    SIGNAL_WEIGHTS,
)


def _make_lead(**kwargs) -> PropertyLead:
    defaults = dict(
        address=NormalizedAddress(
            street="200 Maple Ave", city="Houston", state="TX", zip_code="77001"
        ),
        owner_name="Bob Johnson",
        source=DataSource.PROBATE,
    )
    defaults.update(kwargs)
    return PropertyLead(**defaults)


class TestDistressScoringDeterministic:
    """Tests that use mocked Claude responses to verify scoring logic."""

    def setup_method(self):
        with patch("agents.base_agent.anthropic.Anthropic"):
            self.agent = DistressScoringAgent()

    def _mock_score_result(self, signals: list[str]) -> DistressScoreResult:
        return DistressScoreResult(
            lead_id="placeholder",
            score=0,
            signals_present=signals,
            rationale="Mocked rationale",
        )

    def test_score_computed_correctly_from_signals(self):
        lead = _make_lead(
            signals_raw=[DistressSignal.TAX_DELINQUENT, DistressSignal.VACANCY],
            tax_delinquent_amount=5000.0,
            is_vacant=True,
        )

        mock_result = self._mock_score_result(
            ["tax_delinquent", "vacancy"]
        )

        with patch.object(self.agent, "_call_structured", return_value=mock_result):
            with patch.object(settings, "distress_score_threshold", 30):
                result = self.agent.score_lead(lead)

        expected_score = SIGNAL_WEIGHTS[DistressSignal.TAX_DELINQUENT] + SIGNAL_WEIGHTS[DistressSignal.VACANCY]
        assert result.score == expected_score  # 25 + 15 = 40

    def test_passes_threshold(self):
        lead = _make_lead()
        mock_result = self._mock_score_result(
            ["tax_delinquent", "probate_inherited", "high_equity"]
        )

        with patch.object(self.agent, "_call_structured", return_value=mock_result):
            with patch.object(settings, "distress_score_threshold", 45):
                result = self.agent.score_lead(lead)

        # 25 + 20 + 20 = 65
        assert result.score == 65
        assert result.passes_threshold is True

    def test_fails_threshold(self):
        lead = _make_lead()
        mock_result = self._mock_score_result(["vacancy"])  # only 15 points

        with patch.object(self.agent, "_call_structured", return_value=mock_result):
            with patch.object(settings, "distress_score_threshold", 45):
                result = self.agent.score_lead(lead)

        assert result.score == 15
        assert result.passes_threshold is False

    def test_unknown_signal_ignored(self):
        lead = _make_lead()
        mock_result = self._mock_score_result(["tax_delinquent", "UNKNOWN_SIGNAL"])

        with patch.object(self.agent, "_call_structured", return_value=mock_result):
            with patch.object(settings, "distress_score_threshold", 10):
                result = self.agent.score_lead(lead)

        # Only tax_delinquent counts
        assert result.score == 25
        assert "UNKNOWN_SIGNAL" not in result.signals_present

    def test_score_capped_at_100(self):
        lead = _make_lead()
        # Return all signals
        all_signals = [s.value for s in DistressSignal]
        mock_result = self._mock_score_result(all_signals)

        with patch.object(self.agent, "_call_structured", return_value=mock_result):
            with patch.object(settings, "distress_score_threshold", 10):
                result = self.agent.score_lead(lead)

        assert result.score == 100

    def test_run_filters_passing_only(self):
        leads = [_make_lead() for _ in range(3)]

        call_count = 0

        def mock_score(lead):
            nonlocal call_count
            call_count += 1
            score = 60 if call_count == 1 else 20
            passes = score >= 45
            return DistressScoreResult(
                lead_id=str(lead.id),
                score=score,
                signals_present=[],
                rationale="mock",
                passes_threshold=passes,
            )

        with patch.object(self.agent, "score_lead", side_effect=mock_score):
            passing = self.agent.run(leads)

        assert len(passing) == 1


class TestSignalWeights:
    def test_total_is_100(self):
        assert sum(SIGNAL_WEIGHTS.values()) == 100

    def test_all_signals_covered(self):
        for sig in DistressSignal:
            assert sig in SIGNAL_WEIGHTS
