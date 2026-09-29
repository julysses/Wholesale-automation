"""Lead-list management: see every uploaded list, re-score it, or delete it whole.

Deleting is safe by default: leads a human has already worked (contacted,
appointment, offer, under contract, ...) are kept unless ``include_worked`` is
passed explicitly.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lead-lists", tags=["Lead Lists"])

# Statuses that mean "nobody has touched this lead yet".
UNWORKED_STATUSES = ["new", "qualified_hot", "qualified_warm", "qualified_cold", "scoring_error"]
PAGE = 1000


def _supabase() -> Any:
    from tools.crm import get_supabase_client

    client = get_supabase_client()
    if client is None:
        raise HTTPException(503, detail="Supabase service role is not configured")
    return client


def _count(supabase: Any, list_id: str, *, unworked_only: bool = False, unscored: bool = False) -> int:
    q = supabase.table("leads").select("id", count="exact").eq("list_id", list_id)
    if unworked_only:
        q = q.in_("status", UNWORKED_STATUSES)
    if unscored:
        q = q.is_("score_motivation", "null")
    resp = q.limit(1).execute()
    count = getattr(resp, "count", None)
    return int(count) if count is not None else len(resp.data or [])


@router.get("")
def list_lead_lists() -> dict:
    supabase = _supabase()
    lists = (
        supabase.table("lead_lists").select("id,name,filename,created_at,row_count")
        .order("created_at", desc=True).execute().data or []
    )
    out = []
    for row in lists:
        lead_id = str(row["id"])
        total = _count(supabase, lead_id)
        out.append({
            **row,
            "lead_count": total,
            "unscored": _count(supabase, lead_id, unscored=True),
            "deletable_count": _count(supabase, lead_id, unworked_only=True),
            "worked_count": None,
        })
        out[-1]["worked_count"] = total - out[-1]["deletable_count"]
    return {"lists": out}


@router.delete("/{list_id}")
def delete_lead_list(list_id: str, include_worked: bool = False) -> dict:
    """Delete an uploaded list and its leads. Worked leads are kept unless
    ``include_worked=true``; the list record is removed once it is empty."""
    supabase = _supabase()
    found = supabase.table("lead_lists").select("id,name").eq("id", list_id).limit(1).execute().data
    if not found:
        raise HTTPException(404, detail="List not found")

    deleted = 0
    failed = 0
    while True:
        q = supabase.table("leads").select("id").eq("list_id", list_id)
        if not include_worked:
            q = q.in_("status", UNWORKED_STATUSES)
        ids = [r["id"] for r in (q.limit(PAGE).execute().data or [])]
        if not ids:
            break
        try:
            supabase.table("leads").delete().in_("id", ids).execute()
            deleted += len(ids)
        except Exception:
            logger.exception("Bulk delete failed for list %s; retrying row by row", list_id)
            progressed = 0
            for lead_id in ids:
                try:
                    supabase.table("leads").delete().eq("id", lead_id).execute()
                    deleted += 1
                    progressed += 1
                except Exception:
                    failed += 1
            if progressed == 0:
                break  # nothing deletable left in this page; avoid looping forever

    remaining = _count(supabase, list_id)
    list_removed = False
    if remaining == 0:
        supabase.table("lead_lists").delete().eq("id", list_id).execute()
        list_removed = True
    try:
        supabase.rpc("recompute_priority_ranks").execute()
    except Exception:
        logger.exception("Failed to recompute priority ranks after list delete")
    return {
        "status": "ok",
        "name": found[0]["name"],
        "deleted": deleted,
        "kept_worked": remaining,
        "failed": failed,
        "list_removed": list_removed,
    }


@router.post("/{list_id}/rescore")
def rescore_lead_list(list_id: str) -> dict:
    """Re-run the rules engine over every lead in one list (instant)."""
    from web.api import ScoreUnscoredLeadsRequest, _score_batch_rules

    supabase = _supabase()
    from web.api import _score_via_sql

    body = ScoreUnscoredLeadsRequest(rescore_existing=True, include_errors=True, list_id=list_id)
    return {"status": "ok", **(_score_via_sql(supabase, body) or _score_batch_rules(supabase, body, 100_000))}


# ── Retention / cleanup suggestions ───────────────────────────────────────────
# Rule ids match public.lead_cleanup_ids(). Only untouched leads (unworked status,
# no contact attempts, not DNC) can ever be selected, so nothing a human worked,
# no DNC/opt-out suppression record and no deal history is at risk.

CLEANUP_RULES: dict[str, dict[str, str]] = {
    "not_real_estate": {
        "label": "Not real estate (business personal property, minerals, utilities)",
        "action": "Delete now",
        "timeframe": "Immediately",
        "why": "Tax records for business equipment or non-land assets. There is no house to contract or assign.",
    },
    "duplicates": {
        "label": "Duplicate properties (same street + city)",
        "action": "Delete now",
        "timeframe": "Immediately",
        "why": "Keeps the copy that has a list source and the best score; extras cause double outreach.",
    },
    "stale_prefor": {
        "label": "Pre-foreclosure leads older than 60 days, never contacted",
        "action": "Re-pull, then delete",
        "timeframe": "60 days",
        "why": "Texas foreclosure sales run the first Tuesday of each month. After ~60 days the sale has happened or the owner cured; the lead is stale. Re-pull a fresh list first.",
    },
    "stale_cold": {
        "label": "COLD leads older than 90 days, never contacted",
        "action": "Delete after 90 days",
        "timeframe": "90 days",
        "why": "No distress evidence and no follow-up. Not worth carrying; a fresh list pull will surface them again if they become distressed.",
    },
    "stale_warm": {
        "label": "WARM leads older than 180 days, never contacted",
        "action": "Delete after 180 days",
        "timeframe": "180 days",
        "why": "If it was not worth a call in six months it will not be; re-pull to refresh the data.",
    },
    "stale_tax_roll": {
        "label": "Delinquent tax roll rows older than 12 months, never contacted",
        "action": "Replace yearly",
        "timeframe": "12 months",
        "why": "The county roll is republished annually; last year's delinquencies are usually paid or foreclosed.",
    },
}

HOLD_POLICY = [
    {"who": "HOT and WARM leads not yet contacted", "keep": "Work them - do not delete",
     "why": "These are the pipeline. Call HOT within 48 hours; give WARM one SMS + one call this week."},
    {"who": "Contacted / follow-up scheduled", "keep": "Hold 12 months from last contact",
     "why": "Seller timelines change; 'not now' often becomes 'yes' within a year. Archive after 12 months of silence."},
    {"who": "DNC / opted out / STOP", "keep": "Keep permanently",
     "why": "Deleting the record removes your suppression and risks re-contacting them (TCPA). Never delete."},
    {"who": "Appointments, offers, under contract, closed", "keep": "Keep 7 years",
     "why": "Transaction and compliance records."},
]


@router.get("/cleanup-suggestions")
def cleanup_suggestions() -> dict:
    supabase = _supabase()
    try:
        counts = supabase.rpc("lead_cleanup_counts").execute().data or {}
    except Exception:
        logger.exception("lead_cleanup_counts failed")
        raise HTTPException(503, detail="Cleanup rules are not installed yet (apply the latest migration).")
    if isinstance(counts, list):
        counts = counts[0] if counts else {}
    return {
        "rules": [{"id": rid, **meta, "count": int(counts.get(rid, 0))} for rid, meta in CLEANUP_RULES.items()],
        "hold": HOLD_POLICY,
    }


@router.post("/cleanup/{rule}")
def apply_cleanup(rule: str) -> dict:
    if rule not in CLEANUP_RULES:
        raise HTTPException(404, detail="Unknown cleanup rule")
    supabase = _supabase()
    try:
        ids = [str(i) for i in (supabase.rpc("lead_cleanup_ids", {"p_rule": rule}).execute().data or [])]
    except Exception:
        logger.exception("lead_cleanup_ids failed")
        raise HTTPException(503, detail="Cleanup rules are not installed yet (apply the latest migration).")
    deleted = failed = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        try:
            supabase.table("leads").delete().in_("id", chunk).execute()
            deleted += len(chunk)
        except Exception:
            logger.exception("Bulk cleanup delete failed; retrying row by row")
            for lead_id in chunk:
                try:
                    supabase.table("leads").delete().eq("id", lead_id).execute()
                    deleted += 1
                except Exception:
                    failed += 1
    try:
        supabase.rpc("recompute_priority_ranks").execute()
    except Exception:
        logger.exception("Failed to recompute priority ranks after cleanup")
    return {"status": "ok", "rule": rule, "deleted": deleted, "failed": failed}
