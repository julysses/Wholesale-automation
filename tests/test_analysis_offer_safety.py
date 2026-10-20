"""Underwriting and negotiation cannot establish offer terms."""
import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from agents.deal_analyzer_agent import build_deal_analysis
from agents.negotiation_intelligence_agent import NegotiationIntelligenceAgent
from config.settings import settings


@pytest.mark.parametrize('arv, viable', [(400000, True), (10000, False)])
def test_underwriting_preserves_calculations_without_inventing_purchase_price(arv, viable):
    result = build_deal_analysis('synthetic', 'Test property', arv, arv, arv,
                                 sqft=1500, assignment_fee=15000)
    assert result.arv.low == arv
    assert result.repair.cost_high > 0
    assert result.is_viable == viable
    assert result.mao == max(0, arv * .70 - result.repair.cost_high
                              - result.holding_costs - result.closing_costs - 15000)
    for field in ('offer_range_low', 'offer_range_high', 'projected_assignment_fee', 'deal_spread'):
        assert asdict(result)[field] is None
    assert 'human' in result.offer_range_str
    assert 'Unknown' in result.assignment_fee_str
    assert 'human' in result.summary


@pytest.mark.parametrize('raw', [None, [], {'concern_codes': None}, {
    'concern_codes': ['repairs', 'price', 'price', 'Offer $225000', {}],
    'motivation_level': 'high', 'opening_offer': 225000, 'target_offer': 250000,
    'opening_script': 'Offer $225000 now', 'closing_notes': 'Raise to $250000',
    'pain_points': ['Offer $225000'], 'exit_rationale': 'Pay $250000',
    'custom_objections': [{'objection': 'Price', 'response': 'Pay $250000'}],
}])
def test_model_cannot_inject_prices_or_freeform_offer_scripts(monkeypatch, raw):
    monkeypatch.setattr(settings, 'anthropic_api_key', '')
    agent = NegotiationIntelligenceAgent()
    client = SimpleNamespace(messages=SimpleNamespace(create=MagicMock(return_value=
        SimpleNamespace(content=[SimpleNamespace(text=json.dumps(raw))]))))
    agent._client = client
    result = agent.generate_brief('synthetic', 'Test property', 'Test Owner', 'Seller needs repairs',
                                   210000, 275000).to_dict()
    assert all(result[field] is None for field in ('opening_offer', 'ceiling_offer', 'target_offer'))
    serialized = json.dumps(result)
    assert not any(str(price) in serialized for price in (210000, 225000, 250000, 275000))
    assert 'human' in result['closing_notes']
    prompt = client.messages.create.call_args.kwargs['messages'][0]['content']
    assert '210,000' not in prompt and '275,000' not in prompt
    if isinstance(raw, dict) and raw.get('motivation_level') == 'high':
        assert result['pain_points'] == ['Seller mentioned property repairs', 'Seller mentioned price expectations']
        assert result['motivation_level'] == 'high'


def test_offline_brief_never_calculates_midpoint_or_promises_close(monkeypatch):
    monkeypatch.setattr(settings, 'anthropic_api_key', '')
    result = NegotiationIntelligenceAgent().generate_brief(
        'synthetic', 'Test property', 'Test Owner', '', 210000, 275000,
        sentiment='motivated', timeline='immediately', occupancy='vacant')
    assert result.target_offer is None
    assert result.motivation_level == 'urgent'
    assert result.pain_points
    assert 'two weeks' not in result.opening_script
    assert 'approve' in result.closing_notes
