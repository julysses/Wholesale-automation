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
    body = ScoreUnscoredLeadsRequest(rescore_existing=True, include_errors=True, list_id=list_id)
    return {"status": "ok", **_score_batch_rules(supabase, body, 100_000)}
