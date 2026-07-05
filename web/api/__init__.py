"""
FastAPI REST endpoints bridging the React frontend (WholesaleOS) to our Python AI agents.
These replace the four Supabase Edge Functions from wholesale-control-center.

Routes:
  POST /api/ai/qualify-lead      → Lead qualification (5-factor scoring)
  POST /api/ai/generate-offer    → Strategic offer generation
  POST /api/ai/write-outreach    → Compliant outreach copy
  POST /api/ai/match-buyers      → Buyer matching & blast templates
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI Agents"])

# ── Claude client ──────────────────────────────────────────────────────────────

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise HTTPException(503, detail="ANTHROPIC_API_KEY not configured")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _call_claude(system: str, user: str, max_tokens: int = 2048) -> Any:
    """Call Claude and return parsed JSON. Strips markdown fences if present."""
    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    return json.loads(raw)


# ── 1. Lead Qualifier ──────────────────────────────────────────────────────────

class QualifyLeadRequest(BaseModel):
    lead_id: str | None = None
    property_address: str = ""
    city: str | None = None
    state: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    motivation_tag: str | None = None
    seller_notes: str | None = None
    estimated_equity_pct: float | None = None
    loan_balance: float | None = None
    estimated_arv: float | None = None
    contact_attempts: int = 0
    ai_qualification_summary: str | None = None
    # Accept any extra fields the React app sends
    model_config = {"extra": "allow"}


@router.post("/qualify-lead")
def qualify_lead(body: QualifyLeadRequest) -> dict:
    lead_data = body.model_dump(exclude_none=True)

    system = (
        "You are an expert Texas real estate wholesaler with 15+ years of experience "
        "identifying motivated sellers. Analyze leads and output ONLY valid JSON, no prose or markdown."
    )
    user = f"""Analyze this wholesale real estate lead and score each of 5 factors from 1 (weak) to 3 (strong).

LEAD DATA:
{json.dumps(lead_data, default=str, indent=2)}

Score these factors:
- score_motivation: How motivated is the seller? (distress signals, financial pressure, life event)
- score_timeline: How urgent is their timeline? (must sell now vs. just exploring)
- score_equity: How much equity do they likely have? (loan balance vs. estimated ARV)
- score_condition: What is the likely property condition? (deferred maintenance, description clues)
- score_flexibility: How flexible on price and terms?

Return ONLY this JSON object:
{{
  "score_motivation": <1-3>,
  "score_timeline": <1-3>,
  "score_equity": <1-3>,
  "score_condition": <1-3>,
  "score_flexibility": <1-3>,
  "total_score": <sum of 5 scores>,
  "tier": "<HOT|WARM|COLD>",
  "qualification_summary": "<2-3 sentence summary of this seller's situation>",
  "recommended_next_action": "<specific, actionable next step>",
  "key_risks": ["<risk1>", "<risk2>", "<risk3>"]
}}

Tier rules: HOT if total >= 13, WARM if total >= 8, COLD otherwise."""

    try:
        result = _call_claude(system, user)
        # Recalculate to ensure correctness
        keys = ["score_motivation", "score_timeline", "score_equity",
                "score_condition", "score_flexibility"]
        total = sum(int(result.get(k, 1)) for k in keys)
        result["total_score"] = total
        result["tier"] = "HOT" if total >= 13 else "WARM" if total >= 8 else "COLD"
        return result
    except json.JSONDecodeError as exc:
        logger.exception("qualify-lead: JSON parse failed")
        raise HTTPException(502, f"Claude returned invalid JSON: {exc}")
    except Exception as exc:
        logger.exception("qualify-lead failed")
        raise HTTPException(500, str(exc))


# ── 2. Offer Generator ─────────────────────────────────────────────────────────

class GenerateOfferRequest(BaseModel):
    lead_id: str | None = None
    property_address: str = ""
    city: str | None = None
    motivation_tag: str | None = None
    ai_qualification_summary: str | None = None
    asking_price: float | None = None
    mao: float | None = None
    arv: float | None = None
    repair_estimate: float | None = None
    model_config = {"extra": "allow"}


@router.post("/generate-offer")
def generate_offer(body: GenerateOfferRequest) -> dict:
    arv = body.arv or 0.0
    repairs = body.repair_estimate or 0.0
    assignment_fee = 10_000.0
    mao = body.mao if body.mao is not None else (arv * 0.70 - repairs - assignment_fee)

    lead_data = body.model_dump(exclude_none=True)

    system = (
        "You are an expert Texas real estate wholesaler and negotiation specialist. "
        "Output ONLY valid JSON, no prose or markdown."
    )
    user = f"""Generate 3 strategic offer options for this wholesale deal.

LEAD: {json.dumps(lead_data, default=str, indent=2)}
ARV: ${arv:,.0f}
Repair Estimate: ${repairs:,.0f}
Assignment Fee Target: ${assignment_fee:,.0f}
MAO (70% rule − repairs − fee): ${mao:,.0f}

Return ONLY this JSON:
{{
  "options": [
    {{
      "name": "<offer name e.g. 'Fast Cash Close'>",
      "offer_price": <number>,
      "close_timeline": "<e.g. '7-10 business days'>",
      "selling_points": ["<point1>", "<point2>", "<point3>"],
      "pitch": "<2-3 sentence seller pitch>"
    }}
  ],
  "objections": [
    {{
      "objection": "<common seller objection>",
      "script": "<word-for-word response>"
    }}
  ]
}}

Create 3 options: (1) at MAO with fastest close, (2) slightly above MAO with standard close,
(3) creative terms (subject-to, seller finance, or delayed close). Include 3 objection handlers.
All offers must be ethical — no pressure, no fake urgency."""

    try:
        return _call_claude(system, user, max_tokens=2500)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Claude returned invalid JSON: {exc}")
    except Exception as exc:
        logger.exception("generate-offer failed")
        raise HTTPException(500, str(exc))


# ── 3. Outreach Writer ─────────────────────────────────────────────────────────

class WriteOutreachRequest(BaseModel):
    lead_id: str | None = None
    property_address: str = ""
    city: str | None = None
    owner_first_name: str | None = None
    motivation_tag: str | None = None
    contact_attempts: int = 0
    channel: str = "sms"
    tone: str = "friendly"
    model_config = {"extra": "allow"}


@router.post("/write-outreach")
def write_outreach(body: WriteOutreachRequest) -> list:
    lead_data = body.model_dump(exclude_none=True)

    system = (
        "You are a TCPA/CAN-SPAM compliant Texas real estate outreach specialist. "
        "Never use pressure tactics, fake urgency, or imply physical surveillance. "
        "Output ONLY a valid JSON array, no prose or markdown."
    )
    user = f"""Write 3 outreach message variations.

Channel: {body.channel}
Tone: {body.tone}
LEAD: {json.dumps(lead_data, default=str, indent=2)}

Section 4 & 5 compliance rules:
- No pressure, urgency language, or fake deadlines
- Source leads via "public records" — never say you drove by or watched the property
- SMS: include "Reply STOP to opt out", keep segments ≤160 chars
- Email: include [Unsubscribe] placeholder and physical mailing address
- Contact hours: 9am–7pm CT, Mon–Fri only
- Personalize with seller first name and property address

Return ONLY a JSON array:
[
  {{
    "channel": "{body.channel}",
    "subject": "<email subject line or null for SMS>",
    "body": "<full message body>",
    "estimated_response_rate_notes": "<one sentence on why this variation converts>"
  }}
]"""

    try:
        result = _call_claude(system, user, max_tokens=2000)
        return result if isinstance(result, list) else [result]
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Claude returned invalid JSON: {exc}")
    except Exception as exc:
        logger.exception("write-outreach failed")
        raise HTTPException(500, str(exc))


# ── 4. Buyer Matcher ───────────────────────────────────────────────────────────

class MatchBuyersRequest(BaseModel):
    deal_id: str | None = None
    property_address: str = ""
    contract_price: float | None = None
    buyer_price: float | None = None
    arv: float | None = None
    repair_estimate: float | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    zip_code: str | None = None
    closing_date: str | None = None
    model_config = {"extra": "allow"}


@router.post("/match-buyers")
def match_buyers(body: MatchBuyersRequest) -> dict:
    from tools.crm import CRMStore
    crm = CRMStore()
    buyers_raw = crm.get_active_buyers()[:20]  # cap at 20

    deal_data = body.model_dump(exclude_none=True)

    system = (
        "You are an expert real estate wholesaler matching deals to the right buyer. "
        "Output ONLY valid JSON, no prose or markdown."
    )
    user = f"""Rank the top buyer matches for this wholesale deal.

DEAL:
{json.dumps(deal_data, default=str, indent=2)}

BUYER POOL ({len(buyers_raw)} buyers):
{json.dumps(buyers_raw, default=str, indent=2)}

Return ONLY this JSON:
{{
  "ranked_buyers": [
    {{
      "buyer": {{<buyer object>}},
      "fit_score": <0-100>,
      "fit_reason": "<why this buyer fits>",
      "personalization_tip": "<how to pitch this specific buyer>"
    }}
  ],
  "blast_email_subject": "<subject line for buyer blast email>",
  "blast_email_body": "<email body for all buyers — include property address, price, ARV, repairs>",
  "blast_sms": "<SMS blast ≤160 chars>"
}}

Return top 5 matches. Consider: buy-box fit (zip/price/type), close speed, reliability score."""

    try:
        return _call_claude(system, user, max_tokens=3000)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Claude returned invalid JSON: {exc}")
    except Exception as exc:
        logger.exception("match-buyers failed")
        raise HTTPException(500, str(exc))


# ── 5. Lightweight connectivity test ──────────────────────────────────────────

@router.get("/test")
def test_anthropic_connection() -> dict:
    """1-token Haiku ping using the env-var key. Used as a backend health check."""
    client = _get_client()  # raises 503 if key missing
    client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1,
        messages=[{"role": "user", "content": "ping"}],
    )
    return {"ok": True}


# ── 6. CSV column mapper (list merge tool) ────────────────────────────────────

class MapColumnsRequest(BaseModel):
    headers: list[str]
    samples: list[list[str]] = []


@router.post("/map-columns")
def map_columns(body: MapColumnsRequest) -> dict:
    """Map arbitrary CSV headers (PropStream, county rolls, XLeads, …) to the
    canonical lead schema. Used by the frontend Master List Builder so users can
    drop lists with any column naming and get a clean merge."""
    client = _get_client()
    system = (
        "You map spreadsheet columns from real-estate lead lists to a canonical schema. "
        "Output ONLY valid JSON, no prose or markdown."
    )
    user = f"""Map these CSV columns to canonical lead fields.

COLUMNS (index: header):
{json.dumps(list(enumerate(body.headers)), default=str)}

SAMPLE ROWS (for disambiguation):
{json.dumps(body.samples[:3], default=str)}

Canonical fields:
property_address (the SITUS/property street address — NOT the owner mailing address),
city, state, zip_code, owner_first_name, owner_last_name,
owner_full_name (only if one column holds the complete name),
owner_phone_1, owner_email, bedrooms, bathrooms, sqft, asking_price

Return ONLY this JSON (omit fields with no matching column):
{{"mapping": {{"<canonical_field>": <column index integer>}}}}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        result = json.loads(raw)
        mapping = result.get("mapping", {})
        # Validate: only known fields, indices in range
        valid_fields = {
            "property_address", "city", "state", "zip_code", "owner_first_name",
            "owner_last_name", "owner_full_name", "owner_phone_1", "owner_email",
            "bedrooms", "bathrooms", "sqft", "asking_price",
        }
        clean = {
            k: int(v) for k, v in mapping.items()
            if k in valid_fields and isinstance(v, (int, float, str))
            and str(v).lstrip("-").isdigit() and 0 <= int(v) < len(body.headers)
        }
        return {"mapping": clean}
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Claude returned invalid JSON: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("map-columns failed")
        raise HTTPException(500, str(exc))


class TestKeyRequest(BaseModel):
    key: str


@router.post("/test-key")
def test_api_key(body: TestKeyRequest) -> dict:
    """Test a caller-supplied API key directly. Creates a local client (does not update the
    global singleton) so the Setup Wizard can validate the key the user just entered."""
    k = body.key.strip()
    if not k:
        raise HTTPException(400, detail="No key provided")
    try:
        local_client = anthropic.Anthropic(api_key=k)
        local_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(401, detail="Invalid API key")
    except Exception as exc:
        logger.warning("test-key: unexpected error: %s", exc)
        raise HTTPException(500, detail=str(exc))
    return {"ok": True}
