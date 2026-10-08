"""Durable manual bookings. External calendar capability is reported truthfully."""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field

from tools.calendar_adapter import CalendarAdapter
from tools.crm import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


class CreateAppointmentRequest(BaseModel):
    request_id: UUID
    lead_id: UUID
    scheduled_at: AwareDatetime
    appointment_type: Literal["phone", "in_person", "video"] = "phone"
    notes: str | None = Field(default=None, max_length=4000)


class AppointmentTransition(BaseModel):
    expected_status: Literal["scheduled", "confirmed"]
    status: Literal["confirmed", "completed", "no_show", "cancelled"]


def _operator(request: Request) -> str:
    operator = getattr(request.state, "user_id", None)
    if not operator:
        raise HTTPException(401, "Sign in to continue")
    return str(operator)


def _result(value: object) -> dict:
    if not isinstance(value, dict):
        raise HTTPException(503, "Appointment outcome is unconfirmed. Retry with the same booking details.")
    if value.get("missing"):
        raise HTTPException(404, "Appointment not found")
    if value.get("conflict"):
        raise HTTPException(409, "Booking details or status changed. Refresh appointments before continuing.")
    if value.get("invalid"):
        raise HTTPException(422, "Choose an existing lead and a future appointment time.")
    saved = value.get("appointment")
    if not isinstance(saved, dict) or not saved.get("id"):
        raise HTTPException(503, "Appointment outcome is unconfirmed. Retry with the same booking details.")
    return {**saved, "reused": bool(value.get("reused"))}


@router.post("")
async def create_appointment(body: CreateAppointmentRequest, request: Request):
    operator = _operator(request)
    try:
        db = get_supabase_client()
        value = db.rpc("book_appointment", {
            "p_id": str(body.request_id), "p_lead": str(body.lead_id),
            "p_at": body.scheduled_at.isoformat(), "p_type": body.appointment_type,
            "p_notes": body.notes or "", "p_operator": operator,
            "p_calendar": CalendarAdapter().status,
        }).execute().data
    except Exception:
        logger.exception("Appointment booking acknowledgement unavailable")
        raise HTTPException(503, "Appointment outcome is unconfirmed. Retry with the same booking details.")
    return _result(value)


@router.patch("/{appointment_id}")
async def transition_appointment(appointment_id: UUID, body: AppointmentTransition, request: Request):
    operator = _operator(request)
    try:
        value = get_supabase_client().rpc("transition_appointment", {
            "p_id": str(appointment_id), "p_expected": body.expected_status,
            "p_next": body.status, "p_operator": operator,
        }).execute().data
    except Exception:
        logger.exception("Appointment status acknowledgement unavailable")
        raise HTTPException(503, "Appointment status is unconfirmed. Refresh before continuing.")
    return _result(value)
