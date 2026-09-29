import time

from tools.lead_scoring_engine import score_lead, score_leads, tier_for_total, detect_signals

STRONG_SFR = dict(property_type="SFR", sqft=1500, bedrooms=3, year_built=1985,
                  estimated_arv=220000, loan_balance=40000, asking_price=140000,
                  owner_phone_1="2145550100", owner_phone_2="2145550101")


def lead(**kw):
    return {"id": "L1", "property_address": "1 Main St", "city": "Dallas", **kw}


def test_stacked_probate_tax_lead_with_buybox_fit_is_hot():
    r = score_lead(lead(source="Probate | Tax Delinquent", motivation_tag="probate", **STRONG_SFR))
    assert r.tier == "HOT" and r.total == 15
    assert r.buybox_fit == "strong"
    assert "probate" in r.signals and "tax_delinquent" in r.signals
    assert r.to_update_payload()["status"] == "qualified_hot"
    assert r.to_update_payload()["precision_tier"] == 1


def test_bare_lead_is_cold_baseline():
    r = score_lead(lead())
    assert r.tier == "COLD" and r.total < 8
    assert all(1 <= v <= 3 for v in r.factors.values())


def test_mobile_home_is_downgraded_even_when_seller_is_motivated():
    good = score_lead(lead(motivation_tag="pre-foreclosure", **STRONG_SFR))
    bad = score_lead(lead(motivation_tag="pre-foreclosure", **{**STRONG_SFR, "property_type": "Mobile Home"}))
    assert bad.buybox_fit == "weak" and bad.factors["score_condition"] == 1
    assert good.total > bad.total


def test_ask_above_seventy_percent_rule_loses_flexibility():
    cheap = score_lead(lead(**{**STRONG_SFR, "asking_price": 150000}))
    pricey = score_lead(lead(**{**STRONG_SFR, "asking_price": 210000}))
    assert cheap.factors["score_flexibility"] > pricey.factors["score_flexibility"]


def test_low_equity_scores_one():
    r = score_lead(lead(estimated_arv=200000, loan_balance=180000))
    assert r.factors["score_equity"] == 1


def test_dnc_lead_never_tiers_hot_and_says_do_not_call():
    r = score_lead(lead(source="Probate | Tax Delinquent", motivation_tag="probate", dnc=True, **STRONG_SFR))
    assert r.tier != "HOT"
    assert "Do not call" in r.next_action


def test_stack_count_parsed_from_import_notes():
    a = score_lead(lead(internal_notes="Imported stack_count=3"))
    b = score_lead(lead())
    assert a.factors["score_motivation"] > b.factors["score_motivation"]


def test_messy_values_do_not_crash():
    r = score_lead(lead(estimated_arv="$220,000", loan_balance="n/a", sqft="1,500 sf", year_built="", asking_price=None))
    assert 5 <= r.total <= 15


def test_signal_detection_handles_variants():
    assert set(detect_signals("Pre-Foreclosure NOD", "Estate of J. Smith")) >= {"pre_foreclosure", "probate"}


def test_tier_boundaries():
    assert tier_for_total(13) == "HOT" and tier_for_total(12) == "WARM"
    assert tier_for_total(8) == "WARM" and tier_for_total(7) == "COLD"


def test_scores_twenty_thousand_leads_in_seconds():
    rows = [lead(id=str(i), source="Tax Delinquent", **STRONG_SFR) for i in range(20000)]
    start = time.perf_counter()
    assert len(score_leads(rows)) == 20000
    assert time.perf_counter() - start < 5
