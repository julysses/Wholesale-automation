"""
AI Qualification Agent — LLM-powered call transcript analyzer.

Blueprint qualification scoring formula:

POSITIVE signals
  timeline_immediate   = +30
  timeline_30_days     = +25
  timeline_60_days     = +15
  timeline_3_6_months  = +10
  vacant_property      = +20
  tenant_occupied      = +10
  needs_repairs        = +15
  major_repairs        = +20
  seller_named_price   = +15

NEGATIVE signals
  no_interest          = -50
  hangup               = -20

FINAL CLASSIFICATION
  HOT  = score >= 80
  WARM = score 50–79
  COLD = score < 50
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Qualification score weights ───────────────────────────────────────────────

TIMELINE_SCORES: dict[str, int] = {
    "immediately":     30,
    "30_days":         25,
    "60_days":         15,
    "3_to_6_months":   10,
    "no_timeline":      0,
}

OCCUPANCY_SCORES: dict[str, int] = {
    "vacant":           20,
    "tenant_occupied":  10,
    "owner_occupied":    0,
}

CONDITION_SCORES: dict[str, int] = {
    "major_repairs":    20,
    "needs_repairs":    15,
    "minor_repairs":     5,
    "fully_updated":     0,
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class QualificationResult:
    """Structured output from the qualification agent."""

    # Extracted signals
    timeline: str = "no_timeline"           # immediately | 30_days | 60_days | 3_to_6_months | no_timeline
    condition: str = "fully_updated"        # fully_updated | minor_repairs | needs_repairs | major_repairs
    occupancy: str = "owner_occupied"       # owner_occupied | tenant_occupied | vacant
    asking_price: Optional[float] = None
    mortgage_balance: Optional[float] = None
    sentiment: str = "neutral"              # motivated | neutral | hesitant | not_interested

    # Negative signals detected in transcript
    expressed_no_interest: bool = False
    hung_up: bool = False
    named_price: bool = False

    # Computed scores
    qualification_score: int = 0
    classification: str = "COLD"            # HOT | WARM | COLD

    # LLM analysis
    summary: str = ""
    key_quotes: list[str] = field(default_factory=list)
    offer_range_low: Optional[float] = None
    offer_range_high: Optional[float] = None
    score_breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def is_hot(self) -> bool:
        return self.classification == "HOT"

    @property
    def is_warm(self) -> bool:
        return self.classification == "WARM"

    @property
    def is_callable(self) -> bool:
        return self.classification in ("HOT", "WARM")


def compute_qualification_score(result: QualificationResult) -> tuple[int, dict[str, int]]:
    """
    Apply blueprint qualification scoring formula.
    Returns (total_score, score_breakdown).
    """
    breakdown: dict[str, int] = {}

    # Timeline
    timeline_pts = TIMELINE_SCORES.get(result.timeline, 0)
    if timeline_pts:
        breakdown[f"timeline_{result.timeline}"] = timeline_pts

    # Occupancy
    occ_pts = OCCUPANCY_SCORES.get(result.occupancy, 0)
    if occ_pts:
        breakdown[f"occupancy_{result.occupancy}"] = occ_pts

    # Condition
    cond_pts = CONDITION_SCORES.get(result.condition, 0)
    if cond_pts:
        breakdown[f"condition_{result.condition}"] = cond_pts

    # Seller named a price
    if result.named_price:
        breakdown["seller_named_price"] = 15

    # Negative signals
    if result.expressed_no_interest:
        breakdown["no_interest"] = -50
    if result.hung_up:
        breakdown["hangup"] = -20

    total = sum(breakdown.values())
    return total, breakdown


def classify_score(score: int) -> str:
    if score >= 80:
        return "HOT"
    if score >= 50:
        return "WARM"
    return "COLD"


# ── Agent ──────────────────────────────────────────────────────────────────────

class QualificationAgent:
    """
    Uses Claude claude-sonnet-4-6 to parse a call transcript and extract structured
    qualification signals. Falls back to keyword heuristics if the API
    key is not set.
    """

    name = "qualification_agent"

    _SYSTEM_PROMPT = """
You are a real estate acquisitions analyst. You will receive a call transcript
between an AI agent and a property owner. Extract the seller's qualification
signals and return ONLY a valid JSON object — no markdown, no explanation.

JSON schema:
{
  "timeline": "<immediately|30_days|60_days|3_to_6_months|no_timeline>",
  "condition": "<fully_updated|minor_repairs|needs_repairs|major_repairs>",
  "occupancy": "<owner_occupied|tenant_occupied|vacant>",
  "asking_price": <number or null>,
  "mortgage_balance": <number or null>,
  "sentiment": "<motivated|neutral|hesitant|not_interested>",
  "expressed_no_interest": <true|false>,
  "hung_up": <true|false>,
  "named_price": <true|false>,
  "summary": "<1-2 sentence summary of call>",
  "key_quotes": ["<exact quote 1>", "<exact quote 2>"]
}

Rules:
- Use only the enum values listed above. Never invent new ones.
- asking_price and mortgage_balance are numbers (no $ or commas).
- If the seller didn't mention a field, use the default (null / false / the first enum option).
- expressed_no_interest = true only if the seller explicitly said they are not interested.
- hung_up = true only if the transcript shows the seller disconnected abruptly.
- named_price = true if the seller stated any dollar amount as their asking price.
""".strip()

    def __init__(self) -> None:
        self._client: Optional[anthropic.Anthropic] = None
        if settings.anthropic_api_key:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        else:
            logger.warning(f"[{self.name}] ANTHROPIC_API_KEY not set — using heuristic fallback")

    def analyze_transcript(
        self,
        transcript: str,
        property_address: str = "",
        owner_name: str = "",
    ) -> QualificationResult:
        """
        Analyze a call transcript and return a scored QualificationResult.

        First attempts LLM analysis; falls back to keyword heuristics if the
        API is unavailable.
        """
        if not transcript or not transcript.strip():
            return self._empty_result()

        raw: dict = {}
        if self._client:
            raw = self._llm_analyze(transcript, property_address, owner_name)
        else:
            raw = self._heuristic_analyze(transcript)

        result = self._build_result(raw)
        score, breakdown = compute_qualification_score(result)
        result.qualification_score = score
        result.classification = classify_score(score)
        result.score_breakdown = breakdown

        # Estimate offer range if asking_price is known
        if result.asking_price:
            result.offer_range_high = round(result.asking_price * 0.85, -3)
            result.offer_range_low  = round(result.asking_price * 0.70, -3)

        logger.info(
            f"[{self.name}] score={score} class={result.classification} "
            f"timeline={result.timeline} condition={result.condition} "
            f"occupancy={result.occupancy} sentiment={result.sentiment}"
        )
        return result

    def _llm_analyze(
        self,
        transcript: str,
        property_address: str,
        owner_name: str,
    ) -> dict:
        """Call Claude to extract structured qualification signals."""
        user_content = (
            f"Property: {property_address}\n"
            f"Owner: {owner_name}\n\n"
            f"TRANSCRIPT:\n{transcript[:8000]}"  # stay within context budget
        )
        try:
            msg = self._client.messages.create(  # type: ignore[union-attr]
                model=settings.claude_model,
                max_tokens=512,
                system=self._SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = msg.content[0].text.strip()
            # Strip accidental markdown fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error(f"[{self.name}] JSON parse error: {exc}")
            return {}
        except Exception as exc:
            logger.error(f"[{self.name}] LLM call failed: {exc}")
            return {}

    def _heuristic_analyze(self, transcript: str) -> dict:
        """Keyword-based fallback when LLM is unavailable."""
        t = transcript.lower()

        timeline = "no_timeline"
        if any(w in t for w in ("asap", "immediately", "right away", "as soon as")):
            timeline = "immediately"
        elif "30 day" in t or "next month" in t:
            timeline = "30_days"
        elif "60 day" in t or "two month" in t:
            timeline = "60_days"
        elif any(w in t for w in ("3 month", "6 month", "few month", "couple month")):
            timeline = "3_to_6_months"

        condition = "fully_updated"
        if any(w in t for w in ("major repair", "gut", "tear down", "foundation", "fire damage", "flood")):
            condition = "major_repairs"
        elif any(w in t for w in ("need repair", "needs work", "fixer", "fix up", "rehab")):
            condition = "needs_repairs"
        elif any(w in t for w in ("minor repair", "cosmetic", "paint", "carpet")):
            condition = "minor_repairs"

        occupancy = "owner_occupied"
        if any(w in t for w in ("vacant", "empty", "nobody living", "no one living")):
            occupancy = "vacant"
        elif any(w in t for w in ("tenant", "renter", "renting", "leased")):
            occupancy = "tenant_occupied"

        no_interest = any(w in t for w in ("not interested", "don't want to sell", "not selling", "take me off"))
        hung_up = "[call ended" in t or "disconnected" in t

        sentiment = "neutral"
        if any(w in t for w in ("motivated", "desperate", "need to sell", "have to sell", "behind on", "foreclosure")):
            sentiment = "motivated"
        elif no_interest:
            sentiment = "not_interested"

        return {
            "timeline": timeline,
            "condition": condition,
            "occupancy": occupancy,
            "asking_price": None,
            "mortgage_balance": None,
            "sentiment": sentiment,
            "expressed_no_interest": no_interest,
            "hung_up": hung_up,
            "named_price": False,
            "summary": "Heuristic analysis (LLM unavailable)",
            "key_quotes": [],
        }

    @staticmethod
    def _build_result(raw: dict) -> QualificationResult:
        """Map raw dict to QualificationResult, applying safe defaults."""
        valid_timelines   = set(TIMELINE_SCORES.keys())
        valid_occupancies = set(OCCUPANCY_SCORES.keys())
        valid_conditions  = set(CONDITION_SCORES.keys())
        valid_sentiments  = {"motivated", "neutral", "hesitant", "not_interested"}

        timeline  = raw.get("timeline", "no_timeline")
        occupancy = raw.get("occupancy", "owner_occupied")
        condition = raw.get("condition", "fully_updated")
        sentiment = raw.get("sentiment", "neutral")

        # Coerce to valid enum values
        if timeline  not in valid_timelines:   timeline  = "no_timeline"
        if occupancy not in valid_occupancies: occupancy = "owner_occupied"
        if condition not in valid_conditions:  condition = "fully_updated"
        if sentiment not in valid_sentiments:  sentiment = "neutral"

        asking = raw.get("asking_price")
        mortgage = raw.get("mortgage_balance")

        return QualificationResult(
            timeline=timeline,
            condition=condition,
            occupancy=occupancy,
            asking_price=float(asking) if asking else None,
            mortgage_balance=float(mortgage) if mortgage else None,
            sentiment=sentiment,
            expressed_no_interest=bool(raw.get("expressed_no_interest", False)),
            hung_up=bool(raw.get("hung_up", False)),
            named_price=bool(raw.get("named_price", False)),
            summary=str(raw.get("summary", "")),
            key_quotes=list(raw.get("key_quotes", [])),
        )

    @staticmethod
    def _empty_result() -> QualificationResult:
        result = QualificationResult()
        result.qualification_score = 0
        result.classification = "COLD"
        result.score_breakdown = {}
        return result
