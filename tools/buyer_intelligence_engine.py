"""
Investor Buyer Intelligence Engine (IBIE) — Core Scoring & Matching.

This module is the computational heart of the IBIE system.  It runs
entirely in Python with no external API calls — all scoring uses the
transaction data already stored in Supabase.

Responsibilities:
  1. IBIE Score computation (0–100, 5-factor weighted formula)
  2. IBIE Tier assignment (A/B/C/D based on score bands)
  3. Auto-tag / segmentation (entry_flip, portfolio_landlord, etc.)
  4. Deal matching  (zip + price + type filter, sorted by ibie_score)
  5. Score decay     (weekly: ignoring 5+ outreach → score drops)
  6. Batch re-score  (run over all buyers, update Supabase in bulk)

Score formula (PRD spec):
  score =
    (purchase_frequency * 0.30) +   # deals last 12 months → 0-100
    (recency_weight     * 0.25) +   # last purchase date   → 0-100
    (cash_buyer_bonus   * 0.20) +   # cash purchase flag   → 0 or 100
    (volume_weight      * 0.15) +   # all-time deals count → 0-100
    (price_alignment    * 0.10)     # avg price vs our range → 0-100

Engagement adjustments (applied after base score):
  +5  per closed deal with us
  +3  per positive response (interested / callback)
  -2  per ignored outreach (capped at -20 from ignores)

Tier bands:
  A  ≥ 75
  B  50 – 74
  C  25 – 49
  D  < 25
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Our typical deal price range — used for price alignment scoring
DEFAULT_DEAL_PRICE_MIN: int = 80_000
DEFAULT_DEAL_PRICE_MAX: int = 250_000

# Tier score thresholds
TIER_A = 75
TIER_B = 50
TIER_C = 25

# Score weights (must sum to 1.0)
W_FREQUENCY  = 0.30
W_RECENCY    = 0.25
W_CASH       = 0.20
W_VOLUME     = 0.15
W_PRICE_ALIGN = 0.10

# Segmentation constants
FLIPPER_PRICE_CAP     = 300_000
INSTITUTIONAL_PRICE   = 500_000
INSTITUTIONAL_DEALS   = 10
PORTFOLIO_LANDLORD_MIN = 10

# Engagement deltas
DELTA_CLOSED_DEAL  = 5.0
DELTA_RESPONDED    = 3.0
DELTA_IGNORED      = -2.0
MAX_IGNORE_PENALTY = -20.0


# ── Score factor functions ────────────────────────────────────────────────────

def _frequency_score(purchases_12mo: int) -> float:
    """Normalize purchases in last 12 months against a cap of 12 deals/year."""
    return min(purchases_12mo / 12 * 100, 100.0)


def _recency_score(last_purchase_date: Optional[date]) -> float:
    """
    Score based on days since last purchase:
      ≤ 30 days  → 100
      ≤ 90 days  → 75
      ≤ 180 days → 50
      ≤ 365 days → 25
      > 365 days → 0   (or no date on record)
    """
    if not last_purchase_date:
        return 0.0
    today = date.today()
    # Accept both date and datetime objects
    if isinstance(last_purchase_date, datetime):
        last_purchase_date = last_purchase_date.date()
    days = (today - last_purchase_date).days
    if days <= 30:
        return 100.0
    if days <= 90:
        return 75.0
    if days <= 180:
        return 50.0
    if days <= 365:
        return 25.0
    return 0.0


def _cash_score(is_cash_buyer: bool) -> float:
    return 100.0 if is_cash_buyer else 0.0


def _volume_score(all_time_deals: int, cap: int = 20) -> float:
    """Normalize total all-time deals against a cap of 20."""
    return min(all_time_deals / cap * 100, 100.0)


def _price_alignment_score(
    avg_purchase_price: Optional[float],
    deal_min: int = DEFAULT_DEAL_PRICE_MIN,
    deal_max: int = DEFAULT_DEAL_PRICE_MAX,
) -> float:
    """
    Full score (100) if avg price is within our deal range.
    Tapers linearly to 0 as avg_price moves further from range edges.
    """
    if not avg_purchase_price or avg_purchase_price <= 0:
        return 0.0
    if deal_min <= avg_purchase_price <= deal_max:
        return 100.0
    if avg_purchase_price < deal_min:
        gap = deal_min - avg_purchase_price
        return max(0.0, 100.0 - (gap / deal_min * 100))
    # avg_purchase_price > deal_max
    gap = avg_purchase_price - deal_max
    return max(0.0, 100.0 - (gap / deal_max * 100))


# ── Main scoring function ────────────────────────────────────────────────────

def compute_ibie_score(
    buyer: dict[str, Any],
    deal_price_min: int = DEFAULT_DEAL_PRICE_MIN,
    deal_price_max: int = DEFAULT_DEAL_PRICE_MAX,
) -> float:
    """
    Compute the IBIE score (0–100) for a single buyer record.

    `buyer` is a dict matching the Supabase `buyers` row shape.
    Returns a rounded float to 2 decimal places.
    """
    purchases_12mo   = int(buyer.get("total_purchases_12mo") or 0)
    all_time_deals   = int(buyer.get("deals_closed") or 0)
    is_cash          = bool(buyer.get("cash_buyer", False))
    avg_price        = _safe_float(buyer.get("avg_purchase_price"))
    last_buy_raw     = buyer.get("last_purchase_date")
    ignore_count     = int(buyer.get("outreach_ignore_count") or 0)
    engagement_delta = float(buyer.get("engagement_delta") or 0.0)

    # Parse last_purchase_date
    last_purchase: Optional[date] = None
    if last_buy_raw:
        if isinstance(last_buy_raw, (date, datetime)):
            last_purchase = last_buy_raw if isinstance(last_buy_raw, date) else last_buy_raw.date()
        else:
            try:
                last_purchase = date.fromisoformat(str(last_buy_raw)[:10])
            except (ValueError, TypeError):
                last_purchase = None

    # Weighted base score
    base = (
        _frequency_score(purchases_12mo) * W_FREQUENCY +
        _recency_score(last_purchase)    * W_RECENCY +
        _cash_score(is_cash)             * W_CASH +
        _volume_score(all_time_deals)    * W_VOLUME +
        _price_alignment_score(avg_price, deal_price_min, deal_price_max) * W_PRICE_ALIGN
    )

    # Engagement adjustment: ignore penalty capped at MAX_IGNORE_PENALTY
    ignore_penalty = max(ignore_count * DELTA_IGNORED, MAX_IGNORE_PENALTY)
    adjusted = base + engagement_delta + ignore_penalty

    return round(max(0.0, min(100.0, adjusted)), 2)


def assign_ibie_tier(score: float) -> str:
    """Map a 0–100 score to an A/B/C/D tier."""
    if score >= TIER_A:
        return "A"
    if score >= TIER_B:
        return "B"
    if score >= TIER_C:
        return "C"
    return "D"


# ── Segmentation / Auto-tagging ───────────────────────────────────────────────

def compute_tags(buyer: dict[str, Any]) -> list[str]:
    """
    Auto-generate behavioral tags for a buyer.
    Existing tags are preserved; only system-generated tags are refreshed.
    """
    system_tags = {
        "entry_flip", "mid_flip", "portfolio_landlord", "small_landlord",
        "institutional", "cash_buyer", "repeat_buyer",
        "new_buyer", "high_volume", "dormant",
    }
    # Keep any manually added custom tags
    existing = [t for t in (buyer.get("tags") or []) if t not in system_tags]
    tags = list(existing)

    buyer_type = (buyer.get("buyer_type_ibie") or "").lower()
    avg_price  = _safe_float(buyer.get("avg_purchase_price")) or 0
    props      = int(buyer.get("properties_owned") or 0)
    deals      = int(buyer.get("deals_closed") or 0)
    purchases  = int(buyer.get("total_purchases_12mo") or 0)
    is_cash    = bool(buyer.get("cash_buyer", False))
    is_repeat  = bool(buyer.get("repeat_buyer", False))

    # Flip tags
    if buyer_type == "flipper":
        if avg_price < FLIPPER_PRICE_CAP:
            tags.append("entry_flip")
        else:
            tags.append("mid_flip")

    # Landlord tags
    if buyer_type == "landlord":
        if props > PORTFOLIO_LANDLORD_MIN:
            tags.append("portfolio_landlord")
        elif props >= 2:
            tags.append("small_landlord")

    # Institutional
    if avg_price > INSTITUTIONAL_PRICE and deals > INSTITUTIONAL_DEALS:
        tags.append("institutional")

    # Activity tags
    if is_cash:
        tags.append("cash_buyer")
    if is_repeat:
        tags.append("repeat_buyer")
    if deals == 0 and purchases == 0:
        tags.append("new_buyer")
    if purchases >= 6:
        tags.append("high_volume")

    # Dormancy (no purchase in > 12 months)
    last_raw = buyer.get("last_purchase_date")
    if last_raw:
        try:
            ld = date.fromisoformat(str(last_raw)[:10])
            if (date.today() - ld).days > 365:
                tags.append("dormant")
        except (ValueError, TypeError):
            pass

    return sorted(set(tags))


# ── Deal Matching Engine ───────────────────────────────────────────────────────

@dataclass
class DealMatchInput:
    """Normalized deal attributes used for buyer matching."""
    deal_id: str
    zip_code: str = ""
    buyer_price: float = 0.0         # asking price for the deal (MAO or assignment price)
    property_type: str = ""
    condition: str = ""              # distressed | cosmetic | turnkey | any
    arv: float = 0.0
    city: str = ""
    market: str = ""


@dataclass
class BuyerMatchResult:
    """A single buyer → deal match with factor breakdown."""
    buyer_id: str
    buyer_name: str
    phone: str = ""
    email: str = ""
    company: str = ""
    ibie_score: float = 0.0
    zip_score: float = 0.0
    price_score: float = 0.0
    type_score: float = 0.0
    match_score: float = 0.0        # weighted composite
    rank: int = 0
    tags: list[str] = field(default_factory=list)
    match_reasons: list[str] = field(default_factory=list)
    buyer_row: dict[str, Any] = field(default_factory=dict)


def match_buyers_to_deal(
    deal: DealMatchInput,
    buyers: list[dict[str, Any]],
    limit: int = 50,
    deal_price_tolerance: float = 0.20,
) -> list[BuyerMatchResult]:
    """
    Match and rank buyers against a deal.

    Filter criteria:
      - buyer is active
      - zip_code is in buyer's target_zips (or buyer has no zip restriction)
      - deal.buyer_price is within buyer price range ± tolerance
      - deal.property_type matches buyer's property_types (or buyer has none set)

    Scoring per match:
      zip_score   = 100 if exact zip match, 80 if no zip filter, 0 otherwise
      price_score = 100 if within range, tapers to 0 at edge of tolerance
      type_score  = 100 if type matches, 80 if no type filter, 0 otherwise
      match_score = zip_score*0.30 + price_score*0.40 + type_score*0.10 +
                    buyer.ibie_score*0.20
    """
    results: list[BuyerMatchResult] = []

    for b in buyers:
        if not b.get("active", True):
            continue

        # ── Zip filter ────────────────────────────────────────────────────────
        target_zips = b.get("target_zips") or []
        if target_zips:
            if deal.zip_code and deal.zip_code in target_zips:
                zip_score = 100.0
            elif not deal.zip_code:
                zip_score = 50.0
            else:
                zip_score = 0.0
        else:
            # Buyer has no zip restriction — still a valid match, slightly penalized
            zip_score = 80.0

        # ── Price filter ──────────────────────────────────────────────────────
        b_min  = _safe_float(b.get("min_price")) or 0
        b_max  = _safe_float(b.get("max_price")) or 0
        b_avg  = _safe_float(b.get("avg_purchase_price")) or 0
        d_price = deal.buyer_price

        if b_min > 0 and b_max > 0:
            lo = b_min * (1 - deal_price_tolerance)
            hi = b_max * (1 + deal_price_tolerance)
            if lo <= d_price <= hi:
                price_score = 100.0 if b_min <= d_price <= b_max else 60.0
            else:
                price_score = 0.0
        elif b_avg > 0:
            # Use avg purchase price ± tolerance as proxy range
            if b_avg * (1 - deal_price_tolerance) <= d_price <= b_avg * (1 + deal_price_tolerance):
                price_score = 100.0
            else:
                price_score = 0.0
        else:
            price_score = 40.0  # no price data — neutral

        # Hard price exclusion: if deal price is 0 or buyer is way out of range, skip
        if d_price > 0 and b_max > 0 and d_price > b_max * 1.5:
            continue
        if d_price > 0 and b_min > 0 and d_price < b_min * 0.5:
            continue

        # ── Property type filter ─────────────────────────────────────────────
        buyer_types = [t.upper() for t in (b.get("property_types") or [])]
        if buyer_types:
            if deal.property_type and deal.property_type.upper() in buyer_types:
                type_score = 100.0
            elif not deal.property_type:
                type_score = 70.0
            else:
                type_score = 0.0
        else:
            type_score = 80.0

        # ── Market filter (optional) ─────────────────────────────────────────
        if deal.market and b.get("market") and b["market"] != deal.market:
            continue  # hard exclude cross-market mismatch

        ibie = _safe_float(b.get("ibie_score")) or 0.0

        # ── Composite match score ────────────────────────────────────────────
        match_score = round(
            zip_score   * 0.30 +
            price_score * 0.40 +
            type_score  * 0.10 +
            ibie        * 0.20,
            2,
        )

        reasons: list[str] = []
        if zip_score == 100:
            reasons.append(f"Buys in {deal.zip_code}")
        if price_score >= 100:
            reasons.append("Price within buy box")
        if type_score == 100:
            reasons.append(f"Buys {deal.property_type}")
        if b.get("cash_buyer"):
            reasons.append("Cash buyer")
        if b.get("repeat_buyer"):
            reasons.append("Repeat buyer")
        if ibie >= 75:
            reasons.append(f"IBIE A-tier ({ibie:.0f})")

        results.append(BuyerMatchResult(
            buyer_id=b["id"],
            buyer_name=f"{b.get('first_name', '')} {b.get('last_name', '')}".strip(),
            phone=b.get("phone", ""),
            email=b.get("email", ""),
            company=b.get("company", ""),
            ibie_score=ibie,
            zip_score=zip_score,
            price_score=price_score,
            type_score=type_score,
            match_score=match_score,
            tags=b.get("tags") or [],
            match_reasons=reasons,
            buyer_row=b,
        ))

    results.sort(key=lambda r: r.match_score, reverse=True)
    for i, r in enumerate(results[:limit]):
        r.rank = i + 1

    return results[:limit]


# ── Transaction aggregation ───────────────────────────────────────────────────

def aggregate_transactions(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute buyer-level signals from a list of their transaction records.

    Returns a dict ready to be merged into the buyers table row.
    """
    if not transactions:
        return {
            "total_purchases_12mo": 0,
            "properties_owned": 0,
            "avg_purchase_price": None,
            "last_purchase_date": None,
            "cash_buyer": False,
            "repeat_buyer": False,
        }

    cutoff_12mo = date.today() - timedelta(days=365)
    prices: list[float] = []
    last_date: Optional[date] = None
    purchases_12mo = 0
    cash_count = 0
    flip_count = 0

    for tx in transactions:
        price = _safe_float(tx.get("purchase_price"))
        if price and price > 0:
            prices.append(price)

        raw_date = tx.get("purchase_date")
        if raw_date:
            try:
                tx_date = date.fromisoformat(str(raw_date)[:10])
            except (ValueError, TypeError):
                tx_date = None
            if tx_date:
                if last_date is None or tx_date > last_date:
                    last_date = tx_date
                if tx_date >= cutoff_12mo:
                    purchases_12mo += 1

        if tx.get("cash_transaction"):
            cash_count += 1
        if tx.get("flip_detected"):
            flip_count += 1

    total = len(transactions)
    cash_rate = cash_count / total if total else 0

    return {
        "total_purchases_12mo": purchases_12mo,
        "properties_owned": total,
        "avg_purchase_price": round(sum(prices) / len(prices), 2) if prices else None,
        "last_purchase_date": last_date.isoformat() if last_date else None,
        "cash_buyer": cash_rate >= 0.5,          # majority cash = cash buyer
        "repeat_buyer": total >= 2,
    }


# ── Batch re-scoring ──────────────────────────────────────────────────────────

def batch_score_buyers(
    buyers: list[dict[str, Any]],
    transactions_by_buyer: dict[str, list[dict[str, Any]]],
    deal_price_min: int = DEFAULT_DEAL_PRICE_MIN,
    deal_price_max: int = DEFAULT_DEAL_PRICE_MAX,
) -> list[dict[str, Any]]:
    """
    Score + tag every buyer in the list.

    `transactions_by_buyer` is a dict keyed by buyer_id with a list of
    their transaction rows.

    Returns a list of update dicts: { id, ibie_score, ibie_tier, tags,
    cash_buyer, repeat_buyer, total_purchases_12mo, ... }
    """
    updates: list[dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for b in buyers:
        bid = b["id"]
        txs = transactions_by_buyer.get(bid, [])

        # Merge transaction-derived signals into buyer snapshot
        tx_signals = aggregate_transactions(txs)
        enriched = {**b, **tx_signals}

        score = compute_ibie_score(enriched, deal_price_min, deal_price_max)
        tier  = assign_ibie_tier(score)
        tags  = compute_tags(enriched)

        updates.append({
            "id":                  bid,
            "ibie_score":          score,
            "ibie_tier":           tier,
            "tags":                tags,
            "last_scored_at":      now_iso,
            "score_version":       int(b.get("score_version") or 0) + 1,
            **{k: tx_signals[k] for k in tx_signals},
        })

    return updates


# ── Outreach templates ────────────────────────────────────────────────────────

def build_deal_sms(
    buyer_name: str,
    zip_code: str,
    price: float,
    property_type: str = "property",
    beds: int = 0,
    baths: float = 0,
) -> str:
    """Generate the deal-blast SMS body."""
    name = buyer_name.split()[0] if buyer_name else "there"
    price_str = f"${price:,.0f}" if price else "TBD"
    prop_desc = f"{beds}bd/{baths}ba {property_type}" if beds else property_type
    return (
        f"Hey {name}, I've got an off-market {prop_desc} in {zip_code} — "
        f"asking {price_str}. Want the details?"
    )


def build_deal_email(
    buyer_name: str,
    property_address: str,
    zip_code: str,
    price: float,
    arv: float,
    assignment_fee: float,
    property_type: str = "property",
    beds: int = 0,
    baths: float = 0,
    condition: str = "",
    sender_name: str = "Alex",
    agency_name: str = "Texas Wholesale Solutions",
) -> tuple[str, str]:
    """Return (subject, html_body) for the deal-blast email."""
    name = buyer_name.split()[0] if buyer_name else "Investor"
    price_str = f"${price:,.0f}" if price else "TBD"
    arv_str   = f"${arv:,.0f}"   if arv   else "TBD"
    fee_str   = f"${assignment_fee:,.0f}" if assignment_fee else "TBD"
    prop_desc = f"{beds}bd/{baths}ba " if beds else ""

    subject = f"Off-Market: {prop_desc}{property_type} in {zip_code} — {price_str}"
    body = f"""<p>Hi {name},</p>
<p>I have an off-market deal that matches your buy box:</p>
<table style="border-collapse:collapse;width:100%;max-width:500px">
  <tr><td style="padding:6px 0;color:#555">Address</td><td style="padding:6px 0;font-weight:600">{property_address}</td></tr>
  <tr><td style="padding:6px 0;color:#555">Price</td><td style="padding:6px 0;font-weight:600">{price_str}</td></tr>
  <tr><td style="padding:6px 0;color:#555">ARV</td><td style="padding:6px 0;font-weight:600">{arv_str}</td></tr>
  <tr><td style="padding:6px 0;color:#555">Assignment Fee</td><td style="padding:6px 0;font-weight:600">{fee_str}</td></tr>
  <tr><td style="padding:6px 0;color:#555">Condition</td><td style="padding:6px 0">{condition.replace('_',' ').title() if condition else 'TBD'}</td></tr>
</table>
<p>Reply or call to get photos, comps, and full details.  This one moves fast.</p>
<p>— {sender_name}, {agency_name}</p>
<p style="font-size:11px;color:#aaa">
  Reply STOP to unsubscribe from deal alerts.
</p>"""
    return subject, body


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None
