from datetime import date, timedelta

from tools.buyer_intelligence_engine import (
    aggregate_transactions, assign_ibie_tier, batch_score_buyers, compute_ibie_score, compute_tags,
)

RECENT = (date.today() - timedelta(days=10)).isoformat()


def buyer(**kw):
    return {"id": "b1", "first_name": "A", "last_name": "B", "cash_buyer": True,
            "avg_purchase_price": 180000, "last_purchase_date": RECENT, **kw}


def test_volume_buyer_outscores_casual_buyer():
    casual = compute_ibie_score(buyer(total_purchases_12mo=2, deals_closed=3))
    volume = compute_ibie_score(buyer(total_purchases_12mo=24, deals_closed=60))
    assert volume > casual + 25


def test_proof_of_funds_and_fast_close_add_bounded_bonus():
    base = compute_ibie_score(buyer(total_purchases_12mo=6, deals_closed=10))
    ready = compute_ibie_score(buyer(total_purchases_12mo=6, deals_closed=10, pof_verified=True, close_speed_days=7))
    assert 9.9 <= ready - base <= 10.1


def test_engagement_delta_is_clamped():
    a = compute_ibie_score(buyer(engagement_delta=500))
    b = compute_ibie_score(buyer(engagement_delta=30))
    assert a == b <= 100


def test_score_bounds_and_tiers():
    assert compute_ibie_score({}) == 0.0
    assert assign_ibie_tier(75) == "A" and assign_ibie_tier(74.9) == "B"
    assert assign_ibie_tier(25) == "C" and assign_ibie_tier(24.9) == "D"


def test_institutional_is_volume_or_known_operator_not_price():
    assert "institutional" in compute_tags(buyer(total_purchases_12mo=14, avg_purchase_price=210000))
    assert "institutional" in compute_tags(buyer(entity_name="Opendoor Property Trust I"))
    # A $600k one-off buyer is not an institution.
    assert "institutional" not in compute_tags(buyer(total_purchases_12mo=1, deals_closed=1, avg_purchase_price=600000))


def test_batch_score_merges_transactions():
    txs = [{"purchase_price": 150000, "purchase_date": RECENT, "cash_transaction": True} for _ in range(5)]
    up = batch_score_buyers([{"id": "b1", "first_name": "A", "last_name": "B"}], {"b1": txs})[0]
    assert up["total_purchases_12mo"] == 5 and up["cash_buyer"] is True and up["ibie_score"] > 0
    assert aggregate_transactions([])["total_purchases_12mo"] == 0
