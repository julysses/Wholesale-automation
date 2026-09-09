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
import re
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


# ── 1b. Batch Lead Qualifier (auto-score after import) ────────────────────────

class BatchLeadInput(BaseModel):
    lead_id: str
    property_address: str = ""
    city: str | None = None
    state: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    motivation_tag: str | None = None
    seller_notes: str | None = None
    model_config = {"extra": "allow"}


class QualifyLeadsBatchRequest(BaseModel):
    leads: list[BatchLeadInput]


MAX_BATCH_LEADS = 25
DEFAULT_SCORE_BATCH_SIZE = 25
MAX_SCORE_BATCH_SIZE = MAX_BATCH_LEADS

SCORING_SELECT_COLUMNS = (
    "id,property_address,city,state,zip_code,owner_first_name,owner_last_name,"
    "owner_mailing_address,source,motivation_tag,seller_notes,asking_price,"
    "estimated_equity_pct,loan_balance,estimated_arv,status,internal_notes"
)


def _supabase_or_503() -> Any:
    from tools.crm import get_supabase_client

    supabase = get_supabase_client()
    if supabase is None:
        raise HTTPException(503, detail="Supabase service role is not configured")
    return supabase


def _count_leads(
    supabase: Any,
    *,
    status: str | None = None,
    unscored: bool = False,
    exclude_status: str | None = None,
) -> int:
    query = supabase.table("leads").select("id", count="exact")
    if status:
        query = query.eq("status", status)
    if unscored:
        query = query.is_("score_motivation", "null")
    if exclude_status:
        query = query.neq("status", exclude_status)
    resp = query.execute()
    count = getattr(resp, "count", None)
    if count is not None:
        return int(count)
    return len(resp.data or [])


def _lead_scoring_status(supabase: Any) -> dict[str, int | bool]:
    total = _count_leads(supabase)
    failed = _count_leads(supabase, status="scoring_error")
    unscored = _count_leads(supabase, unscored=True, exclude_status="scoring_error")
    hot = _count_leads(supabase, status="qualified_hot")
    warm = _count_leads(supabase, status="qualified_warm")
    cold = _count_leads(supabase, status="qualified_cold")
    scored = max(0, total - unscored - failed)
    return {
        "total": total,
        "scored": scored,
        "unscored": unscored,
        "failed": failed,
        "hot": hot,
        "warm": warm,
        "cold": cold,
        "complete": unscored == 0,
    }


def _lead_to_scoring_payload(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "lead_id": str(lead.get("id") or lead.get("lead_id")),
        "property_address": lead.get("property_address", ""),
        "city": lead.get("city"),
        "state": lead.get("state"),
        "zip_code": lead.get("zip_code"),
        "owner_first_name": lead.get("owner_first_name"),
        "owner_last_name": lead.get("owner_last_name"),
        "owner_mailing_address": lead.get("owner_mailing_address"),
        "source": lead.get("source"),
        "motivation_tag": lead.get("motivation_tag"),
        "seller_notes": lead.get("seller_notes"),
        "asking_price": lead.get("asking_price"),
        "estimated_equity_pct": lead.get("estimated_equity_pct"),
        "loan_balance": lead.get("loan_balance"),
        "estimated_arv": lead.get("estimated_arv"),
    }


@router.post("/qualify-leads-batch")
def qualify_leads_batch(body: QualifyLeadsBatchRequest) -> dict:
    """Score up to MAX_BATCH_LEADS leads in a single Claude call. Used by the
    frontend's auto-scoring loop that runs after a CSV/Excel import so freshly
    loaded leads get scored without a human clicking through them one at a time."""
    if not body.leads:
        raise HTTPException(400, detail="No leads provided")
    if len(body.leads) > MAX_BATCH_LEADS:
        raise HTTPException(400, detail=f"Max {MAX_BATCH_LEADS} leads per batch call")

    client = _get_client()
    leads_payload = [lead.model_dump(exclude_none=True) for lead in body.leads]

    system = (
        "You are an expert Texas real estate wholesaler with 15+ years of experience "
        "identifying motivated sellers. Score EVERY lead in the provided array. "
        "Output ONLY a valid JSON array, no prose or markdown."
    )
    user = f"""Score each of these wholesale real estate leads on 5 factors, 1 (weak) to 3 (strong).

LEADS:
{json.dumps(leads_payload, default=str, indent=2)}

For EACH lead in the array, return one object (match by lead_id):
{{
  "lead_id": "<same lead_id from input>",
  "score_motivation": <1-3>,
  "score_timeline": <1-3>,
  "score_equity": <1-3>,
  "score_condition": <1-3>,
  "score_flexibility": <1-3>,
  "qualification_summary": "<1-2 sentence summary>",
  "recommended_next_action": "<specific, actionable next step>"
}}

Return ONLY a JSON array with exactly one object per input lead."""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        results = json.loads(raw)
        if not isinstance(results, list):
            raise ValueError("Claude did not return a JSON array")

        keys = ["score_motivation", "score_timeline", "score_equity", "score_condition", "score_flexibility"]
        out = []
        for r in results:
            if not isinstance(r, dict) or "lead_id" not in r:
                continue
            total = sum(int(r.get(k, 1)) for k in keys)
            tier = "HOT" if total >= 13 else "WARM" if total >= 8 else "COLD"
            out.append({
                "lead_id": r["lead_id"],
                "score_motivation": int(r.get("score_motivation", 1)),
                "score_timeline": int(r.get("score_timeline", 1)),
                "score_equity": int(r.get("score_equity", 1)),
                "score_condition": int(r.get("score_condition", 1)),
                "score_flexibility": int(r.get("score_flexibility", 1)),
                "total_score": total,
                "tier": tier,
                "qualification_summary": str(r.get("qualification_summary", ""))[:500],
                "recommended_next_action": str(r.get("recommended_next_action", ""))[:300],
            })
        return {"results": out}
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Claude returned invalid JSON: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("qualify-leads-batch failed")
        raise HTTPException(500, str(exc))


# ── 1c. Consolidated Master List Import ───────────────────────────────────────

IMPORT_FIELDS = {
    "property_address", "city", "state", "zip_code",
    "owner_first_name", "owner_last_name",
    "owner_phone_1", "owner_phone_2", "owner_phone_3", "owner_email",
    "owner_mailing_address", "property_type", "bedrooms", "bathrooms",
    "sqft", "year_built", "asking_price", "source", "status",
}

NUMERIC_IMPORT_FIELDS = {"bedrooms", "bathrooms", "sqft", "year_built", "asking_price"}
PHONE_IMPORT_FIELDS = {"owner_phone_1", "owner_phone_2", "owner_phone_3"}


class ImportLeadRow(BaseModel):
    property_address: str
    city: str | None = None
    state: str | None = "TX"
    zip_code: str | None = None
    owner_first_name: str | None = None
    owner_last_name: str | None = None
    owner_phone_1: str | None = None
    owner_phone_2: str | None = None
    owner_phone_3: str | None = None
    owner_email: str | None = None
    owner_mailing_address: str | None = None
    property_type: str | None = None
    bedrooms: int | float | str | None = None
    bathrooms: int | float | str | None = None
    sqft: int | float | str | None = None
    year_built: int | float | str | None = None
    asking_price: int | float | str | None = None
    source: str | None = None
    stack_count: int | None = None
    sources: list[str] | None = None
    model_config = {"extra": "allow"}


class ImportMasterListRequest(BaseModel):
    rows: list[ImportLeadRow]
    score_with_claude: bool = True


class ScoreUnscoredLeadsRequest(BaseModel):
    batch_size: int = DEFAULT_SCORE_BATCH_SIZE
    rescore_existing: bool = False
    include_errors: bool = False


def _clean_import_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if field == "state":
        return str(value).strip().upper()[:2] or "TX"
    if field == "zip_code":
        z = re.sub(r"\D", "", str(value))
        return z[:5] or None
    if field in PHONE_IMPORT_FIELDS:
        phone = re.sub(r"[^\d+]", "", str(value))
        return phone or None
    if field in NUMERIC_IMPORT_FIELDS:
        cleaned = re.sub(r"[^0-9.]", "", str(value))
        if not cleaned:
            return None
        num = float(cleaned)
        if field in {"bedrooms", "sqft", "year_built"}:
            return int(num)
        return num
    return value


def _normalize_import_address(raw: str) -> str:
    s = (raw or "").lower().strip()
    s = re.sub(r"[.,#]", " ", s)
    s = re.sub(r"\s+", " ", s)
    suffixes = {
        "street": "st", "avenue": "ave", "drive": "dr", "lane": "ln", "road": "rd",
        "court": "ct", "boulevard": "blvd", "place": "pl", "circle": "cir",
        "trail": "trl", "parkway": "pkwy", "highway": "hwy", "terrace": "ter",
        "square": "sq", "loop": "lp",
    }
    return " ".join(suffixes.get(part, part) for part in s.split()).strip()


def _lead_import_key(row: dict[str, Any]) -> str:
    address = _normalize_import_address(str(row.get("property_address") or ""))
    city = " ".join(str(row.get("city") or "").lower().split())
    state = str(row.get("state") or "TX").strip().upper()
    zip_code = str(row.get("zip_code") or "").strip()[:5]
    # A street address is not unique across cities. Prefer locality so adding a
    # previously missing ZIP does not create another copy of the same property.
    return f"{address}|{city}|{state}" if city else f"{address}|{zip_code}|{state}"


def _payload_from_import_row(row: ImportLeadRow) -> dict[str, Any]:
    raw = row.model_dump(exclude_none=True)
    payload: dict[str, Any] = {}
    for field in IMPORT_FIELDS:
        if field in raw:
            payload[field] = _clean_import_value(field, raw[field])
    if not payload.get("state"):
        payload["state"] = "TX"
    if not payload.get("status"):
        payload["status"] = "new"
    sources = row.sources or []
    if sources:
        payload["source"] = " | ".join(sources)[:250]
    if row.stack_count:
        note = f"Imported stack_count={row.stack_count}"
        payload["internal_notes"] = note
    return {k: v for k, v in payload.items() if v is not None}


def _merge_payloads(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for field, value in incoming.items():
        if value in (None, ""):
            continue
        if field == "source" and existing.get("source"):
            current = [s.strip() for s in str(existing["source"]).split("|") if s.strip()]
            added = [s.strip() for s in str(value).split("|") if s.strip()]
            merged["source"] = " | ".join(dict.fromkeys(current + added))[:250]
        elif field == "internal_notes" and existing.get("internal_notes"):
            if str(value) not in str(existing["internal_notes"]):
                merged["internal_notes"] = f"{existing['internal_notes']}\n{value}"
        elif existing.get(field) in (None, ""):
            merged[field] = value
    return {k: v for k, v in merged.items() if k in IMPORT_FIELDS or k == "internal_notes"}


def _score_imported_leads_with_claude(leads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not leads:
        return {}
    client = _get_client()
    scored: dict[str, dict[str, Any]] = {}
    keys = ["score_motivation", "score_timeline", "score_equity", "score_condition", "score_flexibility"]
    system = (
        "You are an expert Texas real estate wholesaler. Rank and qualify uploaded lead lists. "
        "Score EVERY lead in the provided array. Output ONLY a valid JSON array, no prose or markdown. "
        "The qualification_summary MUST explain why the lead is HOT, WARM, or COLD using only the evidence provided."
    )
    for i in range(0, len(leads), MAX_BATCH_LEADS):
        batch = leads[i:i + MAX_BATCH_LEADS]
        user = f"""Score and rank these consolidated wholesale real estate leads.

LEADS:
{json.dumps(batch, default=str, indent=2)}

For EACH lead, return:
{{
  "lead_id": "<same lead_id>",
  "score_motivation": <1-3>,
  "score_timeline": <1-3>,
  "score_equity": <1-3>,
  "score_condition": <1-3>,
  "score_flexibility": <1-3>,
  "qualification_summary": "<1-2 sentence reason explaining the HOT/WARM/COLD classification>",
  "recommended_next_action": "<specific next action>"
}}

Return ONLY a JSON array with exactly one object per input lead."""
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        results = json.loads(raw)
        if not isinstance(results, list):
            raise ValueError("Claude did not return a JSON array")
        for result in results:
            if not isinstance(result, dict) or "lead_id" not in result:
                continue
            lead_id = str(result["lead_id"])
            clean_scores = {k: max(1, min(3, int(result.get(k, 1)))) for k in keys}
            total = sum(clean_scores.values())
            tier = "HOT" if total >= 13 else "WARM" if total >= 8 else "COLD"
            scored[lead_id] = {
                **clean_scores,
                "ai_qualification_summary": str(result.get("qualification_summary", ""))[:500],
                "status": "qualified_hot" if tier == "HOT" else "qualified_warm" if tier == "WARM" else "qualified_cold",
                "precision_tier": 1 if tier == "HOT" else 2 if tier == "WARM" else 3,
            }
    return scored


def _append_scoring_note(existing: str | None, reason: str) -> str:
    note = f"Claude scoring error: {reason[:300]}"
    if existing and note not in existing:
        return f"{existing}\n{note}"[:4000]
    return existing or note


def _mark_scoring_error(supabase: Any, lead: dict[str, Any], reason: str) -> None:
    lead_id = str(lead.get("id") or lead.get("lead_id"))
    supabase.table("leads").update({
        "status": "scoring_error",
        "internal_notes": _append_scoring_note(lead.get("internal_notes"), reason),
    }).eq("id", lead_id).execute()


def _persist_scored_lead(supabase: Any, lead_id: str, score_payload: dict[str, Any]) -> None:
    supabase.table("leads").update(score_payload).eq("id", lead_id).execute()


def _score_and_persist_batch(
    supabase: Any,
    leads: list[dict[str, Any]],
    *,
    allow_split: bool = True,
) -> tuple[int, int]:
    """Score a batch and persist all successful rows.

    Returns (scored_count, failed_count). If a multi-lead Claude call fails,
    split to single-lead calls so one malformed row does not block the backlog.
    """
    if not leads:
        return 0, 0

    scoring_payload = [_lead_to_scoring_payload(lead) for lead in leads]
    try:
        scored = _score_imported_leads_with_claude(scoring_payload)
        scored_count = 0
        failed_count = 0
        for lead in leads:
            lead_id = str(lead.get("id"))
            score_payload = scored.get(lead_id)
            if not score_payload:
                _mark_scoring_error(supabase, lead, "Claude did not return a score for this lead")
                failed_count += 1
                continue
            try:
                _persist_scored_lead(supabase, lead_id, score_payload)
                scored_count += 1
            except Exception as exc:
                logger.exception("Failed to persist Claude score for lead %s", lead_id)
                _mark_scoring_error(supabase, lead, f"Supabase update failed: {exc}")
                failed_count += 1
        return scored_count, failed_count
    except Exception as exc:
        if allow_split and len(leads) > 1:
            logger.warning("Claude batch failed; retrying as single-lead calls: %s", exc)
            scored_total = 0
            failed_total = 0
            for lead in leads:
                scored_one, failed_one = _score_and_persist_batch(
                    supabase, [lead], allow_split=False
                )
                scored_total += scored_one
                failed_total += failed_one
            return scored_total, failed_total

        logger.exception("Claude scoring failed for lead batch")
        for lead in leads:
            _mark_scoring_error(supabase, lead, str(exc))
        return 0, len(leads)


@router.get("/lead-scoring-status")
def lead_scoring_status() -> dict:
    """Return database-backed Claude scoring progress for the Leads table."""
    supabase = _supabase_or_503()
    return _lead_scoring_status(supabase)


@router.post("/score-unscored-leads")
def score_unscored_leads(body: ScoreUnscoredLeadsRequest = ScoreUnscoredLeadsRequest()) -> dict:
    """Score one durable batch of leads from Supabase and persist results.

    This is intentionally bounded so the frontend can call it repeatedly without
    relying on a fragile in-memory browser queue or one long serverless request.
    """
    supabase = _supabase_or_503()
    batch_size = max(1, min(MAX_SCORE_BATCH_SIZE, int(body.batch_size or DEFAULT_SCORE_BATCH_SIZE)))

    query = (
        supabase.table("leads")
        .select(SCORING_SELECT_COLUMNS)
        .order("created_at", desc=False)
        .limit(batch_size)
    )
    if not body.rescore_existing:
        query = query.is_("score_motivation", "null")
    if not body.include_errors:
        query = query.neq("status", "scoring_error")

    resp = query.execute()
    leads = resp.data or []
    if not leads:
        return {
            "status": "complete",
            "processed": 0,
            "scored": 0,
            "failed": 0,
            "progress": _lead_scoring_status(supabase),
        }

    scored_count = 0
    failed_count = 0
    for i in range(0, len(leads), 5):
        scored_part, failed_part = _score_and_persist_batch(supabase, leads[i:i + 5])
        scored_count += scored_part
        failed_count += failed_part

    if scored_count:
        try:
            supabase.rpc("recompute_priority_ranks").execute()
        except Exception:
            logger.exception("Failed to recompute priority ranks after scoring batch")

    return {
        "status": "ok",
        "processed": len(leads),
        "scored": scored_count,
        "failed": failed_count,
        "progress": _lead_scoring_status(supabase),
    }


@router.post("/import-master-list")
def import_master_list(body: ImportMasterListRequest) -> dict:
    """Consolidate an uploaded master list into Supabase, then have Claude rank
    the saved leads. The browser sends already mapped rows; the backend owns the
    final de-duplication/upsert and scoring write so imports do not create raw
    duplicate CRM records."""
    if not body.rows:
        raise HTTPException(400, detail="No rows provided")

    from tools.crm import get_supabase_client

    supabase = get_supabase_client()
    if supabase is None:
        raise HTTPException(503, detail="Supabase service role is not configured")

    incoming_by_key: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in body.rows:
        payload = _payload_from_import_row(row)
        if not payload.get("property_address") or not payload.get("city"):
            skipped += 1
            continue
        key = _lead_import_key(payload)
        if not key:
            skipped += 1
            continue
        incoming_by_key[key] = _merge_payloads(incoming_by_key.get(key, {}), payload)

    if not incoming_by_key:
        raise HTTPException(400, detail="No importable rows with property_address and city")

    existing_columns = (
        "id,property_address,city,state,zip_code,owner_first_name,owner_last_name,"
        "owner_phone_1,owner_phone_2,owner_phone_3,owner_email,owner_mailing_address,"
        "property_type,bedrooms,bathrooms,sqft,year_built,asking_price,source,status,internal_notes"
    )
    existing_rows = []
    offset = 0
    # PostgREST caps a response even when no limit is requested. Keep reading
    # until an empty page; advancing by the actual page length also supports
    # installations whose configured cap is smaller than our requested page.
    while True:
        page = (
            supabase.table("leads").select(existing_columns)
            .order("id").range(offset, offset + 999).execute().data or []
        )
        if not page:
            break
        existing_rows.extend(page)
        offset += len(page)
    existing_by_key = {_lead_import_key(row): row for row in existing_rows if row.get("property_address")}

    imported = 0
    updated = 0
    saved_for_scoring: list[dict[str, Any]] = []

    saved_rows: list[dict[str, Any]] = []
    new_rows: list[dict[str, Any]] = []
    for key, incoming in incoming_by_key.items():
        existing = existing_by_key.get(key)
        if existing:
            lead_id = existing["id"]
            update_payload = _merge_payloads(existing, incoming)
            changes = {k: v for k, v in update_payload.items() if v != existing.get(k)}
            if changes:
                supabase.table("leads").update(changes).eq("id", lead_id).execute()
            saved = {**existing, **update_payload, "id": lead_id}
            updated += 1
            saved_rows.append(saved)
        else:
            new_rows.append(incoming)

    # A large upload should not require one network round trip per new lead.
    # Use default_to_null=False so omitted fields retain database defaults.
    for start in range(0, len(new_rows), 250):
        batch = new_rows[start:start + 250]
        data = supabase.table("leads").insert(batch, default_to_null=False).execute().data or []
        if len(data) != len(batch):
            raise HTTPException(503, "Import could not confirm all saved rows. Retry the upload to reconcile it.")
        saved_rows.extend(data)
        imported += len(data)

    for saved in saved_rows:
        lead_id = saved["id"]
        saved_for_scoring.append({
            "lead_id": str(lead_id),
            "property_address": saved.get("property_address", ""),
            "city": saved.get("city"),
            "state": saved.get("state"),
            "owner_first_name": saved.get("owner_first_name"),
            "owner_last_name": saved.get("owner_last_name"),
            "source": saved.get("source"),
        })

    scored_count = 0
    if body.score_with_claude and saved_for_scoring:
        scored = _score_imported_leads_with_claude(saved_for_scoring)
        for lead_id, score_payload in scored.items():
            supabase.table("leads").update(score_payload).eq("id", lead_id).execute()
        scored_count = len(scored)
        try:
            supabase.rpc("recompute_priority_ranks").execute()
        except Exception:
            logger.exception("Failed to recompute priority ranks after import")

    return {
        "status": "ok",
        "input_rows": len(body.rows),
        "consolidated_rows": len(incoming_by_key),
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "scored": scored_count,
    }


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
    """Have Claude review an arbitrary lead list (PropStream, county tax /
    foreclosure rolls, XLeads, …) and figure out how to reshape it into the
    canonical lead schema. Returns not just a column mapping but the data-management
    plan: whether the address column is a combined "addr, city, state zip" string
    that must be split, and the city/state to backfill when the list omits them
    (common for single-county rolls). The frontend applies this plan deterministically
    to every row."""
    client = _get_client()
    system = (
        "You are a data-cleaning assistant for a real-estate wholesaling CRM. You review "
        "messy lead lists from any source and decide how to reshape them into the app's "
        "schema. You handle PropStream exports, county tax-delinquent and pre-foreclosure "
        "rolls, probate lists, and skip-trace exports. Output ONLY valid JSON, no prose or markdown."
    )
    user = f"""Review this lead list and produce a plan to load it into the canonical schema.

COLUMNS (index: header):
{json.dumps(list(enumerate(body.headers)), default=str)}

SAMPLE ROWS (index-aligned to the columns above):
{json.dumps(body.samples[:4], default=str)}

Canonical fields:
- property_address: the SITUS / physical property street address — NOT the owner's mailing address
- city, state, zip_code
- owner_mailing_address: the owner's mailing address if separate from the property
- owner_first_name, owner_last_name
- owner_full_name: use ONLY if a single column holds the whole name
- owner_phone_1, owner_phone_2, owner_phone_3: map multiple phone columns (skip-trace
  lists often have several) into these in order
- owner_email
- property_type, bedrooms, bathrooms, sqft, year_built, asking_price

Decide:
1. Which column index maps to each canonical field (omit fields with no match).
2. address_combined: true if the property_address column ALSO contains city/state/zip
   inline (e.g. "123 Main St, Dallas, TX 75201"). If true, the app will split it.
3. default_city / default_state: if this looks like a single-city or single-county list
   and the rows have no usable city column, infer the city and 2-letter state from the
   sample data (e.g. county seat). Leave blank if you can't tell.

Return ONLY this JSON:
{{
  "mapping": {{"<canonical_field>": <column index integer>}},
  "address_combined": <true|false>,
  "default_city": "<city or empty string>",
  "default_state": "<2-letter state or empty string>",
  "notes": "<one short sentence on what you did, for the user>"
}}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        result = json.loads(raw)
        mapping = result.get("mapping", {})
        valid_fields = {
            "property_address", "city", "state", "zip_code", "owner_mailing_address",
            "owner_first_name", "owner_last_name", "owner_full_name",
            "owner_phone_1", "owner_phone_2", "owner_phone_3", "owner_email",
            "property_type", "bedrooms", "bathrooms", "sqft", "year_built", "asking_price",
        }
        clean = {
            k: int(v) for k, v in mapping.items()
            if k in valid_fields and isinstance(v, (int, float, str))
            and str(v).lstrip("-").isdigit() and 0 <= int(v) < len(body.headers)
        }
        return {
            "mapping": clean,
            "address_combined": bool(result.get("address_combined", False)),
            "default_city": str(result.get("default_city", "") or "").strip()[:80],
            "default_state": str(result.get("default_state", "") or "").strip().upper()[:2],
            "notes": str(result.get("notes", "") or "").strip()[:200],
        }
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
