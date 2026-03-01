"""Buyer Qualification Agent — objective, data-driven buyer scoring."""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from schemas.buyer import BuyerProfile, BuyerQualification
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class QualificationEvent(BaseModel):
    event_type: str  # "ghost" | "lowball" | "close" | "pod_verification"
    deal_id: Optional[str] = None
    days_to_close: Optional[int] = None
    offer_vs_ask_pct: Optional[float] = None  # e.g. 0.72 means offered 72% of ask
    notes: str = ""


class BuyerQualificationAgent(BaseAgent):
    name = "buyer_qualification_agent"
    system_prompt = SystemPrompts.BUYER_QUALIFICATION

    def initial_qualify(self, buyer: BuyerProfile) -> BuyerQualification:
        """
        Produce an initial qualification record for a new buyer.
        Uses Claude to assess profile quality and set starting reliability score.
        """
        prompt = f"""
Produce an initial BuyerQualification for this buyer profile.

Buyer:
- Name: {buyer.name}
- Company: {buyer.company}
- Markets: {buyer.markets}
- Strategies: {[s.value for s in buyer.strategies]}
- Price range: ${buyer.price_min or 0:,.0f} – ${buyer.price_max or 0:,.0f}
- Proof of funds: {buyer.proof_of_funds}
- Close speed stated: {buyer.close_speed_days} days
- Source: {buyer.source.value}
- Permission granted: {buyer.permission_granted}
- Notes: {buyer.notes}

Rules:
- New buyers with no track record start at reliability_score 50
- Verified proof of funds: +10 to score
- Institutional / company buyer with public record: +5 to score
- No contact info / no proof of funds: −10 to score
- Set buyer_id to "{buyer.id}"
- Set disqualified to false unless clearly a spam/fake profile
- Provide notes explaining the starting score
"""
        qual = self._call_structured(prompt, BuyerQualification)
        qual.buyer_id = buyer.id

        # Clamp score to valid range
        qual.reliability_score = max(0.0, min(100.0, qual.reliability_score))

        logger.info(
            f"[{self.name}] Initial qualification for {buyer.name}: "
            f"score={qual.reliability_score:.0f}"
        )
        return qual

    def update_qualification(
        self,
        qual: BuyerQualification,
        event: QualificationEvent,
    ) -> BuyerQualification:
        """Apply an event to an existing qualification record."""
        if event.event_type == "ghost":
            qual.degrade_for_ghost()
            logger.info(
                f"[{self.name}] Buyer {qual.buyer_id} ghosted — score now {qual.reliability_score:.0f}"
            )
        elif event.event_type == "lowball":
            qual.degrade_for_lowball()
            logger.info(
                f"[{self.name}] Buyer {qual.buyer_id} lowballed — score now {qual.reliability_score:.0f}"
            )
        elif event.event_type == "close":
            days = event.days_to_close or 30
            qual.upgrade_for_close(days)
            logger.info(
                f"[{self.name}] Buyer {qual.buyer_id} closed in {days}d — "
                f"score now {qual.reliability_score:.0f}"
            )

        # Auto-disqualify on sustained low score
        if qual.reliability_score < 20 and qual.ghost_count >= 3:
            qual.disqualified = True
            qual.disqualification_reason = (
                f"Auto-disqualified: score {qual.reliability_score:.0f}, "
                f"{qual.ghost_count} ghosts"
            )
            logger.warning(
                f"[{self.name}] Buyer {qual.buyer_id} auto-disqualified"
            )

        return qual

    def run(
        self,
        buyers: list[BuyerProfile],
    ) -> list[BuyerQualification]:
        """Initial qualification for a list of new buyers."""
        qualifications: list[BuyerQualification] = []
        for buyer in buyers:
            try:
                qual = self.initial_qualify(buyer)
                qualifications.append(qual)
            except Exception as exc:
                logger.error(
                    f"[{self.name}] Failed to qualify buyer {buyer.name}: {exc}"
                )
        return qualifications
