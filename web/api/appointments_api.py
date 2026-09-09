from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.calendar_adapter import CalendarAdapter
from tools.crm import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


class CreateAppointmentRequest(BaseModel):
    lead_id: str
    scheduled_at: datetime
    appointment_type: str = "phone"
    notes: Optional[str] = None


@router.post("")
async def create_appointment(body: CreateAppointmentRequest):
    """Create a new appointment and sync to calendar."""
    supabase = get_supabase_client()
    
    # 1. Insert into DB
    try:
        resp = supabase.table("appointments").insert({
            "lead_id": body.lead_id,
            "scheduled_at": body.scheduled_at.isoformat(),
            "appointment_type": body.appointment_type,
            "notes": body.notes,
            "status": "scheduled",
            "source": "manual",
        }).execute()
        
        if not resp.data:
            raise HTTPException(status_code=500, detail="Failed to create appointment in DB")
            
        appointment = resp.data[0]
        
    except Exception as exc:
        logger.error(f"Appointment creation failed: {exc}")
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=str(exc))

    calendar_sync = "failed"
    # 2. Sync to Calendar
    try:
        # Fetch lead address for calendar entry
        lead_resp = supabase.table("leads").select("property_address").eq("id", body.lead_id).single().execute()
        address = lead_resp.data.get("property_address", "Unknown Property") if lead_resp.data else "Unknown Property"
        
        calendar = CalendarAdapter()
        synced = calendar.sync_deal_milestones(
            deal_id=body.lead_id, # using lead_id as deal_id for now
            address=address,
            milestones={f"Appointment ({body.appointment_type})": body.scheduled_at}
        )
        calendar_sync = "synced" if synced else calendar.status
    except Exception as exc:
        logger.warning(f"Calendar sync failed: {exc}")
        # We don't fail the whole request if calendar sync fails

    return {**appointment, "calendar_sync": calendar_sync}
