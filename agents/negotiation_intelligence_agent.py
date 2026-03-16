"""
Negotiation Intelligence Agent

For HOT sellers, generates a complete negotiation brief:
  • seller pain points (derived from transcript + distress signals)
  • suggested opening offer
  • maximum ceiling offer
  • objection handlers (scripted responses to common objections)
  • recommended exit strategy

PRD exit strategies:
  wholesale assignment   — assign contract to cash buyer
  novation agreement     — list and sell on MLS, collect spread at closing
  wholetail sale         — light rehab, list at discount for quick sale
  investor resale        — sell to landlord / rental investor as-is
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Exit strategy definitions ─────────────────────────────────────────────────

EXIT_STRATEGIES = {
    "wholesale_assignment": {
        "label": "Wholesale Assignment",
        "description": "Assign purchase contract to cash buyer. Fast close, minimal risk.",
        "best_for": "Heavy repairs, motivated seller, tight timeline",
    },
    "novation_agreement": {
        "label": "Novation Agreement",
        "description": "List property on MLS and collect spread at closing. No upfront capital.",
        "best_for": "Reluctant seller, light repairs, higher ARV market",
    },
    "wholetail": {
        "label": "Wholetail Sale",
        "description": "Buy, make cosmetic improvements, list at slight discount for quick sale.",
        "best_for": "Minor repairs, ARV > $200k, suburban market",
    },
    "investor_resale": {
        "label": "Investor Resale",
        "description": "Sell as-is to landlord or rental investor at as-is value.",
        "best_for": "Tenant-occupied, cash-flow market, landlord buyers available",
    },
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ObjectionHandler:
    objection: str
    response: str


@dataclass
class NegotiationBrief:
    lead_id: str
    property_address: str
    owner_name: str

    # Seller psychology
    pain_points: list[str] = field(default_factory=list)
    motivation_level: str = "medium"   # low | medium | high | urgent

    # Offer guidance (from DealAnalysis)
    opening_offer: float = 0.0
    ceiling_offer: float = 0.0      # = MAO (never exceed)
    target_offer: float = 0.0       # sweet spot

    # Exit strategy
    primary_exit: str = "wholesale_assignment"
    secondary_exit: str = "investor_resale"
    exit_rationale: str = ""

    # Objection handlers
    objection_handlers: list[ObjectionHandler] = field(default_factory=list)

    # AI-generated talking points
    opening_script: str = ""
    closing_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "property_address": self.property_address,
            "owner_name": self.owner_name,
            "pain_points": self.pain_points,
            "motivation_level": self.motivation_level,
            "opening_offer": self.opening_offer,
            "ceiling_offer": self.ceiling_offer,
            "target_offer": self.target_offer,
            "primary_exit": self.primary_exit,
            "secondary_exit": self.secondary_exit,
            "exit_rationale": self.exit_rationale,
            "objection_handlers": [
                {"objection": oh.objection, "response": oh.response}
                for oh in self.objection_handlers
            ],
            "opening_script": self.opening_script,
            "closing_notes": self.closing_notes,
        }


# ── Default objection library ─────────────────────────────────────────────────

DEFAULT_OBJECTIONS: list[tuple[str, str]] = [
    (
        "Your offer is too low",
        "I completely understand — I want to be fair with you. Our offer reflects the "
        "cost of repairs and the fact that we close quickly with cash, no contingencies, "
        "and on your timeline. Can I ask what number would work for you?"
    ),
    (
        "I need to think about it",
        "Of course, take all the time you need. I do want to mention that our cash "
        "position is committed right now. If timing becomes a concern, I'm happy to "
        "revisit. Would it help if I called you Thursday to see where your head is at?"
    ),
    (
        "I already have a realtor",
        "That's great — working with an agent is a solid option. One thing we offer "
        "that's different: we close in 2–3 weeks with zero commissions, repairs, or "
        "showings. It might be worth comparing both options side by side."
    ),
    (
        "I don't want to sell",
        "I respect that completely. If anything changes — a tenant issue, tax bill, "
        "or you just decide the time is right — please keep my number. We work on "
        "your schedule, not ours."
    ),
    (
        "I owe more than you're offering",
        "That's helpful to know. We do have options — including a subject-to purchase "
        "or a short sale if the lender agrees. Would it be okay if I had our deal "
        "structuring team reach out to walk through what's possible?"
    ),
]


# ── Agent ─────────────────────────────────────────────────────────────────────

class NegotiationIntelligenceAgent:
    """
    Generates a seller-specific negotiation brief using the call transcript
    and deal analysis outputs.

    Uses Claude to personalize pain points and opening script.
    Falls back to rule-based brief if LLM unavailable.
    """

    name = "negotiation_intelligence_agent"

    _SYSTEM_PROMPT = """
You are a real estate negotiation specialist. Given seller call transcript and
deal details, generate a personalized negotiation brief.

Return ONLY a valid JSON object (no markdown, no explanation):
{
  "pain_points": ["<specific pain point 1>", "<specific pain point 2>", "<specific pain point 3>"],
  "motivation_level": "<low|medium|high|urgent>",
  "opening_script": "<2-3 sentence opening the acquisitions manager should use>",
  "closing_notes": "<1-2 sentence tactical note for closing the deal>",
  "exit_rationale": "<1 sentence explaining why this exit strategy fits>",
  "custom_objections": [
    {"objection": "<seller-specific concern>", "response": "<tailored response>"}
  ]
}

Rules:
- Pain points must be SPECIFIC to this seller, not generic.
- opening_script should reference the seller by name and their specific situation.
- motivation_level = urgent if seller mentioned foreclosure, eviction, death, divorce, or financial hardship.
""".strip()

    def __init__(self) -> None:
        self._client = None
        if settings.anthropic_api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            except Exception as exc:
                logger.warning(f"[{self.name}] Anthropic init failed: {exc}")

    def generate_brief(
        self,
        lead_id: str,
        property_address: str,
        owner_name: str,
        transcript: str,
        opening_offer: float,
        ceiling_offer: float,
        exit_strategy: str = "wholesale_assignment",
        secondary_exit: str = "investor_resale",
        sentiment: str = "neutral",
        timeline: str = "no_timeline",
        condition: str = "needs_repairs",
        occupancy: str = "owner_occupied",
    ) -> NegotiationBrief:
        """
        Build a negotiation brief for an acquisition manager meeting a HOT seller.
        """
        target_offer = round((opening_offer + ceiling_offer) / 2, -3)

        if self._client:
            llm_data = self._llm_enrich(
                transcript, owner_name, property_address,
                opening_offer, ceiling_offer, exit_strategy, timeline, occupancy,
            )
        else:
            llm_data = self._rule_based_brief(
                owner_name, property_address, sentiment, timeline,
                condition, occupancy, opening_offer,
            )

        # Build objection handler list (default set + LLM custom)
        handlers = [ObjectionHandler(o, r) for o, r in DEFAULT_OBJECTIONS]
        for custom in llm_data.get("custom_objections", []):
            handlers.insert(0, ObjectionHandler(
                custom.get("objection", ""),
                custom.get("response", ""),
            ))

        return NegotiationBrief(
            lead_id=lead_id,
            property_address=property_address,
            owner_name=owner_name,
            pain_points=llm_data.get("pain_points", []),
            motivation_level=llm_data.get("motivation_level", "medium"),
            opening_offer=opening_offer,
            ceiling_offer=ceiling_offer,
            target_offer=target_offer,
            primary_exit=exit_strategy,
            secondary_exit=secondary_exit,
            exit_rationale=llm_data.get(
                "exit_rationale",
                EXIT_STRATEGIES.get(exit_strategy, {}).get("description", ""),
            ),
            objection_handlers=handlers,
            opening_script=llm_data.get("opening_script", ""),
            closing_notes=llm_data.get("closing_notes", ""),
        )

    def _llm_enrich(
        self,
        transcript: str,
        owner_name: str,
        property_address: str,
        opening_offer: float,
        ceiling_offer: float,
        exit_strategy: str,
        timeline: str,
        occupancy: str,
    ) -> dict:
        prompt = (
            f"Owner: {owner_name}\n"
            f"Property: {property_address}\n"
            f"Recommended exit: {exit_strategy}\n"
            f"Timeline: {timeline}\n"
            f"Occupancy: {occupancy}\n"
            f"Opening offer: ${opening_offer:,.0f}\n"
            f"Ceiling (MAO): ${ceiling_offer:,.0f}\n\n"
            f"CALL TRANSCRIPT:\n{transcript[:6000]}"
        )
        try:
            msg = self._client.messages.create(  # type: ignore[union-attr]
                model=settings.claude_model,
                max_tokens=600,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            return json.loads(text)
        except Exception as exc:
            logger.error(f"[{self.name}] LLM call failed: {exc}")
            return {}

    @staticmethod
    def _rule_based_brief(
        owner_name: str,
        address: str,
        sentiment: str,
        timeline: str,
        condition: str,
        occupancy: str,
        opening_offer: float,
    ) -> dict:
        """Fallback brief when LLM is unavailable."""
        pain_points = []
        if timeline in ("immediately", "30_days"):
            pain_points.append("Seller is under time pressure to sell quickly")
        if occupancy == "vacant":
            pain_points.append("Property is vacant — ongoing holding costs with no income")
        if condition in ("needs_repairs", "major_repairs"):
            pain_points.append("Property needs significant repairs — difficult to sell retail")
        if not pain_points:
            pain_points = ["Seller has not revealed specific pain points yet"]

        motivation_map = {
            "motivated": "high",
            "neutral":   "medium",
            "hesitant":  "low",
            "not_interested": "low",
        }
        motivation = motivation_map.get(sentiment, "medium")
        if timeline == "immediately":
            motivation = "urgent"

        script = (
            f"Hi {owner_name}, this is [name] following up on the property at {address}. "
            f"I wanted to reconnect and see if you're still open to discussing a cash offer. "
            f"We can move quickly — our team is ready to close in as little as two weeks."
        )

        return {
            "pain_points": pain_points,
            "motivation_level": motivation,
            "opening_script": script,
            "closing_notes": "Emphasize speed and certainty. Avoid low-balling — start at opening offer.",
            "exit_rationale": "Rule-based selection (LLM unavailable)",
            "custom_objections": [],
        }
