"""Dispo / Matching Agent — matches deals to qualified buyers by fit + reliability."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from schemas.buyer import BuyerProfile, BuyerQualification, BuyerTier
from schemas.deal import Deal, UnderwritingReport
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BuyerMatch(BaseModel):
    buyer_id: str
    buyer_name: str
    tier: BuyerTier
    fit_score: float = Field(ge=0.0, le=100.0)
    reliability_score: float = Field(ge=0.0, le=100.0)
    combined_score: float = Field(ge=0.0, le=100.0)
    fit_rationale: str
    recommended: bool = False


class DispoMatchResult(BaseModel):
    deal_id: str
    lead_address: str
    top_matches: list[BuyerMatch] = Field(default_factory=list)
    winner_id: Optional[str] = None
    winner_rationale: str = ""
    distribution_notes: str = ""


class DispoMatchingAgent(BaseAgent):
    name = "dispo_matching_agent"
    system_prompt = SystemPrompts.DISPO_MATCHING

    def match_deal(
        self,
        deal: Deal,
        report: UnderwritingReport,
        buyers: list[tuple[BuyerProfile, BuyerQualification]],
    ) -> DispoMatchResult:
        """
        Match an underwritten deal to the top buyers from the qualified pool.
        """
        if not buyers:
            logger.warning(f"[{self.name}] No buyers available for deal {deal.id}")
            return DispoMatchResult(
                deal_id=str(deal.id),
                lead_address=report.address_full,
            )

        # Build buyer summary for the prompt
        buyer_summaries = []
        for profile, qual in buyers:
            if qual.disqualified:
                continue
            buyer_summaries.append(
                f"- ID: {profile.id} | Name: {profile.name} | "
                f"Markets: {profile.markets} | "
                f"Strategies: {[s.value for s in profile.strategies]} | "
                f"Price: ${profile.price_min or 0:,.0f}–${profile.price_max or 0:,.0f} | "
                f"Close speed: {profile.close_speed_days}d | "
                f"Reliability: {qual.reliability_score:.0f}/100 | "
                f"Total closes: {qual.total_closes_with_agency} | "
                f"Ghosts: {qual.ghost_count}"
            )

        prompt = f"""
Match this deal to the best qualified buyers.

Deal:
- ID: {deal.id}
- Address: {report.address_full}
- ARV (low/mid/high): ${report.arv.low:,.0f} / ${report.arv.mid:,.0f} / ${report.arv.high:,.0f}
- Rehab (low/mid/high): ${report.rehab.low:,.0f} / ${report.rehab.mid:,.0f} / ${report.rehab.high:,.0f}
- MAO: ${report.mao:,.0f}
- Strategy: {report.strategy.value}

Qualified buyer pool:
{chr(10).join(buyer_summaries) if buyer_summaries else "None available"}

Instructions:
- Rank up to 10 buyers by: (1) buy box fit, (2) reliability_score, (3) close speed
- Assign tiers: Tier 1 = top 3, Tier 2 = next 4, Tier 3 = remaining
- combined_score = (fit_score × 0.5) + (reliability_score × 0.5)
- Identify one recommended winner (highest certainty of close, NOT just highest offer)
- winner_id must be one of the buyer IDs listed above
- Set deal_id = "{deal.id}"
- lead_address = "{report.address_full}"
"""
        result = self._call_structured(prompt, DispoMatchResult)
        result.deal_id = str(deal.id)
        result.lead_address = report.address_full

        # Mark the recommended match
        for match in result.top_matches:
            if match.buyer_id == result.winner_id:
                match.recommended = True

        logger.info(
            f"[{self.name}] Deal {deal.id} matched to {len(result.top_matches)} buyers. "
            f"Winner: {result.winner_id}"
        )
        return result

    def run(
        self,
        deals_with_reports: list[tuple[Deal, UnderwritingReport]],
        buyers: list[tuple[BuyerProfile, BuyerQualification]],
    ) -> list[DispoMatchResult]:
        """Match a batch of deals to the buyer pool."""
        results: list[DispoMatchResult] = []
        for deal, report in deals_with_reports:
            try:
                result = self.match_deal(deal, report, buyers)
                results.append(result)
            except Exception as exc:
                logger.error(f"[{self.name}] Matching failed for deal {deal.id}: {exc}")
        return results
