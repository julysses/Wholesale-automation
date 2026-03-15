"""
Seller Score Agent — blueprint additive scoring formula.

Produces a 0–100+ seller_score and a priority tier (A/B/C/D) for each lead.
This runs AFTER skip tracing so phone quality is factored in.

Scoring formula (from blueprint):
  +20  absentee owner
  +20  vacant property
  +15  tax delinquent
  +15  pre-foreclosure
  +10  equity > 50%
  +10  years owned > 10
  +10  out-of-state owner
  ─────────────────────
  Max  100 (before penalties)

  -40  on DNC list
  -20  duplicate owner contacted in last 90 days
  -15  landline only (no mobile phone found)

Tiers:
  A = 70+  → push to dialer automatically
  B = 50–69 → push to dialer automatically
  C = 30–49 → enroll in SMS nurture
  D = <30   → suppress unless manually approved

This agent is deterministic — no Claude call needed.
It is used by the orchestrator after skip tracing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ── Score result ───────────────────────────────────────────────────────────────

@dataclass
class SellerScoreResult:
    lead_id: str
    seller_score: int
    priority_tier: str          # A | B | C | D
    score_breakdown: dict       # field → points awarded
    routing_action: str         # dialer | sms_nurture | suppress
    routing_reason: str


# ── Tier helpers ───────────────────────────────────────────────────────────────

def score_to_tier(score: int) -> str:
    if score >= 70:
        return "A"
    if score >= 50:
        return "B"
    if score >= 30:
        return "C"
    return "D"


def tier_to_routing(tier: str) -> tuple[str, str]:
    """Return (routing_action, routing_reason) for a given tier."""
    if tier in ("A", "B"):
        return "dialer", f"Tier {tier} (score >= {'70' if tier == 'A' else '50'}) — push to dialer"
    if tier == "C":
        return "sms_nurture", "Tier C (30–49) — enroll in SMS nurture campaign"
    return "suppress", "Tier D (< 30) — suppress unless manually approved"


# ── Agent ──────────────────────────────────────────────────────────────────────

class SellerScoreAgent:
    """
    Deterministic seller scoring agent.

    Inputs come from the lead record + skip trace result.
    All scoring logic is explicit and auditable — no AI call.
    """

    name = "seller_score_agent"

    def score_lead(
        self,
        lead_id: str,
        # Motivation flags
        absentee_owner: bool = False,
        vacant: bool = False,
        tax_delinquent: bool = False,
        pre_foreclosure: bool = False,
        out_of_state_owner: bool = False,
        years_owned: Optional[int] = None,
        estimated_equity_pct: Optional[float] = None,
        # Compliance penalties
        dnc: bool = False,
        days_since_last_contact: Optional[int] = None,  # for 90-day duplicate check
        # Phone quality (from skip trace)
        has_mobile_phone: bool = True,
        has_any_phone: bool = True,
    ) -> SellerScoreResult:
        """
        Score a single lead using the blueprint additive formula.
        Returns a SellerScoreResult with score, tier, and routing action.
        """
        breakdown: dict[str, int] = {}
        score = 0

        # ── Positive signals ──────────────────────────────────────────────────

        if absentee_owner:
            breakdown["absentee_owner"] = 20
            score += 20

        if vacant:
            breakdown["vacant"] = 20
            score += 20

        if tax_delinquent:
            breakdown["tax_delinquent"] = 15
            score += 15

        if pre_foreclosure:
            breakdown["pre_foreclosure"] = 15
            score += 15

        if estimated_equity_pct is not None and estimated_equity_pct > 50:
            breakdown["equity_gt_50pct"] = 10
            score += 10

        if years_owned is not None and years_owned > 10:
            breakdown["years_owned_gt_10"] = 10
            score += 10

        if out_of_state_owner:
            breakdown["out_of_state_owner"] = 10
            score += 10

        # ── Penalties ─────────────────────────────────────────────────────────

        if dnc:
            breakdown["dnc_penalty"] = -40
            score -= 40

        if days_since_last_contact is not None and days_since_last_contact < 90:
            breakdown["duplicate_contact_90d_penalty"] = -20
            score -= 20

        if has_any_phone and not has_mobile_phone:
            breakdown["landline_only_penalty"] = -15
            score -= 15

        # ── Derive tier + routing ─────────────────────────────────────────────

        # If no valid phone at all, force suppress regardless of score
        if not has_any_phone:
            breakdown["no_phone_override"] = 0
            tier = "D"
            routing_action = "suppress"
            routing_reason = "No phone number found from skip trace — direct mail only"
        else:
            tier = score_to_tier(score)
            routing_action, routing_reason = tier_to_routing(tier)

        result = SellerScoreResult(
            lead_id=lead_id,
            seller_score=score,
            priority_tier=tier,
            score_breakdown=breakdown,
            routing_action=routing_action,
            routing_reason=routing_reason,
        )

        logger.info(
            f"[{self.name}] lead={lead_id} score={score} tier={tier} "
            f"action={routing_action} breakdown={breakdown}"
        )
        return result

    def score_batch(self, lead_inputs: list[dict]) -> list[SellerScoreResult]:
        """
        Score a list of leads from dicts.
        Each dict should include the same kwargs as score_lead().
        Required key: 'lead_id'.
        """
        results = []
        for inp in lead_inputs:
            lead_id = str(inp.pop("lead_id", "unknown"))
            result = self.score_lead(lead_id=lead_id, **inp)
            results.append(result)

        tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for r in results:
            tier_counts[r.priority_tier] = tier_counts.get(r.priority_tier, 0) + 1

        logger.info(
            f"[{self.name}] Batch scored {len(results)} leads — "
            f"A={tier_counts['A']} B={tier_counts['B']} "
            f"C={tier_counts['C']} D={tier_counts['D']}"
        )
        return results
