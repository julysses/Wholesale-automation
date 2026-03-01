"""
Buyer Sourcing Agent — ethical, permission-based buyer identification.
Uses only approved outreach templates (Section 4).
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from config.prompts import SystemPrompts
from config.settings import settings
from schemas.buyer import BuyerProfile, BuyerSource, BuyerStrategy
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Approved outreach templates (Section 4) ───────────────────────────────────

FACEBOOK_DM_TEMPLATE = (
    "Hi {buyer_name},\n"
    "I'm local to {city} and saw your post in {group_name}.\n"
    "I'm building a small off-market pipeline in Texas and wanted to ask whether "
    "you'd be open to receiving deals that actually match your buy box.\n"
    "No blast lists—only relevant properties. Totally fine if not.\n"
    "— {sender_name}"
)

INSTITUTIONAL_EMAIL_SUBJECT = "Texas Off-Market Opportunities (Permission-Based)"

INSTITUTIONAL_EMAIL_TEMPLATE = (
    "Hi {buyer_name},\n\n"
    "I'm based in Texas and focus on sourcing off-market residential and light "
    "multifamily opportunities in specific local markets.\n\n"
    "Before sharing anything, I wanted to ask whether you're open to reviewing "
    "opportunities aligned with your acquisition criteria.\n\n"
    "If so, I'd appreciate learning your preferred markets and deal size.\n\n"
    "Best regards,\n"
    "{sender_name}"
)


class BuyerResearchRequest(BaseModel):
    platform: str  # "facebook_group" | "bigger_pockets" | "reia" | etc.
    platform_url: str = ""
    market_focus: str = "Texas"
    raw_profile_text: str  # publicly observed info about the buyer
    source: BuyerSource
    group_name: str = ""  # for Facebook DM template
    city: str = "Texas"   # for Facebook DM template


class BuyerOutreachDraft(BaseModel):
    subject: str = ""       # for email
    body: str
    tone_assessment: str
    platform: str
    template_used: str = ""  # which approved template was rendered


class BuyerSourcingAgent(BaseAgent):
    name = "buyer_sourcing_agent"
    system_prompt = SystemPrompts.BUYER_SOURCING

    def identify_buyer(self, request: BuyerResearchRequest) -> BuyerProfile:
        """Extract a structured buyer profile from publicly observed profile text."""
        prompt = f"""
Extract a buyer profile from this publicly observed information.

Platform: {request.platform}
Platform URL: {request.platform_url}
Market focus: {request.market_focus}
Observed public profile / post text:
{request.raw_profile_text}

Instructions:
- Extract: name, company (if mentioned), inferred buy box (markets, price range, strategy)
- Only use information clearly present in the text — do NOT invent contact info
- Set permission_granted to false (requires explicit opt-in from buyer)
- source should be "{request.source.value}"
- source_platform_url should be "{request.platform_url}"
- inferred_buy_box should be a 1–2 sentence summary
"""
        profile = self._call_structured(prompt, BuyerProfile)
        profile.source = request.source
        profile.source_platform_url = request.platform_url
        profile.permission_granted = False  # always enforce — requires explicit opt-in

        logger.info(
            f"[{self.name}] Identified buyer '{profile.name}' from {request.platform}"
        )
        return profile

    def draft_facebook_outreach(
        self,
        buyer: BuyerProfile,
        request: Optional[BuyerResearchRequest] = None,
    ) -> BuyerOutreachDraft:
        """
        Render the approved Facebook/forum DM template (Section 4).
        No Claude generation — template is fixed.
        """
        city = (buyer.markets[0] if buyer.markets else None) or (
            request.city if request else "Texas"
        )
        group_name = (request.group_name if request else "") or "the group"
        buyer_first = buyer.name.split()[0] if buyer.name else "there"

        body = FACEBOOK_DM_TEMPLATE.format(
            buyer_name=buyer_first,
            city=city,
            group_name=group_name,
            sender_name=settings.agency_contact_name,
        )

        logger.info(f"[{self.name}] Rendered Facebook DM template for buyer {buyer.name}")
        return BuyerOutreachDraft(
            body=body,
            tone_assessment="peer-to-peer, permission-based, no pitch",
            platform="facebook_or_forum",
            template_used="FACEBOOK_DM_TEMPLATE",
        )

    def draft_institutional_outreach(
        self,
        buyer: BuyerProfile,
        context: str = "",
    ) -> BuyerOutreachDraft:
        """
        Render the approved institutional email template (Section 4).
        Claude may add market-specific detail within the approved structure.
        """
        buyer_first = buyer.name.split()[0] if buyer.name else "there"

        # Render the base approved template
        base_body = INSTITUTIONAL_EMAIL_TEMPLATE.format(
            buyer_name=buyer_first,
            sender_name=settings.agency_contact_name,
        )

        # If buyer has specific market context, ask Claude to add one personalized line
        # within the approved structure (no deviation from tone rules)
        if buyer.markets or buyer.company:
            prompt = f"""
The approved institutional outreach template is:

Subject: {INSTITUTIONAL_EMAIL_SUBJECT}

{base_body}

Personalize ONLY the first sentence of paragraph 2 ("Before sharing anything...")
to reference the buyer's specific markets or company if known.

Buyer context:
- Name: {buyer_first}
- Company: {buyer.company or "not specified"}
- Markets: {buyer.markets or "not specified"}
- Additional context: {context or "None"}

HARD RULES:
- Do NOT change the template structure
- Do NOT add urgency, pressure, or promotional language
- Do NOT make any claims about deal volume or exclusivity
- Maximum one added clause referencing their market/company
- Keep total email under 120 words
- Tone: professional, peer-to-peer, permission-based

Return body (full email text), tone_assessment, platform="email",
template_used="INSTITUTIONAL_EMAIL_TEMPLATE".
Subject line must remain: "{INSTITUTIONAL_EMAIL_SUBJECT}"
"""
            draft = self._call_structured(prompt, BuyerOutreachDraft)
            draft.subject = INSTITUTIONAL_EMAIL_SUBJECT
            draft.platform = "email"
            draft.template_used = "INSTITUTIONAL_EMAIL_TEMPLATE"
            logger.info(f"[{self.name}] Rendered institutional email for {buyer.name}")
            return draft

        logger.info(f"[{self.name}] Rendered institutional email template for {buyer.name}")
        return BuyerOutreachDraft(
            subject=INSTITUTIONAL_EMAIL_SUBJECT,
            body=base_body,
            tone_assessment="professional, permission-based, no pitch",
            platform="email",
            template_used="INSTITUTIONAL_EMAIL_TEMPLATE",
        )

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
                logger.error(
                    f"[{self.name}] Failed to identify buyer from {req.platform}: {exc}"
                )
        return profiles
