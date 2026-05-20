"""Regression tests for market-aware ARV fallback behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.deal_analyzer_agent import DealAnalyzerAgent, fallback_price_per_sqft
from tools.batchdata_adapter import CompsResult, PropertyDetails


def _agent_without_real_arv_sources() -> DealAnalyzerAgent:
    agent = DealAnalyzerAgent()
    agent._client = None
    agent.batchdata = MagicMock()
    agent.batchdata.get_comparable_sales.return_value = CompsResult(
        lead_id="lead_123",
        success=False,
    )
    agent.batchdata.get_property_details.return_value = PropertyDetails(
        lead_id="lead_123",
        address="123 Test Ave",
        city="Austin",
        state="TX",
        zip_code="78704",
        success=False,
    )
    return agent


def test_fallback_price_per_sqft_uses_city_and_zip_signals():
    austin_ppsf, austin_source = fallback_price_per_sqft(
        city="Unknown",
        state="TX",
        zip_code="78704",
        beds=3,
    )
    waco_ppsf, waco_source = fallback_price_per_sqft(
        city="Waco",
        state="TX",
        zip_code="76701",
        beds=3,
    )

    assert austin_ppsf > waco_ppsf
    assert austin_source == "TX ZIP prefix 787"
    assert waco_source == "Waco, TX"


def test_deal_analyzer_market_fallback_replaces_flat_statewide_sqft_estimate():
    agent = _agent_without_real_arv_sources()

    analysis = agent.analyze(
        lead_id="lead_123",
        property_address="123 Test Ave",
        city="Austin",
        state="TX",
        zip_code="78704",
        beds=3,
        sqft=2_000,
        condition="minor_repairs",
    )

    assert analysis.arv.mid == 420_000
    assert analysis.arv.confidence == "low"
    assert analysis.arv_source == "heuristic"
    assert "Market-aware heuristic estimate" in analysis.arv.notes
    assert "Austin, TX" in analysis.arv.notes


def test_deal_analyzer_market_fallback_blends_low_tax_assessment_with_market_floor():
    agent = _agent_without_real_arv_sources()

    analysis = agent.analyze(
        lead_id="lead_123",
        property_address="123 Test Ave",
        city="Austin",
        state="TX",
        zip_code="78704",
        beds=3,
        sqft=2_000,
        condition="minor_repairs",
        tax_assessed_value=120_000,
    )

    assert analysis.arv.mid == 357_000
    assert analysis.arv.confidence == "low"
    assert analysis.arv.mid > 120_000 * 1.10
    assert "blended with tax assessment $120,000" in analysis.arv.notes
