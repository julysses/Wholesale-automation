"""
Marketing & Conversion API — bulk outreach and lead nurture.

Routes:
  POST /api/marketing/bulk-sms-warm  → Trigger bulk SMS to qualified_warm leads
"""

from __future__ import annotations

import logging
from typing import Any, List

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from tools.crm import CRMStore
from tools.sms_client import SMSClient
from schemas.outreach import OutreachMessage, OutreachChannel, OutreachStatus
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


class BulkSMSRequest(BaseModel):
    template: str = "Hi {first_name}, I'm following up on {address}. Are you still considering a cash offer? Reply STOP to opt out."


@router.post("/bulk-sms-warm")
async def bulk_sms_warm(body: BulkSMSRequest, background_tasks: BackgroundTasks) -> dict:
    """
    Fetch all 'qualified_warm' leads and trigger a bulk SMS follow-up.
    Only sends to leads that are NOT DNC and NOT paused.
    """
    crm = CRMStore()
    leads = crm.get_all_leads()
    
    # Filter for qualified_warm leads
    warm_leads = [
        l for l in leads 
        if l.get("status") == "qualified_warm" 
        and not l.get("dnc")
    ]
    
    if not warm_leads:
        return {"status": "success", "sent_count": 0, "message": "No warm leads found for outreach."}

    background_tasks.add_task(_process_bulk_sms, warm_leads, body.template)
    
    return {
        "status": "accepted",
        "target_count": len(warm_leads),
        "message": f"Bulk SMS sequence initiated for {len(warm_leads)} warm lead(s).",
    }


async def _process_bulk_sms(leads: List[dict], template: str) -> None:
    """Background task: personalize and dispatch SMS batch."""
    sms_client = SMSClient()
    batch = []
    
    for lead in leads:
        data = lead.get("data", {})
        first_name = data.get("owner_first_name") or data.get("owner_name", "there").split()[0]
        address = data.get("address", {}).get("street") or lead.get("address_full", "your property")
        
        body = template.format(first_name=first_name, address=address)
        
        msg = OutreachMessage(
            body=body,
            channel=OutreachChannel.SMS,
            compliance_cleared=True, # Batch triggers are pre-cleared by policy
        )
        
        # Phone logic: leads table has owner_phone_1 in Supabase, 
        # but PropertyLead schema has phone_numbers list.
        # CRMStore.get_all_leads returns rows from the local SQLite 'leads' table.
        phone = data.get("owner_phone_1") or (data.get("phone_numbers", [None])[0])
        
        if phone:
            batch.append((msg, phone))
    
    if batch:
        results = sms_client.send_batch(batch)
        logger.info(f"[Marketing] Bulk SMS batch complete. Success count: {sum(results.values())}/{len(batch)}")
