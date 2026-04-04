"""
Lead Generation Agent — AI-powered campaign optimization and ad copy generation.

Uses Claude Haiku (fast + cheap) to:
1. Analyze campaign/creative performance and recommend optimizations
2. Generate HomeVestors-style ad copy variants for any pain-point angle
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from config.settings import settings

logger = logging.getLogger(__name__)

# Override to Haiku for speed/cost efficiency on copy gen tasks
HAIKU_MODEL = "claude-haiku-4-5-20251001"


class PauseRecommendation(BaseModel):
    creative_id: str
    reason: str


class BudgetShift(BaseModel):
    from_campaign: str
    to_campaign: str
    amount: float
    reason: str


class AdCopyVariant(BaseModel):
    headline: str
    primary_text: str
    cta: str = "Get My Cash Offer"
    pain_point_angle: str
    rationale: str


class OptimizationReport(BaseModel):
    pause_recommendations: list[PauseRecommendation] = Field(default_factory=list)
    budget_shifts: list[BudgetShift] = Field(default_factory=list)
    new_copy_angles: list[AdCopyVariant] = Field(default_factory=list)
    audience_suggestions: list[str] = Field(default_factory=list)
    summary: str = ""


class CopyGenerationResponse(BaseModel):
    variants: list[AdCopyVariant]


class LeadGenerationAgent(BaseAgent):
    """Analyzes ad campaign performance and generates optimized ad copy."""

    name = "lead_generation_agent"
    system_prompt = """You are an expert direct-response real estate advertising strategist.
You specialize in motivated seller campaigns for Texas wholesale real estate.
You emulate the best practices of HomeVestors, We Buy Ugly Houses, and top iBuyer campaigns.

Your copy principles:
- Pain-point first (address the seller's specific situation)
- Simple, clear language (8th grade reading level)
- One clear call to action
- Zero fake urgency or pressure
- Honest value proposition: fair offer, fast close, no repairs, no fees
- Local market credibility

When analyzing campaigns:
- Flag underperformers based on CPL > $80 or lead quality score < 50
- Recommend budget shifts toward proven winners
- Suggest new angles for A/B testing based on market data
- Be specific and actionable — not generic advice"""

    def __init__(self) -> None:
        super().__init__()
        # Override to Haiku for copy generation
        self._model = HAIKU_MODEL

    def analyze_campaign_performance(
        self,
        campaigns: list[dict],
        creatives: list[dict],
    ) -> OptimizationReport:
        """
        Analyze campaign and creative performance data, return optimization recommendations.

        campaigns: list of ad_campaign dicts (name, total_spend, leads_count, cpl, avg_lead_quality_score, status)
        creatives: list of ad_creative dicts (id, name, headline, pain_point_angle, cpl, leads_count, avg_lead_quality_score, is_winner)
        """
        if not campaigns and not creatives:
            return OptimizationReport(
                summary="No campaign data available for analysis. Import campaigns and run ads to get optimization recommendations."
            )

        # Build context summary
        campaign_summary = json.dumps(
            [
                {
                    "name": c.get("name"),
                    "spend": c.get("total_spend", 0),
                    "leads": c.get("leads_count", 0),
                    "cpl": c.get("cpl"),
                    "avg_quality": c.get("avg_lead_quality_score"),
                    "status": c.get("status"),
                }
                for c in campaigns
            ],
            indent=2,
        )
        creative_summary = json.dumps(
            [
                {
                    "id": cr.get("id"),
                    "name": cr.get("name"),
                    "headline": cr.get("headline"),
                    "angle": cr.get("pain_point_angle"),
                    "cpl": cr.get("cpl"),
                    "leads": cr.get("leads_count", 0),
                    "avg_quality": cr.get("avg_lead_quality_score"),
                    "is_winner": cr.get("is_winner", False),
                }
                for cr in creatives
            ],
            indent=2,
        )

        prompt = f"""Analyze this Texas wholesale real estate ad campaign performance data:

CAMPAIGNS:
{campaign_summary}

AD CREATIVES (A/B variants):
{creative_summary}

Provide optimization recommendations. Consider:
- Pause creatives with CPL > $80 or avg lead quality < 50 with sufficient spend (>$100)
- Budget shifts from poor performers to proven winners
- 3 new copy variants to test (different pain-point angles not yet represented)
- Audience expansion or refinement suggestions

Return your analysis as a JSON object.
"""
        try:
            return self._call_structured(prompt, OptimizationReport, max_tokens=2048)
        except Exception as exc:
            logger.error(f"analyze_campaign_performance error: {exc}")
            return OptimizationReport(
                summary=f"Analysis failed: {exc}. Please try again."
            )

    def generate_ad_copy_variants(
        self,
        pain_point_angle: str,
        market: str = "Texas",
        num_variants: int = 5,
    ) -> list[AdCopyVariant]:
        """
        Generate Facebook ad copy variants for a given pain-point angle.

        pain_point_angle: foreclosure | divorce | inherited | tired_landlord | relocation | repairs | generic
        market: geographic area (e.g., "Dallas-Fort Worth", "Texas")
        """
        prompt = f"""Generate {num_variants} unique Facebook ad copy variants for a {market} real estate cash buyer targeting the "{pain_point_angle}" seller pain point.

Each variant should:
- Have a different headline approach (question, statement, benefit, social proof, urgency)
- Have a 2–3 sentence primary text body
- Use clear, honest language — no fake urgency or pressure
- End with a natural call to action
- Be appropriate for Facebook/Instagram feed placement

Pain point context:
- foreclosure: seller is behind on payments, facing sheriff sale
- divorce: need to split equity quickly, complicated co-ownership
- inherited: don't want to manage a property, need probate relief
- tired_landlord: bad tenants, maintenance burden, want to exit rental
- relocation: job move, retirement, military deployment — need to sell quickly
- repairs: roof, foundation, HVAC issues — can't afford to fix
- generic: any motivated seller, flexible situations

Return a JSON object with a "variants" array of {num_variants} variants.
"""
        try:
            result = self._call_structured(
                prompt, CopyGenerationResponse, max_tokens=2048
            )
            return result.variants
        except Exception as exc:
            logger.error(f"generate_ad_copy_variants error: {exc}")
            return []

    # Pre-seeded copy examples (HomeVestors-style templates)
    SEED_COPY: dict[str, dict[str, str]] = {
        "foreclosure": {
            "headline": "Stop Foreclosure — Get Cash Fast",
            "primary_text": "Facing foreclosure? We buy houses in ANY condition, close in 7 days, and pay all closing costs. No banks. No delays. Get a fair offer today.",
            "cta": "Stop My Foreclosure",
        },
        "divorce": {
            "headline": "Need to Sell Fast? We Pay Cash",
            "primary_text": "Going through a divorce? We make it simple — fair cash offer, close on your timeline, zero hassle. Walk away with your equity intact.",
            "cta": "Get My Cash Offer",
        },
        "inherited": {
            "headline": "Inherited a House? We'll Buy It As-Is",
            "primary_text": "Don't spend months cleaning out and fixing up. We buy inherited homes exactly as they are — fair price, fast close, all paperwork handled.",
            "cta": "Sell My Inherited Home",
        },
        "tired_landlord": {
            "headline": "Done Being a Landlord?",
            "primary_text": "Bad tenants? Repairs piling up? We buy rental properties and take the headache off your hands. Cash offer in 24 hours.",
            "cta": "Sell My Rental",
        },
        "repairs": {
            "headline": "We Buy Houses That Need Work",
            "primary_text": "No repairs needed. No showings. No commissions. Just a fair cash offer and a fast close — regardless of condition.",
            "cta": "Get My As-Is Offer",
        },
        "relocation": {
            "headline": "Moving? Sell Your House in Days, Not Months",
            "primary_text": "Need to relocate for work or family? We buy your house fast so you can move forward without the stress of a traditional sale.",
            "cta": "Sell Before I Move",
        },
        "generic": {
            "headline": "Sell Your House in 7 Days",
            "primary_text": "Local cash buyers. Close fast. No fees, no repairs, no stress. Get a fair offer today — any condition, any situation.",
            "cta": "Get My Free Offer",
        },
    }
