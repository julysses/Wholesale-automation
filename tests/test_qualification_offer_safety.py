"""Seller facts must never be converted to acquisition prices."""
import pytest
from agents.qualification_agent import QualificationAgent
from config.settings import settings


@pytest.mark.parametrize("llm", [False, True])
def test_qualification_preserves_seller_facts_without_pricing(monkeypatch, llm):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    agent = QualificationAgent()
    raw = dict(asking_price=300000, named_price=True, timeline="immediately",
               occupancy="vacant", condition="major_repairs", sentiment="motivated",
               offer_range_low=210000, offer_range_high=255000)
    if llm:
        agent._client = object()
        monkeypatch.setattr(agent, "_llm_analyze", lambda *_: raw)
    else:
        monkeypatch.setattr(agent, "_heuristic_analyze", lambda *_: raw)
    result = agent.analyze_transcript("Seller asks $300,000 and wants to sell immediately.")
    assert result.asking_price == 300000
    assert result.qualification_score == 85
    assert result.classification == "HOT"
    assert result.offer_range_low is None
    assert result.offer_range_high is None
