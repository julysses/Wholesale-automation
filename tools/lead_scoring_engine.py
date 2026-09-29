"""
Deterministic seller-lead scoring engine (rules-based, no network calls).

Scores a lead on the same five 1–3 factors the CRM already stores
(motivation, timeline, equity, condition, flexibility; total 5–15) so the
existing HOT/WARM/COLD tiers, priority ranking and UI keep working, but derives
each factor from the data actually on the lead instead of asking an LLM to guess
from an address and a name.  17k leads score in well under a second, results
are reproducible, and every point is explainable via ``reasons``.

Wholesale logic
---------------
* Motivation  – stacked distress signals (probate, pre-foreclosure, tax
  delinquency, code violations, vacancy, absentee/out-of-state) found in the
  tag/source/notes text and in multi-list stack counts.
* Timeline    – hard clocks (foreclosure sale, probate, tax sale) and
  time-pressure language.
* Equity      – spread between value and liens; an assignable deal needs
  roughly 30%+ equity after repairs to leave a fee for the end buyer.
* Condition   – *exit-ability* to the large buyers (institutional SFR
  operators, iBuyers, rehab funds): standard SFR, 3+ bed, 1,000–3,000 sqft,
  built 1960+, mid-priced.  Old/oversized/land/multi-unit/mobile homes shrink
  the buyer pool, so they score lower even if the seller is motivated.
* Flexibility – asking price vs. estimated ARV (and the 70% rule), owner
  reachability (phone count) and DNC status.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# ── Tiers (kept identical to the AI path) ─────────────────────────────────────

HOT_MIN = 13
WARM_MIN = 8

FACTOR_KEYS = (
    "score_motivation",
    "score_timeline",
    "score_equity",
    "score_condition",
    "score_flexibility",
)


def tier_for_total(total: int) -> str:
    return "HOT" if total >= HOT_MIN else "WARM" if total >= WARM_MIN else "COLD"


STATUS_FOR_TIER = {"HOT": "qualified_hot", "WARM": "qualified_warm", "COLD": "qualified_cold"}
PRECISION_TIER_FOR_TIER = {"HOT": 1, "WARM": 2, "COLD": 3}

# ── Buy-box the big buyers use (tunable in one place) ─────────────────────────

BUYBOX_MIN_SQFT = 900
BUYBOX_MAX_SQFT = 3_200
BUYBOX_MIN_BEDS = 3
BUYBOX_MIN_YEAR = 1960
BUYBOX_MIN_VALUE = 90_000
BUYBOX_MAX_VALUE = 450_000
TARGET_ARV_RATIO = 0.70   # 70% rule
MIN_EQUITY_PCT = 30.0

# ── Signal vocabulary ─────────────────────────────────────────────────────────

# (regex, signal). Matched against tag + source + notes.
_SIGNAL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"probate|inherit|estate of|deceased|\bheir\b", "probate"),
    (r"pre[\s-]?foreclos|\bprefor\b|foreclos|\blis pendens\b|\bnod\b|notice of default|auction|trustee sale", "pre_foreclosure"),
    (r"delinq|tax[\s-]?(lien|sale|roll)|back tax", "tax_delinquent"),
    (r"code (violation|enforcement)|condemn|unsafe|nuisance", "code_violation"),
    (r"vacant|abandon|empty", "vacant"),
    (r"absentee|non[\s-]?owner|out[\s-]?of[\s-]?(state|town)", "absentee"),
    (r"divorce|bankrupt|chapter 7|chapter 13", "life_event"),
    (r"tired landlord|landlord|evict|tenant", "tired_landlord"),
    (r"water shut|utility (shut|disconnect)|shutoff", "utility_shutoff"),
    (r"fire damage|fire[\s-]?damaged|\bflood|\bhail\b|\bstorm|foundation|\bmold\b|\broof", "damaged"),
    (r"high equity|free and clear|no mortgage|paid off|\blow ltv\b", "high_equity"),
    (r"need(s)? to sell|must sell|asap|relocat|behind on|hardship|job loss|as[\s-]?is", "urgent_language"),
)

_MOTIVATION_POINTS = {
    "probate": 3, "pre_foreclosure": 3, "tax_delinquent": 2, "code_violation": 2,
    "utility_shutoff": 2, "vacant": 2, "life_event": 2, "tired_landlord": 1.5,
    "absentee": 1, "damaged": 1, "urgent_language": 1.5, "high_equity": 0.5,
}

_HARD_CLOCK = {"pre_foreclosure": 3, "probate": 2, "tax_delinquent": 2, "code_violation": 2,
               "utility_shutoff": 2, "life_event": 2, "urgent_language": 2}

# Tax-roll rows for business equipment etc. are not real estate and can never be assigned.
_NOT_REAL_ESTATE = re.compile(r"business personal|personal property|mineral|utility|inventory", re.I)
_RESIDENTIAL = re.compile(r"single[\s-]?family|\bsfr\b|residential|\bhouse\b|\bhome\b|townhome", re.I)
_NON_SFR = re.compile(
    r"mobile|manufactured|trailer|land|lot\b|vacant land|acre|multi|duplex|triplex|fourplex|"
    r"quad|apartment|commercial|condo|coop|co-op|industrial|farm|^other$",
    re.I,
)
_MISSING = (None, "", "None", "nan")


def _num(value: Any) -> Optional[float]:
    if value in _MISSING:
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(value)))
    except (ValueError, TypeError):
        return None


def _clamp(n: float) -> int:
    return max(1, min(3, int(round(n))))


@dataclass
class LeadScore:
    lead_id: str
    factors: dict[str, int]
    total: int
    tier: str
    signals: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    next_action: str = ""
    buybox_fit: str = "unknown"      # strong | ok | weak | unknown
    suppress_reason: Optional[str] = None

    def to_update_payload(self) -> dict[str, Any]:
        """Columns to write to ``leads`` (total_score is a generated column)."""
        payload: dict[str, Any] = dict(self.factors)
        payload["ai_qualification_summary"] = self.summary()
        payload["status"] = STATUS_FOR_TIER[self.tier]
        payload["precision_tier"] = PRECISION_TIER_FOR_TIER[self.tier]
        return payload

    def summary(self) -> str:
        head = f"{self.tier} ({self.total}/15)"
        body = "; ".join(self.reasons[:5]) or "Limited data — score is a baseline."
        text = f"{head}: {body}."
        if self.next_action:
            text += f" Next: {self.next_action}"
        return text[:500]


def detect_signals(*texts: Any) -> list[str]:
    blob = " ".join(str(t) for t in texts if t not in _MISSING).lower()
    blob = re.sub(r"[_+/]+", " ", blob)   # list names like Collin_County_Delinquent_Tax_Roll
    found: list[str] = []
    for pattern, signal in _SIGNAL_PATTERNS:
        if signal not in found and re.search(pattern, blob):
            found.append(signal)
    return found


_SUFFIX = {"street": "st", "avenue": "ave", "drive": "dr", "lane": "ln", "road": "rd",
           "court": "ct", "boulevard": "blvd", "place": "pl", "circle": "cir", "trail": "trl",
           "parkway": "pkwy", "highway": "hwy", "north": "", "south": "", "east": "", "west": ""}


def _street_key(raw: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(raw or "").lower())
    return " ".join(x for x in (_SUFFIX.get(t, t) for t in text.split()) if x)


def mailing_absentee(lead: dict[str, Any]) -> Optional[bool]:
    """True when the owner's mailing street differs from the property street
    (or is a PO box / suite = entity or out-of-house owner); None if unknown."""
    mail, prop = _street_key(lead.get("owner_mailing_address")), _street_key(lead.get("property_address"))
    if not mail or not prop:
        return None
    if re.match(r"^(po|p o) box\b", mail) or re.search(r"\b(ste|suite)\b", mail):
        return True
    return mail != prop


def _stack_count(lead: dict[str, Any]) -> int:
    sc = lead.get("stack_count")
    if isinstance(sc, (int, float)) and sc:
        return int(sc)
    m = re.search(r"stack_count=(\d+)", str(lead.get("internal_notes") or ""))
    if m:
        return int(m.group(1))
    source = str(lead.get("source") or "")
    return len([s for s in source.split("|") if s.strip()]) if "|" in source else 1


def score_lead(lead: dict[str, Any]) -> LeadScore:
    """Score one lead row (as stored in ``leads`` or a scoring payload)."""
    lead_id = str(lead.get("id") or lead.get("lead_id") or "")
    reasons: list[str] = []

    signals = detect_signals(
        lead.get("motivation_tag"), lead.get("source"),
        lead.get("seller_notes"), lead.get("internal_notes"),
    )
    stack = _stack_count(lead)
    ptype = str(lead.get("property_type") or "")

    if _NOT_REAL_ESTATE.search(ptype):
        return LeadScore(
            lead_id=lead_id, factors={k: 1 for k in FACTOR_KEYS}, total=5, tier="COLD",
            signals=signals, reasons=[f"Not real property ('{ptype}') - cannot be assigned"],
            next_action="Suppress: not a wholesale target", buybox_fit="weak",
            suppress_reason="NOT_REAL_ESTATE",
        )

    absentee = mailing_absentee(lead)
    if absentee and "absentee" not in signals:
        signals.append("absentee")
    elif absentee is False:
        reasons.append("Owner-occupied")

    # ── Motivation ────────────────────────────────────────────────────────────
    pts = sum(_MOTIVATION_POINTS.get(s, 0) for s in signals)
    if stack >= 3:
        pts += 2
    elif stack == 2:
        pts += 1
    if pts >= 3:
        motivation = 3
    elif pts >= 1.5:
        motivation = 2
    else:
        motivation = 1
    distress = [s for s in signals if s in _MOTIVATION_POINTS and s != "high_equity"]
    if distress:
        reasons.append("Distress: " + ", ".join(s.replace("_", " ") for s in distress))
    if stack >= 2:
        reasons.append(f"Stacked on {stack} lists")

    # ── Timeline ──────────────────────────────────────────────────────────────
    clock = max((_HARD_CLOCK.get(s, 0) for s in signals), default=0)
    attempts = int(_num(lead.get("contact_attempts")) or 0)
    if clock >= 3 or (clock >= 2 and stack >= 2):
        timeline = 3
        reasons.append("Hard deadline pressure")
    elif clock >= 2 or "vacant" in signals or stack >= 2:
        timeline = 2
    else:
        timeline = 1
    if attempts >= 4 and timeline > 1:
        timeline -= 1  # long-worked, not converting

    # ── Equity ────────────────────────────────────────────────────────────────
    arv = _num(lead.get("estimated_arv"))
    loan = _num(lead.get("loan_balance"))
    equity_pct = _num(lead.get("estimated_equity_pct"))
    if equity_pct is None and arv and arv > 0 and loan is not None:
        equity_pct = max(0.0, (arv - loan) / arv * 100)
    if equity_pct is not None:
        equity = 3 if equity_pct >= 50 else 2 if equity_pct >= MIN_EQUITY_PCT else 1
        reasons.append(f"~{equity_pct:.0f}% equity")
    elif "high_equity" in signals:
        equity = 3
        reasons.append("High equity indicated")
    elif "tired_landlord" in signals or "absentee" in signals:
        equity = 2  # long-held absentee/rentals usually carry equity
    else:
        equity = 2 if any(x in _MOTIVATION_POINTS and x != "high_equity" for x in signals) else 1

    # ── Condition / exit-ability to large buyers ──────────────────────────────
    buybox = 0
    checks = 0
    wrong_type = False
    no_street_number = not re.match(r"^\s*\d", _street_key(lead.get("property_address")))
    if (ptype and _NON_SFR.search(ptype)) or no_street_number:
        checks += 1
        buybox -= 2
        wrong_type = True
        reasons.append("No street number (unimproved land)" if no_street_number
                       else f"Type '{ptype}' outside institutional buy-box")
    elif ptype and _RESIDENTIAL.search(ptype):
        checks += 1
        buybox += 1
    sqft = _num(lead.get("sqft"))
    if sqft:
        checks += 1
        buybox += 1 if BUYBOX_MIN_SQFT <= sqft <= BUYBOX_MAX_SQFT else -1
    beds = _num(lead.get("bedrooms"))
    if beds:
        checks += 1
        buybox += 1 if beds >= BUYBOX_MIN_BEDS else -1
    year = _num(lead.get("year_built"))
    if year:
        checks += 1
        buybox += 1 if year >= BUYBOX_MIN_YEAR else -1
    value = arv or _num(lead.get("asking_price"))
    if value:
        checks += 1
        buybox += 1 if BUYBOX_MIN_VALUE <= value <= BUYBOX_MAX_VALUE else -1

    if checks == 0:
        buybox_fit, condition = "unknown", 2
    else:
        ratio = buybox / checks
        if wrong_type:
            buybox_fit, condition = "weak", 1   # wrong product type caps the exit
        elif ratio >= 0.6 and checks >= 2:
            buybox_fit, condition = "strong", 3
            reasons.append("Fits institutional/flip buy-box")
        elif ratio >= 0:
            buybox_fit, condition = "ok", 2
        else:
            buybox_fit, condition = "weak", 1
        if buybox_fit == "weak":
            reasons.append("Narrow exit (small buyer pool)")
    # Visible damage widens the discount, but only helps if the type is buyable.
    if "damaged" in signals and buybox_fit in ("strong", "ok"):
        condition = min(3, condition + 1)
        reasons.append("Damage signals (rehab discount)")

    # ── Flexibility ───────────────────────────────────────────────────────────
    ask = _num(lead.get("asking_price"))
    phones = sum(1 for k in ("owner_phone_1", "owner_phone_2", "owner_phone_3")
                 if lead.get(k) not in _MISSING)
    if ask and arv and arv > 0:
        ratio = ask / arv
        if ratio <= TARGET_ARV_RATIO:
            flexibility = 3
            reasons.append(f"Ask is {ratio:.0%} of ARV (fits 70% rule)")
        elif ratio <= 0.85:
            flexibility = 2
        else:
            flexibility = 1
            reasons.append(f"Ask is {ratio:.0%} of ARV (little spread)")
    else:
        flexibility = 2  # no ARV to test the ask against (often an AVM value, not a seller ask)
    needs_skip_trace = phones == 0 and lead.get("owner_email") in _MISSING
    if needs_skip_trace:
        reasons.append("No phone/email - skip trace first")   # a workflow step, not a reason to down-score
    elif phones >= 2 and flexibility < 3:
        flexibility += 1
        reasons.append(f"{phones} phone numbers")

    suppress_reason = None
    if lead.get("dnc"):
        suppress_reason = "DNC"
        flexibility = 1
        reasons.append("DNC — do not contact")

    factors = {
        "score_motivation": _clamp(motivation),
        "score_timeline": _clamp(timeline),
        "score_equity": _clamp(equity),
        "score_condition": _clamp(condition),
        "score_flexibility": _clamp(flexibility),
    }
    total = sum(factors.values())
    tier = tier_for_total(total)
    if factors["score_motivation"] < 2:
        tier = "COLD"   # a nice house with no distress evidence is not a motivated-seller lead
    if suppress_reason == "DNC" and tier == "HOT":
        tier = "WARM"  # never auto-route a DNC lead to calling

    if suppress_reason:
        action = "Do not call; direct mail only if legal"
    elif tier == "HOT":
        action = ("Call today; pull comps and line up an end buyer" if buybox_fit != "weak"
                  else "Call today; confirm a buyer exists before contracting")
    elif tier == "WARM":
        action = "SMS + follow-up call this week"
    else:
        action = "Nurture only; revisit if a new distress signal appears"

    if needs_skip_trace and not suppress_reason and tier != "COLD":
        action = "Skip trace first, then " + action[0].lower() + action[1:]

    return LeadScore(
        lead_id=lead_id, factors=factors, total=total, tier=tier,
        signals=signals, reasons=reasons, next_action=action,
        buybox_fit=buybox_fit, suppress_reason=suppress_reason,
    )


def score_leads(leads: list[dict[str, Any]]) -> list[LeadScore]:
    return [score_lead(l) for l in leads]
