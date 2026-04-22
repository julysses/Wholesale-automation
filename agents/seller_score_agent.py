"""
Seller Score Agent — blueprint additive scoring formula with stacking bonuses.

SIGNAL SCORES:
  +20  absentee_owner
  +25  vacant_property
  +25  probate_case
  +20  pre_foreclosure
  +15  tax_delinquent
  +20  code_violation         (government data)
  +20  utility_shutoff        (government data)
  +15  municipal_lien         (government data)
  +10  equity_above_50
  +10  ownership_length_over_10
  +10  out_of_state_owner

STACKING BONUSES (applied on top of signal scores):
  absentee + vacant                        +30
  vacant + tax_delinquent                  +35
  probate + vacant                         +40
  code_violation + vacant                  +40
  utility_shutoff + vacant                 +45
  absentee + tax_delinquent                +30
  absentee + vacant + tax_delinquent       +50
  Ultimate Distress (all four)             +70

TIER THRESHOLDS:
  A = 90+  → AI calling campaign (highest priority)
  B = 70–89 → AI calling campaign
  C = 50–69 → SMS nurture only
  D = <50   → suppress

Only Tier A and B enter AI calling campaigns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from schemas.property import DistressSignal, PropertyLead, SIGNAL_WEIGHTS, compute_stack_bonus

logger = logging.getLogger(__name__)


# ── Tier configuration ─────────────────────────────────────────────────────────

TIER_A_MIN = 90
TIER_B_MIN = 70
TIER_C_MIN = 50
# D is anything below TIER_C_MIN


def score_to_tier(score: int) -> str:
    if score >= TIER_A_MIN: return "A"
    if score >= TIER_B_MIN: return "B"
    if score >= TIER_C_MIN: return "C"
    return "D"


def tier_to_routing(tier: str) -> tuple[str, str]:
    """Return (routing_action, routing_reason) for a given tier."""
    if tier == "A":
        return "ai_calling", "Tier A (90+) — highest priority AI calling campaign"
    if tier == "B":
        return "ai_calling", "Tier B (70–89) — AI calling campaign"
    if tier == "C":
        return "sms_nurture", "Tier C (50–69) — SMS nurture only"
    return "suppress", "Tier D (<50) — suppress unless manually approved"


# ── Score result ───────────────────────────────────────────────────────────────

@dataclass
class SellerScoreResult:
    lead_id: str
    seller_score: int
    priority_tier: str              # A | B | C | D
    signal_score: int               # Sum of raw signal points
    stack_name: str                 # e.g. "Absentee + Vacant" or "Single Signal"
    stack_bonus: int                # Extra points from stacking
    score_breakdown: dict           # signal/penalty → points
    active_signals: list[str]       # Which signals contributed
    routing_action: str             # ai_calling | sms_nurture | suppress
    routing_reason: str
    enters_calling_campaign: bool   # True only for A and B


# ── Agent ──────────────────────────────────────────────────────────────────────

class SellerScoreAgent:
    """
    Deterministic seller scoring agent implementing the blueprint formula.
    Supports both direct field inputs and PropertyLead objects.
    """

    name = "seller_score_agent"

    def score_lead(
        self,
        lead_id: str,
        # Core distress signals
        absentee_owner: bool = False,
        vacant: bool = False,
        probate: bool = False,
        pre_foreclosure: bool = False,
        tax_delinquent: bool = False,
        code_violation: bool = False,
        utility_shutoff: bool = False,
        municipal_lien: bool = False,
        # Equity / ownership modifiers
        estimated_equity_pct: Optional[float] = None,
        years_owned: Optional[int] = None,
        out_of_state_owner: bool = False,
        # Compliance penalties
        dnc: bool = False,
        days_since_last_contact: Optional[int] = None,
        # Phone quality
        has_mobile_phone: bool = True,
        has_any_phone: bool = True,
    ) -> SellerScoreResult:
        """Score a single lead using the blueprint additive formula + stacking."""

        breakdown: dict[str, int] = {}
        active_signals: list[DistressSignal] = []

        # ── Signal scores ──────────────────────────────────────────────────────

        def add(signal: DistressSignal, condition: bool) -> None:
            if condition:
                pts = SIGNAL_WEIGHTS[signal]
                breakdown[signal.value] = pts
                active_signals.append(signal)

        add(DistressSignal.ABSENTEE_OWNER,     absentee_owner)
        add(DistressSignal.VACANCY,            vacant)
        add(DistressSignal.PROBATE_INHERITED,  probate)
        add(DistressSignal.PRE_FORECLOSURE,    pre_foreclosure)
        add(DistressSignal.TAX_DELINQUENT,     tax_delinquent)
        add(DistressSignal.CODE_VIOLATION,     code_violation)
        add(DistressSignal.UTILITY_SHUTOFF,    utility_shutoff)
        add(DistressSignal.MUNICIPAL_LIEN,     municipal_lien)

        if estimated_equity_pct is not None and estimated_equity_pct > 50:
            add(DistressSignal.HIGH_EQUITY, True)

        if years_owned is not None and years_owned >= 10:
            add(DistressSignal.LONG_TERM_OWNER, True)

        add(DistressSignal.OUT_OF_STATE_OWNER, out_of_state_owner)

        signal_score = sum(breakdown.values())

        # ── Stacking bonus ────────────────────────────────────────────────────

        signal_set = set(active_signals)
        stack_name, stack_bonus = compute_stack_bonus(signal_set)

        if stack_bonus > 0:
            breakdown[f"stack_bonus:{stack_name}"] = stack_bonus

        raw_score = signal_score + stack_bonus

        # ── Penalties ─────────────────────────────────────────────────────────

        if dnc:
            breakdown["dnc_penalty"] = -40
            raw_score -= 40

        if days_since_last_contact is not None and days_since_last_contact < 90:
            breakdown["duplicate_contact_90d_penalty"] = -20
            raw_score -= 20

        if has_any_phone and not has_mobile_phone:
            breakdown["landline_only_penalty"] = -15
            raw_score -= 15

        # ── Tier + routing ────────────────────────────────────────────────────

        if not has_any_phone:
            # No phone at all → direct mail only, force suppress
            breakdown["no_phone_override"] = 0
            tier = "D"
            routing_action = "suppress"
            routing_reason = "No phone number found — direct mail only"
        else:
            tier = score_to_tier(raw_score)
            routing_action, routing_reason = tier_to_routing(tier)

        enters_calling = tier in ("A", "B") and not dnc and has_any_phone

        result = SellerScoreResult(
            lead_id=lead_id,
            seller_score=raw_score,
            priority_tier=tier,
            signal_score=signal_score,
            stack_name=stack_name,
            stack_bonus=stack_bonus,
            score_breakdown=breakdown,
            active_signals=[s.value for s in active_signals],
            routing_action=routing_action,
            routing_reason=routing_reason,
            enters_calling_campaign=enters_calling,
        )

        logger.info(
            f"[{self.name}] lead={lead_id} score={raw_score} "
            f"(signals={signal_score} + stack={stack_bonus}) "
            f"tier={tier} stack='{stack_name}' action={routing_action}"
        )
        return result

    def score_property_lead(self, lead: PropertyLead) -> SellerScoreResult:
        """Score from a PropertyLead object directly."""
        out_of_state = (
            lead.owner_mailing_address is not None
            and lead.owner_mailing_address.state != lead.address.state
        )
        result = self.score_lead(
            lead_id=str(lead.id),
            absentee_owner=lead.is_absentee,
            vacant=lead.is_vacant,
            probate=lead.probate_status,
            pre_foreclosure=lead.pre_foreclosure_status,
            tax_delinquent=bool(lead.tax_delinquent_amount and lead.tax_delinquent_amount > 0),
            code_violation=lead.code_violation_status,
            utility_shutoff=lead.utility_shutoff_status,
            municipal_lien=lead.municipal_lien_status,
            estimated_equity_pct=lead.estimated_equity_pct,
            years_owned=lead.years_owned,
            out_of_state_owner=out_of_state,
            dnc=lead.flagged,
            has_mobile_phone=bool(lead.phone_numbers),
            has_any_phone=bool(lead.phone_numbers),
        )
        # Write back to lead
        lead.seller_score = result.seller_score
        lead.distress_score = result.seller_score
        lead.stack_name = result.stack_name
        lead.stack_bonus = result.stack_bonus
        return result

    def score_batch(self, leads: list[PropertyLead]) -> list[SellerScoreResult]:
        """Score a list of PropertyLead objects."""
        results = []
        tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}

        for lead in leads:
            result = self.score_property_lead(lead)
            tier_counts[result.priority_tier] += 1
            results.append(result)

        calling_count = sum(1 for r in results if r.enters_calling_campaign)
        logger.info(
            f"[{self.name}] Batch {len(leads)} leads — "
            f"A={tier_counts['A']} B={tier_counts['B']} "
            f"C={tier_counts['C']} D={tier_counts['D']} "
            f"calling_eligible={calling_count}"
        )
        return results
