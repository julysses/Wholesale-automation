"""
Leads API router — handles lead re-scoring and batch operations.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.seller_score_agent import SellerScoreAgent
from schemas.property import PropertyLead
from tools.crm import CRMStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/leads", tags=["Leads"])


class RescoreRequest(BaseModel):
    strategy: Optional[str] = None   # filter by routing_action: ai_calling | sms_nurture | suppress
    min_score: Optional[int] = None  # only rescore leads with current distress_score >= this value


class RescoreResponse(BaseModel):
    status: str
    message: str
    count: int
    tiers: Dict[str, int]


@router.post("/rescore", response_model=RescoreResponse)
def rescore_leads(filters: RescoreRequest = RescoreRequest()) -> RescoreResponse:
    """
    Recalculate distress scores and priority tiers for leads in the database.

    Optional filters:
      - strategy: restrict to leads currently routed as 'ai_calling', 'sms_nurture', or 'suppress'
      - min_score: only rescore leads whose current distress_score >= this threshold
    """
    crm = CRMStore()
    agent = SellerScoreAgent()

    # 1. Fetch all leads from the local CRM store
    raw_leads = crm.get_all_leads()
    if not raw_leads:
        return RescoreResponse(
            status="ok",
            message="No leads found in database to re-score.",
            count=0,
            tiers={"A": 0, "B": 0, "C": 0, "D": 0},
        )

    # 2. Parse raw database rows into PropertyLead objects
    leads: List[PropertyLead] = []
    for raw in raw_leads:
        try:
            lead = PropertyLead.model_validate(raw["data"])
            leads.append(lead)
        except Exception as exc:
            logger.error(f"Failed to parse lead {raw.get('id')}: {exc}")
            continue

    if not leads:
        raise HTTPException(status_code=500, detail="Failed to parse any leads from database.")

    # 3. Apply optional filters before scoring
    if filters.min_score is not None:
        leads = [
            lead for lead in leads
            if (lead.distress_score or 0) >= filters.min_score
        ]

    if filters.strategy is not None:
        from agents.seller_score_agent import score_to_tier, tier_to_routing
        strategy_filter = filters.strategy.lower()
        filtered = []
        for lead in leads:
            tier = score_to_tier(lead.distress_score or 0)
            action, _ = tier_to_routing(tier)
            if action == strategy_filter:
                filtered.append(lead)
        leads = filtered

    if not leads:
        return RescoreResponse(
            status="ok",
            message="No leads matched the provided filters.",
            count=0,
            tiers={"A": 0, "B": 0, "C": 0, "D": 0},
        )

    # 4. Re-calculate scores and tiers in batch
    results = agent.score_batch(leads)

    # 5. Persist updated leads back to the database
    for lead in leads:
        crm.save_lead(lead)

    # 6. Aggregate tier counts for the response
    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for res in results:
        tier_counts[res.priority_tier] += 1

    filter_desc = ""
    if filters.strategy:
        filter_desc += f" (strategy={filters.strategy})"
    if filters.min_score is not None:
        filter_desc += f" (min_score={filters.min_score})"

    logger.info(f"Re-scored {len(leads)} leads{filter_desc}: {tier_counts}")

    return RescoreResponse(
        status="ok",
        message=f"Successfully re-scored {len(leads)} leads{filter_desc}.",
        count=len(leads),
        tiers=tier_counts,
    )


def trigger_rescore_after_import(lead_ids: Optional[List[str]] = None) -> None:
    """
    Hook called by the import pipeline after a batch import completes.
    Rescores all leads (or a specific subset by lead_id) in the background.
    """
    crm = CRMStore()
    agent = SellerScoreAgent()

    raw_leads = crm.get_all_leads()
    if not raw_leads:
        return

    leads: List[PropertyLead] = []
    for raw in raw_leads:
        if lead_ids and raw.get("id") not in lead_ids:
            continue
        try:
            lead = PropertyLead.model_validate(raw["data"])
            leads.append(lead)
        except Exception as exc:
            logger.error(f"[rescore_import] Failed to parse lead {raw.get('id')}: {exc}")

    if not leads:
        return

    results = agent.score_batch(leads)
    for lead in leads:
        crm.save_lead(lead)

    tier_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for res in results:
        tier_counts[res.priority_tier] += 1

    scope = f"{len(lead_ids)} specific leads" if lead_ids else "all leads"
    logger.info(f"[rescore_import] Auto-rescore after import ({scope}): {tier_counts}")
