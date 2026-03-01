"""Buyer Sourcing Agent — ethical, permission-based buyer identification."""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from schemas.buyer import BuyerProfile, BuyerSource, BuyerStrategy
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BuyerResearchRequest(BaseModel):
    platform: str  # "facebook_group" | "bigger_pockets" | "reia" | etc.
    platform_url: str = ""
    market_focus: str = "Texas"
    raw_profile_text: str  # scraped/observed public info about the buyer
    source: BuyerSource


class FacebookOutreachDraft(BaseModel):
    body: str
    tone_assessment: str
    platform: str = "facebook"


class BuyerSourcingAgent(BaseAgent):
    name = "buyer_sourcing_agent"
    system_prompt = SystemPrompts.BUYER_SOURCING

    def identify_buyer(self, request: BuyerResearchRequest) -> BuyerProfile:
        """
        Extract a structured buyer profile from publicly observed profile text.
        """
        prompt = f"""
Extract a buyer profile from this publicly observed information.

Platform: {request.platform}
Platform URL: {request.platform_url}
Market focus: {request.market_focus}
Observed public profile / post text:
{request.raw_profile_text}

Instructions:
- Extract: name, company (if mentioned), inferred buy box (markets, price range, strategy)
- Only use information clearly present in the text
- Set permission_granted to false (requires explicit opt-in)
- source should be "{request.source.value}"
- source_platform_url should be "{request.platform_url}"
- Do NOT invent contact info not present in the text
- inferred_buy_box should be a 1–2 sentence summary
"""
        profile = self._call_structured(prompt, BuyerProfile)
        profile.source = request.source
        profile.source_platform_url = request.platform_url
        profile.permission_granted = False  # always enforce

        logger.info(
            f"[{self.name}] Identified buyer '{profile.name}' from {request.platform}"
        )
        return profile

    def draft_facebook_outreach(
        self,
        buyer: BuyerProfile,
        context: str = "",
    ) -> FacebookOutreachDraft:
        """
        Draft a respectful Facebook DM requesting permission to send off-market deals.
        """
        prompt = f"""
Draft a respectful Facebook DM to a Texas real estate investor.

Investor profile summary:
- Name: {buyer.name}
- Inferred buy box: {buyer.inferred_buy_box}
- Strategies: {[s.value for s in buyer.strategies]}
- Markets: {buyer.markets}
- Context: {context if context else "None"}

Goal: Ask permission to send relevant off-market deals.

Rules:
- Tone: peer-to-peer, genuine, no pitch
- No emojis. No urgency.
- No claims about deal volume or exclusivity
- Keep it under 100 words
- Lead with something specific to their profile (shows you read it)
- End with a simple yes/no question

Return body (the message text), tone_assessment, and platform="facebook".
"""
        draft = self._call_structured(prompt, FacebookOutreachDraft)
        logger.info(f"[{self.name}] Drafted Facebook DM for buyer {buyer.name}")
        return draft

    def draft_institutional_outreach(
        self,
        buyer: BuyerProfile,
        context: str = "",
    ) -> FacebookOutreachDraft:
        """Draft outreach to institutional buyers (funds, family offices, PE)."""
        prompt = f"""
Draft a professional email or LinkedIn message to an institutional real estate buyer.

Buyer / firm:
- Name: {buyer.name}
- Company: {buyer.company}
- Strategies: {[s.value for s in buyer.strategies]}
- Markets: {buyer.markets}
- Context: {context if context else "None"}

Goal: Introduce ourselves as a Texas-based wholesaler and ask if they accept off-market deal flow.

Rules:
- Professional, concise — under 120 words
- Reference their market focus specifically
- No hype, no inflated claims
- Clear opt-in request: "Would you be open to receiving relevant Texas off-market opportunities?"
- Include brief one-liner about our sourcing approach

Return body, tone_assessment, platform="email_or_linkedin".
"""
        draft = self._call_structured(prompt, FacebookOutreachDraft)
        logger.info(f"[{self.name}] Drafted institutional outreach for {buyer.name}")
        return draft

    def run(
        self,
        requests: list[BuyerResearchRequest],
    ) -> list[BuyerProfile]:
        """Process a batch of buyer research requests."""
        profiles: list[BuyerProfile] = []
        for req in requests:
            try:
                profile = self.identify_buyer(req)
                profiles.append(profile)
            except Exception as exc:
                logger.error(f"[{self.name}] Failed to identify buyer from {req.platform}: {exc}")
        return profiles
