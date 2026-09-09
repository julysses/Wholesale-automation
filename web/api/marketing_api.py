"""Bounded WARM-lead SMS delivery with current database eligibility checks."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from string import Formatter
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from tools.crm import get_supabase_client
from tools.sms_client import SMSClient
from schemas.outreach import OutreachMessage, OutreachChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing", tags=["Marketing"])


class BulkSMSRequest(BaseModel):
    lead_ids: list[UUID] = Field(min_length=1, max_length=25)
    template: str = Field(
        default="Hi {first_name}, I'm following up on {address}. Are you still considering a cash offer? Reply STOP to opt out.",
        min_length=1, max_length=1600,
    )

    @field_validator("template")
    @classmethod
    def validate_template(cls, value: str) -> str:
        try:
            for _, field, spec, conversion in Formatter().parse(value):
                if field is not None and (field not in {"first_name", "address"} or spec or conversion):
                    raise ValueError("Only {first_name} and {address} placeholders are supported.")
        except ValueError as exc:
            raise ValueError("Use a valid SMS template with only {first_name} and {address} placeholders.") from exc
        return value


def _contact_suppressed(sb, phone: str, lead_id: str | None = None) -> bool:
    """Check the shared suppression registry before sending; query errors fail closed."""
    if lead_id and (sb.table("dnc_registry").select("id").eq("lead_id", lead_id).limit(1).execute().data):
        return True
    digits = re.sub(r"\D", "", phone)
    variants = {phone.strip(), digits, f"+{digits}"}
    if len(digits) == 10:
        variants.update({f"1{digits}", f"+1{digits}"})
    elif len(digits) == 11 and digits.startswith("1"):
        variants.add(digits[1:])
    return bool(sb.table("dnc_registry").select("id").in_("phone_number", list(variants)).limit(1).execute().data)


@router.post("/bulk-sms-warm")
async def bulk_sms_warm(body: BulkSMSRequest) -> dict:
    """Send a selected batch before responding, so failures cannot look queued."""
    return await run_in_threadpool(_process_bulk_sms, body)


def _process_bulk_sms(body: BulkSMSRequest) -> dict:
    sb = get_supabase_client()
    if sb is None:
        raise HTTPException(503, "Database not configured")
    sms = SMSClient()
    lead_ids = list(dict.fromkeys(str(value) for value in body.lead_ids))
    counts = {"sent_count": 0, "failed_count": 0, "skipped_count": 0, "dry_run_count": 0, "log_failed_count": 0}

    for lead_id in lead_ids:
        delivery_recorded = False
        try:
            lead = (sb.table("leads").select("id,owner_first_name,property_address,owner_phone_1,status,dnc,ai_calling_paused")
                    .eq("id", lead_id).single().execute().data or {})
            phone = lead.get("owner_phone_1") or ""
            if (not phone or lead.get("dnc") or lead.get("ai_calling_paused")
                    or lead.get("status") in {"dead", "dnc", "closed", "under_contract", "hot", "cold", "qualified_hot", "qualified_cold"}):
                counts["skipped_count"] += 1
                continue
            # The WARM screen can contain an older qualification. Re-read the
            # newest result before acting on its displayed selection.
            qualifications = (sb.table("qualification_results").select("classification")
                              .eq("lead_id", lead_id).order("created_at", desc=True).limit(1).execute().data or [])
            is_warm = (qualifications[0].get("classification") == "WARM" if qualifications
                       else lead.get("status") in {"warm", "qualified_warm"})
            if not is_warm or _contact_suppressed(sb, phone, lead_id):
                counts["skipped_count"] += 1
                continue
            text = body.template.format(
                first_name=lead.get("owner_first_name") or "there",
                address=lead.get("property_address") or "your property",
            )
            if not re.search(r"reply\s+stop\b", text, re.IGNORECASE):
                text += " Reply STOP to opt out."
            message = OutreachMessage(
                lead_id=lead_id, channel=OutreachChannel.SMS, body=text,
                compliance_cleared=True,
            )
            sent = sms.send(message, phone)
            status = "dry_run" if sent and message.a2p_provider.endswith(":dry-run") else "sent" if sent else "failed"
            counts[f"{status}_count"] += 1
            delivery_recorded = True
            sb.table("outreach_activity").insert({
                "lead_id": lead_id, "channel": "sms", "direction": "outbound",
                "status": status, "message": text,
            }).execute()
            if status == "sent":
                sb.table("leads").update({"last_contact_date": datetime.now(timezone.utc).date().isoformat()}).eq("id", lead_id).execute()
        except Exception:
            counts["log_failed_count" if delivery_recorded else "failed_count"] += 1
            logger.exception("WARM SMS failed for lead %s", lead_id)

    return {
        "status": "partial" if counts["failed_count"] or counts["log_failed_count"] else "complete",
        "target_count": len(lead_ids), "processed_count": len(lead_ids), **counts,
    }
