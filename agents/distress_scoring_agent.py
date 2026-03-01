"""Distress Scoring Agent — scores seller motivation, not property value."""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from config.settings import settings
from schemas.property import DistressSignal, PropertyLead, SIGNAL_WEIGHTS
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DistressScoreResult(BaseModel):
    lead_id: str
    score: int = Field(ge=0, le=100)
    signals_present: list[str] = Field(default_factory=list)
    rationale: str
    passes_threshold: bool = False


class DistressScoringAgent(BaseAgent):
    name = "distress_scoring_agent"
    system_prompt = SystemPrompts.DISTRESS_SCORING

    def score_lead(self, lead: PropertyLead) -> DistressScoreResult:
        """Score a single property lead for seller distress."""
        prompt = f"""
Score this Texas property lead for seller distress motivation.

Property: {lead.address.full}
Owner: {lead.owner_name}
Is absentee owner: {lead.is_absentee}
Is vacant: {lead.is_vacant}
Estimated equity %: {lead.estimated_equity_pct}
Tax delinquent amount: {lead.tax_delinquent_amount}
Source: {lead.source.value}
Raw signals from data source: {[s.value for s in lead.signals_raw]}
Notes: {lead.notes}

Instructions:
- Only score signals for which you have actual evidence in the data above
- Do not infer signals that aren't supported by the data
- Return lead_id as "{lead.id}"
- passes_threshold should be false (the orchestrator sets this)
"""
        result = self._call_structured(prompt, DistressScoreResult)
        result.lead_id = str(lead.id)

        # Recalculate score deterministically from confirmed signals
        # (Claude confirms which signals are evidenced; we calculate the math)
        confirmed_signals = []
        computed_score = 0
        for sig_str in result.signals_present:
            try:
                sig = DistressSignal(sig_str)
                confirmed_signals.append(sig)
                computed_score += SIGNAL_WEIGHTS.get(sig, 0)
            except ValueError:
                logger.warning(f"[{self.name}] Unknown signal: {sig_str}")

        result.score = min(100, computed_score)
        result.signals_present = [s.value for s in confirmed_signals]
        result.passes_threshold = result.score >= settings.distress_score_threshold

        logger.info(
            f"[{self.name}] Lead {lead.id} scored {result.score} "
            f"(threshold={settings.distress_score_threshold}, "
            f"passes={result.passes_threshold})"
        )
        return result

    def run(self, leads: list[PropertyLead]) -> list[tuple[PropertyLead, DistressScoreResult]]:
        """
        Score all leads. Return (lead, score) pairs that pass the threshold.
        """
        passing: list[tuple[PropertyLead, DistressScoreResult]] = []

        for lead in leads:
            score_result = self.score_lead(lead)
            # Update the lead's distress_score field
            lead.distress_score = score_result.score
            if score_result.passes_threshold:
                passing.append((lead, score_result))
            else:
                logger.info(
                    f"[{self.name}] Lead {lead.id} filtered out (score={score_result.score})"
                )

        logger.info(f"[{self.name}] {len(passing)}/{len(leads)} leads passed threshold")
        return passing
