"""
Facebook Ads Command Center — Claude advisory API endpoints.

Routes (all under /api/ai/fb-ads):
  POST /api/ai/fb-ads/review-copy         — Review ad copy against battle plan
  POST /api/ai/fb-ads/review-headline     — Review ad headline
  POST /api/ai/fb-ads/preflight-summary   — Generate pre-flight campaign summary
  POST /api/ai/fb-ads/performance-alerts  — Analyze performance and return alerts
  POST /api/ai/fb-ads/score-campaign      — Compute battle plan compliance score
  POST /api/ai/fb-ads/explain-section     — Explain a battle plan section
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai/fb-ads", tags=["FB Ads Claude Advisor"])

_client: Optional[anthropic.Anthropic] = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client

HAIKU = "claude-haiku-4-5-20251001"

def _call(system: str, user: str, model: str = HAIKU, max_tokens: int = 1024) -> Any:
    client = _get_client()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json\n").strip() if len(parts) > 1 else raw
    return raw


def _call_json(endpoint: str, system: str, user: str, max_tokens: int = 1024):
    """Call Claude, parse JSON response, raise HTTP 500 on any failure."""
    try:
        return json.loads(_call(system, user, max_tokens=max_tokens))
    except Exception as exc:
        logger.error(f"{endpoint} failed: {exc}")
        raise HTTPException(500, str(exc))


# ── Review Ad Copy ─────────────────────────────────────────────────────────────

class ReviewCopyRequest(BaseModel):
    copy: str
    segment: str = "pre-foreclosure"


@router.post("/review-copy")
def review_copy(body: ReviewCopyRequest):
    system = (
        "You are a Facebook ad copy compliance reviewer for a Texas real estate wholesaler. "
        "You enforce the approved battle plan: pain-point reference, local DFW signal, CTA, "
        "no generic 'We Buy Houses' openers, strong emotional hook. "
        "Output ONLY valid JSON matching the schema provided."
    )
    user = f"""Review this Facebook ad copy for the "{body.segment}" segment:

COPY:
{body.copy}

Evaluate:
1. Does it reference the seller's pain point?
2. Does it mention DFW, Dallas, Texas, or a local signal?
3. Is there a clear CTA?
4. Does it use any generic "we buy houses" / "we buy homes" openers?
5. How strong is the emotional hook? (strong/moderate/weak)
6. Any specific flags?

Return ONLY this JSON:
{{
  "pain_point_present": <boolean>,
  "local_signal": <boolean>,
  "cta_present": <boolean>,
  "generic_detected": <boolean>,
  "emotional_hook": "<strong|moderate|weak>",
  "flags": ["<specific issue 1>", "<specific issue 2>"],
  "score": <0-100>
}}"""

    return _call_json("review-copy", system, user)


# ── Review Headline ────────────────────────────────────────────────────────────

class ReviewHeadlineRequest(BaseModel):
    headline: str
    segment: str = "pre-foreclosure"


@router.post("/review-headline")
def review_headline(body: ReviewHeadlineRequest):
    system = (
        "You are a Facebook ad headline reviewer. You enforce the battle plan: segment-specific "
        "pain point, under 10 words, no generic phrases, no fair housing risk language. "
        "Output ONLY valid JSON."
    )
    user = f"""Review this headline for the "{body.segment}" segment:

HEADLINE: {body.headline}

Word count: {len(body.headline.split())}

Check:
- Pain point reference for this segment
- Word count (10 word max for Meta)
- Generic phrase detection ("we buy houses", "cash for houses", etc.)
- Any fair housing language risk
- Overall score

Return ONLY this JSON:
{{
  "score": <0-100>,
  "pain_point_present": <boolean>,
  "local_signal_present": <boolean>,
  "cta_present": <boolean>,
  "emotional_hook_strength": "<strong|moderate|weak>",
  "generic_detected": <boolean>,
  "flags": ["<issue>"],
  "suggestion": "<improved headline if score < 80, else null>"
}}"""

    return _call_json("review-headline", system, user)


# ── Pre-Flight Summary ─────────────────────────────────────────────────────────

class PreFlightRequest(BaseModel):
    wizard_state: dict


@router.post("/preflight-summary")
def preflight_summary(body: PreFlightRequest):
    system = (
        "You are a Facebook Ads campaign analyst for a DFW Texas real estate wholesaler. "
        "Generate a plain-language campaign intelligence summary and CPL estimate. "
        "Output ONLY valid JSON."
    )
    state = body.wizard_state
    step1 = state.get("step1", {})
    step2 = state.get("step2", {})
    step3 = state.get("step3", {})

    audiences = step2.get("custom_audiences", [])
    total_records = sum(a.get("recordCount", 0) for a in audiences)
    tier1_count = len(step2.get("tier1_signals", []))
    counties = step2.get("counties", [])
    ad_sets = step3.get("ad_sets", [])

    user = f"""Analyze this Facebook campaign setup:

Campaign: {step1.get('name', 'Draft')}
Daily Budget: ${step1.get('daily_budget', 25)}/day
Custom Audiences: {len(audiences)} ({total_records:,} total records)
Tier 1 Distress Signals: {tier1_count}
DFW Counties: {', '.join(counties)}
Ad Sets: {len(ad_sets)} (segments: {', '.join(a.get('segment', '') for a in ad_sets)})
A/B Testing: {step1.get('ab_test_enabled', True)}

Market context: DFW, Texas. Motivated seller real estate. Facebook Lead Ads.
Battle plan CPL targets: $18–$35 cold audience, $8–$14 retargeting.

Provide:
1. A 2-3 sentence plain-language campaign summary
2. Estimated CPL range for cold audience based on audience quality and size
3. Estimated CPL range for retargeting (if applicable)
4. One specific actionable recommendation

Return ONLY this JSON:
{{
  "summary": "<2-3 sentence campaign summary>",
  "estimated_cpl_cold": "<$X–$Y range>",
  "estimated_cpl_retargeting": "<$X–$Y range>",
  "recommendation": "<one specific actionable recommendation>"
}}"""

    return _call_json("preflight-summary", system, user, max_tokens=512)


# ── Performance Alerts ─────────────────────────────────────────────────────────

class PerformanceAlertsRequest(BaseModel):
    performance_data: list


@router.post("/performance-alerts")
def performance_alerts(body: PerformanceAlertsRequest):
    if not body.performance_data:
        return []

    system = (
        "You are a Facebook Ads performance analyst for a DFW real estate wholesaler. "
        "Identify issues against battle plan thresholds and return actionable alerts. "
        "Output ONLY a valid JSON array."
    )
    user = f"""Analyze this campaign performance data against battle plan thresholds:

Performance Data (last entries):
{json.dumps(body.performance_data[-20:], default=str, indent=2)}

Battle plan thresholds:
- CPL > $40 for 5+ days = urgent flag
- Frequency > 3.0 = warning (audience fatigue)
- Contact rate < 40% = warning
- 50 leads accumulated = info (lookalike threshold reached)

Return ONLY a JSON array of alerts:
[
  {{
    "type": "<urgent|warning|info>",
    "ad_set": "<ad set name or 'All Campaigns'>",
    "message": "<specific issue description>",
    "recommendation": "<specific action to take>"
  }}
]

Return empty array [] if no issues found. Maximum 5 alerts."""

    result = _call_json("performance-alerts", system, user, max_tokens=1024)
    return result if isinstance(result, list) else []


# ── Score Campaign ─────────────────────────────────────────────────────────────

class ScoreCampaignRequest(BaseModel):
    campaign: dict


@router.post("/score-campaign")
def score_campaign(body: ScoreCampaignRequest):
    system = (
        "You are a battle plan compliance auditor for a DFW real estate Facebook Ads campaign. "
        "Score the campaign 0-100 based on adherence to approved settings and strategy. "
        "Output ONLY valid JSON."
    )
    user = f"""Score this live campaign for battle plan compliance:

Campaign Data:
{json.dumps(body.campaign, default=str, indent=2)}

Battle plan requirements:
- Objective: Leads (required)
- Special Ad Category: Housing ON (required)
- Daily budget: $20-$100 (required)
- A/B testing: ON (recommended)
- At least one distress signal or custom audience
- Marketplace placement ON
- Audience Network OFF
- Segment-matched headlines (no generic copy)

Return ONLY:
{{
  "score": <0-100>,
  "flags": ["<specific compliance issue>"]
}}"""

    return _call_json("score-campaign", system, user, max_tokens=256)


# ── Explain Section ────────────────────────────────────────────────────────────

class ExplainSectionRequest(BaseModel):
    section_title: str
    content: str


@router.post("/explain-section")
def explain_section(body: ExplainSectionRequest):
    system = (
        "You are a Facebook Ads strategy expert for real estate wholesalers. "
        "Explain battle plan concepts clearly and concisely. "
        "Write in plain language for a non-technical operator."
    )
    user = f"""Explain the strategic rationale behind this battle plan element in 3-4 sentences.
Write in plain, direct language — no jargon, no fluff.

Section: {body.section_title}

Content:
{body.content[:500]}

Explain WHY this matters and WHAT happens if it's ignored."""

    try:
        return {"explanation": _call(system, user, max_tokens=300)}
    except Exception as exc:
        logger.error(f"explain-section failed: {exc}")
        raise HTTPException(500, str(exc))
